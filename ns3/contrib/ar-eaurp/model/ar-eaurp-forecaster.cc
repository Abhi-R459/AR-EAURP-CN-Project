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
    // Normalise by the largest power ever seen, so the network works on values
    // of order one regardless of the panel rating.
    double maxWatts = 0.0;
    size_t total = 0;
    for (const auto& trace : m_traces)
    {
        total += trace.size();
        for (const auto& s : trace)
        {
            maxWatts = std::max(maxWatts, s.watts);
        }
    }
    if (maxWatts <= 0.0 || total < (size_t)(m_inputLen + m_horizon) * 4)
    {
        NS_LOG_WARN("not enough harvest history to train the forecaster");
        return 0.0;
    }
    m_scale = maxWatts;

    m_sequences.clear();
    for (const auto& trace : m_traces)
    {
        if (trace.size() < (size_t)(m_inputLen + m_horizon))
        {
            continue;
        }
        for (size_t start = 0; start + m_inputLen + m_horizon <= trace.size(); ++start)
        {
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
            m_sequences.emplace_back(seq, target);
        }
    }

    if (m_sequences.size() < 20)
    {
        NS_LOG_WARN("too few training sequences: " << m_sequences.size());
        return 0.0;
    }

    // Chronological split: the last 20% is held out, so the model is never
    // scored on windows it trained on.
    const size_t split = (size_t)(0.8 * m_sequences.size());
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
    for (size_t idx = split; idx < m_sequences.size(); ++idx)
    {
        const auto& seq = m_sequences[idx];
        const double truth = seq.second * m_scale;
        const Vec y = m_lstm.Forward(seq.first);
        lstmErr += std::fabs(y[0] * m_scale - truth);

        // persistence: the next horizon looks like the last sample
        persistErr += std::fabs(seq.first.back()[0] * m_scale - truth);

        // seasonal naive: the same phase of the day, one period earlier. The
        // window is shorter than a day, so the closest available proxy is the
        // mean of the window, which is what a node without a model would use.
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
