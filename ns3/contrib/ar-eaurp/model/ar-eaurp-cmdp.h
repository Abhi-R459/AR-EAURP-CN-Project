/*
 * Constrained-MDP routing agent -- AR-EAURP step 4.
 *
 * A DQN chooses, per route discovery, which weighting the node should use when
 * it scores its neighbours:
 *
 *   0 trust           ignore energy, follow the most trustworthy relays
 *   1 energy surplus  follow residual charge blended with the harvest forecast
 *   2 balanced        base.pdf's own R_Score = a*T + b*E
 *   3 diversified     as balanced, but avoid the next hop used last time, so a
 *                     flow stops feeding a relay that keeps losing its traffic
 *
 * The advancement asks for a hard floor: delivery must stay at or above 90%
 * even with a third of the network hostile. That is a constraint, not a
 * reward term, so it is carried as a Lagrangian:
 *
 *   r      = +/-1 - w_e * energy_cost - lambda * max(0, floor - PDR_window) * C
 *   lambda <- clip(lambda + eta * (floor - PDR_window), 0, lambda_max)
 *
 * Report lambda and observed violations together with achieved PDR. Reaching
 * the multiplier ceiling shows an unmet target under this learned policy;
 * it does not prove that the constraint is mathematically infeasible.
 *
 * The policy is shared across the fleet (one set of parameters, per-node
 * states and actions) -- the usual parameter-sharing arrangement for
 * multi-agent RL, and the way such a model would be provisioned to nodes.
 */

#ifndef AR_EAURP_CMDP_H
#define AR_EAURP_CMDP_H

#include "ar-eaurp-nnet.h"

#include <cstdint>
#include <random>
#include <vector>

namespace ns3
{
namespace arEaurp
{

constexpr uint32_t kStateDim = 6;

enum RouteAction
{
    ACTION_TRUST = 0,
    ACTION_ENERGY = 1,
    ACTION_BALANCED = 2,
    ACTION_DIVERSE = 3,
    ACTION_COUNT = 4,
};

const char* ActionName(uint32_t action);

class CmdpAgent
{
  public:
    CmdpAgent(uint32_t nActions, uint32_t hidden, uint32_t seed);

    void SetConstraint(double pdrFloor, double penalty, double lambdaLr, double lambdaMax);
    void SetExploration(double epsStart, double epsEnd, double decaySteps);
    void SetLearning(double lr, double gamma, uint32_t batch, uint32_t targetSync);

    /// Epsilon-greedy action for a state.
    uint32_t Act(const Vec& state);

    /// Greedy action, no exploration (used for reporting the learned policy).
    uint32_t Greedy(const Vec& state) const;

    /// Reward with the energy term and the Lagrangian constraint penalty.
    double ShapedReward(bool delivered, double energyCost, double pdrWindow, bool& violated) const;

    /// Store a transition and take a gradient step every m_trainEvery samples.
    void Observe(const Vec& state, uint32_t action, double reward, const Vec& next);

    /// Dual ascent on the constraint multiplier.
    void UpdateLambda(double pdrWindow);

    double Lambda() const
    {
        return m_lambda;
    }

    double Epsilon() const;

    uint64_t Steps() const
    {
        return m_steps;
    }

    uint64_t Violations() const
    {
        return m_violations;
    }

    uint64_t Decisions() const
    {
        return m_decisions;
    }

    uint64_t ActionCount(uint32_t a) const
    {
        return (a < m_actionCounts.size()) ? m_actionCounts[a] : 0;
    }

    double MeanReward() const
    {
        return (m_rewardCount > 0) ? m_rewardSum / (double)m_rewardCount : 0.0;
    }

    double LambdaPeak() const
    {
        return m_lambdaPeak;
    }

  private:
    struct Transition
    {
        Vec state;
        uint32_t action;
        double reward;
        Vec next;
    };

    void TrainBatch();

    uint32_t m_nActions;
    mutable Mlp m_online;
    mutable Mlp m_target;
    std::mt19937 m_rng;

    std::vector<Transition> m_buffer;
    size_t m_cursor;
    size_t m_capacity;

    double m_lr;
    double m_gamma;
    uint32_t m_batch;
    uint32_t m_targetSync;
    uint32_t m_trainEvery;

    double m_epsStart;
    double m_epsEnd;
    double m_epsDecay;

    double m_pdrFloor;
    double m_penalty;
    double m_lambdaLr;
    double m_lambdaMax;
    double m_lambda;
    double m_lambdaPeak;

    uint64_t m_steps;
    uint64_t m_decisions;
    uint64_t m_violations;
    uint64_t m_trainCalls;
    double m_rewardSum;
    uint64_t m_rewardCount;
    std::vector<uint64_t> m_actionCounts;
};

} // namespace arEaurp
} // namespace ns3

#endif /* AR_EAURP_CMDP_H */
