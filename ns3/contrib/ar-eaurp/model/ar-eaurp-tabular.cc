#include "ar-eaurp-tabular.h"
#include <algorithm>
#include <cmath>

namespace ns3::arEaurp
{
TabularAgent::State TabularAgent::Discretise(const Vec& state)
{
    State result{};
    for (size_t i = 0; i < result.size(); ++i)
        result[i] = static_cast<int>(std::lround(std::clamp(state.at(i), 0.0, 1.0) * 10));
    return result;
}

uint32_t TabularAgent::Act(const Vec& state, double explorationCoin, uint32_t randomAction)
{
    const auto& q = m_q[Discretise(state)];
    return explorationCoin < 0.1 ? randomAction % 2 : (q[0] >= q[1] ? 0 : 1);
}

void TabularAgent::Observe(const Vec& state, uint32_t action, bool delivered, const Vec& next)
{
    const double reward = delivered ? 1.0 : -1.0;
    const auto& nextQ = m_q[Discretise(next)];
    auto& q = m_q[Discretise(state)];
    q.at(action) += 0.1 * (reward + 0.9 * std::max(nextQ[0], nextQ[1]) - q.at(action));
    m_reward += reward;
    ++m_updates;
}

void EndpointTrust::Record(bool sent)
{
    if (sent) ++m_sent;
    else ++m_received;
    if (m_received) m_trust = 0.7 * m_trust + 0.3 * static_cast<double>(m_sent) / m_received;
}

double EndpointTrust::Trust() const { return std::clamp(m_trust, 0.0, 1.0); }
}
