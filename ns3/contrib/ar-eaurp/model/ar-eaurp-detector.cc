#include "ar-eaurp-detector.h"

#include "ns3/log.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("ArEaurpDetector");

namespace arEaurp
{

namespace
{
constexpr double kLabelSmooth = 0.9; //!< one-sided label smoothing
constexpr double kLr = 2e-4;
constexpr double kEps = 1e-9;
} // namespace

GanAnomalyDetector::GanAnomalyDetector(uint32_t featureDim,
                                       uint32_t latentDim,
                                       uint32_t hidden,
                                       uint32_t seed)
    : m_featureDim(featureDim),
      m_latentDim(latentDim),
      m_hidden(hidden),
      m_rng(seed),
      m_mean(featureDim, 0.0),
      m_scale(featureDim, 1.0),
      m_threshold(1.0),
      m_trained(false),
      m_dLoss(0.0),
      m_gLoss(0.0)
{
    m_discriminator.Add(featureDim, hidden, Activation::LEAKY_RELU, m_rng);
    m_discriminator.Add(hidden, hidden / 2, Activation::LEAKY_RELU, m_rng);
    m_discriminator.Add(hidden / 2, 1, Activation::SIGMOID, m_rng);

    m_generator.Add(latentDim, hidden, Activation::RELU, m_rng);
    m_generator.Add(hidden, hidden, Activation::RELU, m_rng);
    m_generator.Add(hidden, featureDim, Activation::NONE, m_rng);
}

void
GanAnomalyDetector::AddTrainingSample(const std::vector<double>& features)
{
    if (features.size() == m_featureDim)
    {
        m_train.push_back(features);
    }
}

void
GanAnomalyDetector::Standardise(const std::vector<double>& in, Vec& out) const
{
    out.assign(m_featureDim, 0.0);
    for (uint32_t i = 0; i < m_featureDim; ++i)
    {
        out[i] = (in[i] - m_mean[i]) / m_scale[i];
    }
}

bool
GanAnomalyDetector::Fit(uint32_t epochs, uint32_t batch, double percentile)
{
    if (m_train.size() < 32)
    {
        NS_LOG_WARN("not enough clean windows to train the detector: " << m_train.size());
        return false;
    }

    // Standardise the feature space so no single column dominates purely by
    // scale; the statistics come from the clean phase only.
    for (uint32_t i = 0; i < m_featureDim; ++i)
    {
        double sum = 0.0;
        for (const auto& s : m_train)
        {
            sum += s[i];
        }
        m_mean[i] = sum / (double)m_train.size();
        double var = 0.0;
        for (const auto& s : m_train)
        {
            const double d = s[i] - m_mean[i];
            var += d * d;
        }
        m_scale[i] = std::sqrt(var / (double)m_train.size());
        if (m_scale[i] < 1e-3)
        {
            m_scale[i] = 1e-3;
        }
    }

    std::vector<Vec> data;
    data.reserve(m_train.size());
    for (const auto& s : m_train)
    {
        Vec z;
        Standardise(s, z);
        data.push_back(z);
    }

    std::normal_distribution<double> noise(0.0, 1.0);
    std::uniform_int_distribution<size_t> pick(0, data.size() - 1);

    for (uint32_t epoch = 0; epoch < epochs; ++epoch)
    {
        double dLoss = 0.0;
        double gLoss = 0.0;
        const uint32_t steps = std::max<uint32_t>(1, (uint32_t)(data.size() / batch));

        for (uint32_t step = 0; step < steps; ++step)
        {
            // ---- discriminator: real -> kLabelSmooth, fake -> 0 ----
            m_discriminator.ZeroGrad();
            for (uint32_t b = 0; b < batch; ++b)
            {
                const Vec& real = data[pick(m_rng)];
                const Vec& dr = m_discriminator.Forward(real);
                const double pr = std::min(1.0 - kEps, std::max(kEps, dr[0]));
                dLoss -= std::log(pr);
                // d/dp of -log(p) with the sigmoid derivative folded in by the
                // layer itself: pass dL/dy = -(label/p) + (1-label)/(1-p).
                Vec grad(1, -(kLabelSmooth / pr) + (1.0 - kLabelSmooth) / (1.0 - pr));
                m_discriminator.Backward(grad);

                Vec z(m_latentDim, 0.0);
                for (auto& v : z)
                {
                    v = noise(m_rng);
                }
                const Vec fake = m_generator.Forward(z);
                const Vec& df = m_discriminator.Forward(fake);
                const double pf = std::min(1.0 - kEps, std::max(kEps, df[0]));
                dLoss -= std::log(1.0 - pf);
                Vec gradF(1, 1.0 / (1.0 - pf));
                m_discriminator.Backward(gradF);
            }
            m_discriminator.Step(kLr, 2 * batch);

            // ---- generator: push the discriminator towards 1 on fakes ----
            m_generator.ZeroGrad();
            m_discriminator.ZeroGrad();
            for (uint32_t b = 0; b < batch; ++b)
            {
                Vec z(m_latentDim, 0.0);
                for (auto& v : z)
                {
                    v = noise(m_rng);
                }
                const Vec fake = m_generator.Forward(z);
                const Vec& df = m_discriminator.Forward(fake);
                const double pf = std::min(1.0 - kEps, std::max(kEps, df[0]));
                gLoss -= std::log(pf);
                Vec grad(1, -1.0 / pf);
                // Backward through the (frozen for this step) discriminator to
                // reach the generator's output.
                m_discriminator.Backward(grad);
                // Mlp::Backward leaves dL/d(sample) in the first layer's input
                // gradient; that is the signal the generator trains on.
                m_generator.Backward(m_discriminator.InputGradient());
            }
            m_generator.Step(kLr, batch);
            m_discriminator.ZeroGrad();
        }

        m_dLoss = dLoss / (double)(steps * batch * 2);
        m_gLoss = gLoss / (double)(steps * batch);
    }

    m_trained = true;

    // Approximate the learned healthy manifold with generated samples. The
    // discriminator is useful for training the generator, but its output only
    // distinguishes training examples from generator output; it is not itself
    // an anomaly score for malicious observations.
    m_generatedBank.clear();
    constexpr size_t kGeneratedSamples = 2048;
    m_generatedBank.reserve(kGeneratedSamples);
    for (size_t i = 0; i < kGeneratedSamples; ++i)
    {
        Vec z(m_latentDim, 0.0);
        for (auto& v : z)
        {
            v = noise(m_rng);
        }
        const Vec generated = m_generator.Forward(z);
        m_generatedBank.push_back(generated);
    }

    // Calibrate the threshold on clean samples with the exact same nearest-
    // manifold metric used during evaluation.
    std::vector<double> scores;
    scores.reserve(m_train.size());
    for (const auto& s : m_train)
    {
        scores.push_back(Score(s));
    }
    std::sort(scores.begin(), scores.end());
    const size_t idx = std::min(scores.size() - 1,
                                (size_t)std::llround(percentile / 100.0 * (scores.size() - 1)));
    m_threshold = scores[idx];
    return true;
}

double
GanAnomalyDetector::Score(const std::vector<double>& features) const
{
    if (!m_trained || features.size() != m_featureDim || m_generatedBank.empty())
    {
        return 0.0;
    }
    Vec z;
    Standardise(features, z);
    double nearest = std::numeric_limits<double>::infinity();
    for (const auto& generated : m_generatedBank)
    {
        double squared = 0.0;
        for (uint32_t i = 0; i < m_featureDim; ++i)
        {
            const double difference = z[i] - generated[i];
            squared += difference * difference;
        }
        nearest = std::min(nearest, squared);
    }
    return std::sqrt(nearest / static_cast<double>(m_featureDim));
}

} // namespace arEaurp
} // namespace ns3
