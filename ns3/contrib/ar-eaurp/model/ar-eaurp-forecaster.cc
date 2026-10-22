#include "ar-eaurp-forecaster.h"

#include "ns3/log.h"

#include <algorithm>
#include <cmath>
#include <numeric>
#include <random>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("ArEaurpForecaster");

namespace arEaurp
{

namespace
{
constexpr uint32_t kInputFeatures = 3; //!< normalised power, sin(phase), cos(phase)
constexpr double kTwoPi = 6.283185307179586;
} // namespace

EnergyForecaster::EnergyForecaster(uint32_t inputLen,
                                   uint32_t horizon,
                                   uint32_t hidden,
                                   uint32_t seed)
    : m_inputLen(inputLen),
      m_horizon(horizon),
      m_hidden(hidden),
      m_lstm(kInputFeatures, hidden, 1, seed),
      m_scale(1.0),
      m_lstmMae(0.0),
      m_persistenceMae(0.0),
      m_seasonalMae(0.0),
      m_trained(false),
      m_seed(seed)
{
}

void
EnergyForecaster::AddSample(uint32_t nodeId, double watts, double dayPhase)
{
    if (m_traces.size() <= nodeId)
    {
        m_traces.resize(nodeId + 1);
    }
    m_traces[nodeId].push_back({watts, dayPhase});
}

double
EnergyForecaster::Fit(uint32_t epochs, double lr)
{
    m_trained = false;
    m_validationSequences = 0;
    m_lstmMae = m_persistenceMae = m_seasonalMae = 0.0;
    // Normalise using training intervals only, so validation values cannot leak.
    // The network works on values
    // of order one regardless of the panel rating.
    double maxWatts = 0.0;
    size_t total = 0;
    for (const auto& trace : m_traces)
    {
        total += trace.size();
        const size_t cutoff = static_cast<size_t>(0.7 * trace.size());
        for (size_t i = 0; i < cutoff; ++i) maxWatts = std::max(maxWatts, trace[i].watts);
    }
    if (maxWatts <= 0.0 || total < (size_t)(m_inputLen + m_horizon) * 4)
    {
        NS_LOG_WARN("not enough harvest history to train the forecaster");
        return 0.0;
    }
    m_scale = maxWatts;

    m_sequences.clear();
    decltype(m_sequences) holdout;
    for (const auto& trace : m_traces)
    {
        if (trace.size() < (size_t)(m_inputLen + m_horizon))
        {
            continue;
        }
        const size_t cutoff = static_cast<size_t>(0.7 * trace.size());
        for (size_t start = 0; start + m_inputLen + m_horizon <= trace.size(); ++start)
        {
            const bool training = start + m_inputLen + m_horizon <= cutoff;
            if (!training && start < cutoff) continue; // purge overlapping windows
            std::vector<Vec> seq;
            seq.reserve(m_inputLen);
            for (uint32_t t = 0; t < m_inputLen; ++t)
            {
                const Sample& s = trace[start + t];
                seq.push_back({s.watts / m_scale,
                               std::sin(kTwoPi * s.phase),
                               std::cos(kTwoPi * s.phase)});
            }
            double target = 0.0;
            for (uint32_t t = 0; t < m_horizon; ++t)
            {
                target += trace[start + m_inputLen + t].watts;
            }
            target /= (double)m_horizon * m_scale;
            if (training) m_sequences.emplace_back(seq, target);
            else holdout.emplace_back(seq, target);
        }
    }

    m_validationSequences = holdout.size();
    if (m_sequences.size() < 20 || holdout.empty())
    {
        NS_LOG_WARN("too few training sequences: " << m_sequences.size());
        return 0.0;
    }

    // Each node contributes its earlier 70% to training and its later 30%
    // to validation. No input or target sample occurs in both groups.
    const size_t split = m_sequences.size();
    std::mt19937 rng(m_seed + 17);
    std::vector<size_t> order(split);
    std::iota(order.begin(), order.end(), 0);

    for (uint32_t epoch = 0; epoch < epochs; ++epoch)
    {
        std::shuffle(order.begin(), order.end(), rng);
        for (size_t idx : order)
        {
            const auto& seq = m_sequences[idx];
            m_lstm.TrainStep(seq.first, Vec(1, seq.second), lr);
        }
    }
    m_trained = true;

    // Held-out evaluation against two baselines a node could run for free.
    double lstmErr = 0.0;
    double persistErr = 0.0;
    double seasonalErr = 0.0;
    size_t count = 0;
    for (const auto& seq : holdout)
    {
        const double truth = seq.second * m_scale;
        const Vec y = m_lstm.Forward(seq.first);
        lstmErr += std::fabs(y[0] * m_scale - truth);

        // persistence: the next horizon looks like the last sample
        persistErr += std::fabs(seq.first.back()[0] * m_scale - truth);

        // Window-mean baseline. A true seasonal baseline requires one day
        // of history, which this input window does not contain.
        double windowMean = 0.0;
        for (const auto& step : seq.first)
        {
            windowMean += step[0];
        }
        windowMean = windowMean / (double)seq.first.size() * m_scale;
        seasonalErr += std::fabs(windowMean - truth);
        count++;
    }
    if (count > 0)
    {
        m_lstmMae = lstmErr / (double)count;
        m_persistenceMae = persistErr / (double)count;
        m_seasonalMae = seasonalErr / (double)count;
    }
    return m_lstmMae;
}

double
EnergyForecaster::Predict(const std::deque<std::pair<double, double>>& recent) const
{
    if (!m_trained || recent.size() < m_inputLen)
    {
        return recent.empty() ? 0.0 : recent.back().first;
    }
    // A learned model only controls routing when it beats persistence on the
    // held-out commissioning windows. Until then, keep the validated baseline.
    if (!UsesLstm())
    {
        return recent.back().first;
    }
    std::vector<Vec> seq;
    seq.reserve(m_inputLen);
    auto it = recent.end() - m_inputLen;
    for (; it != recent.end(); ++it)
    {
        seq.push_back({it->first / m_scale,
                       std::sin(kTwoPi * it->second),
                       std::cos(kTwoPi * it->second)});
    }
    const Vec y = m_lstm.Forward(seq);
    return std::max(0.0, y[0] * m_scale);
}

} // namespace arEaurp
} // namespace ns3
