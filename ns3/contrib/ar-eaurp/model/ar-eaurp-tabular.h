#ifndef AR_EAURP_TABULAR_H
#define AR_EAURP_TABULAR_H

#include "ar-eaurp-nnet.h"
#include <array>
#include <map>

namespace ns3::arEaurp
{
// Lekha Eq. (3), (29)-(37). State is a local estimate of trust, charge and
// mobility, discretised to tenths. Actions select trust or diverse routes.
class TabularAgent
{
  public:
    uint32_t Act(const Vec& state, double explorationCoin, uint32_t randomAction);
    void Observe(const Vec& state, uint32_t action, bool delivered, const Vec& next);
    uint64_t Updates() const { return m_updates; }
    size_t States() const { return m_q.size(); }
    double MeanReward() const { return m_updates ? m_reward / m_updates : 0.0; }

  private:
    using State = std::array<int, 3>;
    static State Discretise(const Vec& state);
    std::map<State, std::array<double, 2>> m_q;
    uint64_t m_updates{0};
    double m_reward{0.0};
};

// The senior code credits endpoints, rather than relays. In a packet network
// endpoints can observe only their own sends/receives; no ground truth is read.
class EndpointTrust
{
  public:
    void Record(bool sent);
    double Trust() const;
  private:
    uint64_t m_sent{0};
    uint64_t m_received{0};
    double m_trust{1.0};
};
}
#endif
