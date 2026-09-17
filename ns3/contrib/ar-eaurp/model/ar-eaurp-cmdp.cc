#include "ar-eaurp-cmdp.h"

#include "ns3/log.h"

#include <algorithm>
#include <cmath>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("ArEaurpCmdp");

namespace arEaurp
{

namespace
{
constexpr double kEnergyCostWeight = 0.05;
} // namespace

const char*
ActionName(uint32_t action)
{
    switch (action)
    {
    case ACTION_TRUST:
        return "trust";
    case ACTION_ENERGY:
        return "energy_surplus";
    case ACTION_BALANCED:
        return "balanced";
    case ACTION_DIVERSE:
        return "diversified";
    default:
        return "unknown";
    }
}

CmdpAgent::CmdpAgent(uint32_t nActions, uint32_t hidden, uint32_t seed)
    : m_nActions(nActions),
      m_rng(seed),
      m_cursor(0),
      m_capacity(5000),
      m_lr(1e-3),
      m_gamma(0.9),
      m_batch(32),
      m_targetSync(200),
      m_trainEvery(4),
      m_epsStart(0.30),
      m_epsEnd(0.05),
      m_epsDecay(800.0),
      m_pdrFloor(0.90),
      m_penalty(5.0),
      m_lambdaLr(0.05),
      m_lambdaMax(20.0),
      m_lambda(0.0),
      m_lambdaPeak(0.0),
      m_steps(0),
      m_decisions(0),
      m_violations(0),
      m_trainCalls(0),
      m_rewardSum(0.0),
      m_rewardCount(0),
      m_actionCounts(nActions, 0)
{
    m_online.Add(kStateDim, hidden, Activation::RELU, m_rng);
    m_online.Add(hidden, hidden, Activation::RELU, m_rng);
    m_online.Add(hidden, nActions, Activation::NONE, m_rng);

    std::mt19937 targetRng(seed + 1);
    m_target.Add(kStateDim, hidden, Activation::RELU, targetRng);
    m_target.Add(hidden, hidden, Activation::RELU, targetRng);
    m_target.Add(hidden, nActions, Activation::NONE, targetRng);
    m_target.CopyFrom(m_online);

    m_buffer.reserve(m_capacity);
}

void
CmdpAgent::SetConstraint(double pdrFloor, double penalty, double lambdaLr, double lambdaMax)
{
    m_pdrFloor = pdrFloor;
    m_penalty = penalty;
    m_lambdaLr = lambdaLr;
    m_lambdaMax = lambdaMax;
}

void
CmdpAgent::SetExploration(double epsStart, double epsEnd, double decaySteps)
{
    m_epsStart = epsStart;
    m_epsEnd = epsEnd;
    m_epsDecay = std::max(1.0, decaySteps);
}

void
CmdpAgent::SetLearning(double lr, double gamma, uint32_t batch, uint32_t targetSync)
{
    m_lr = lr;
    m_gamma = gamma;
    m_batch = batch;
    m_targetSync = targetSync;
}

double
CmdpAgent::Epsilon() const
{
    const double decay = std::exp(-(double)m_decisions / m_epsDecay);
    return m_epsEnd + (m_epsStart - m_epsEnd) * decay;
}

uint32_t
CmdpAgent::Act(const Vec& state)
{
    m_decisions++;
    std::uniform_real_distribution<double> uni(0.0, 1.0);
    uint32_t action;
    if (uni(m_rng) < Epsilon())
    {
        std::uniform_int_distribution<uint32_t> pick(0, m_nActions - 1);
        action = pick(m_rng);
    }
    else
    {
        action = Greedy(state);
    }
    m_actionCounts[action]++;
    return action;
}

uint32_t
CmdpAgent::Greedy(const Vec& state) const
{
    const Vec& q = m_online.Forward(state);
    uint32_t best = 0;
    for (uint32_t a = 1; a < m_nActions; ++a)
    {
        if (q[a] > q[best])
        {
            best = a;
        }
    }
    return best;
}

double
CmdpAgent::ShapedReward(bool delivered, double energyCost, double pdrWindow, bool& violated) const
{
    const double base = delivered ? 1.0 : -1.0;
    const double shortfall = std::max(0.0, m_pdrFloor - pdrWindow);
    violated = (shortfall > 0.0);
    return base - kEnergyCostWeight * energyCost - m_lambda * shortfall * m_penalty;
}

void
CmdpAgent::Observe(const Vec& state, uint32_t action, double reward, const Vec& next)
{
    m_rewardSum += reward;
    m_rewardCount++;

    if (m_buffer.size() < m_capacity)
    {
        m_buffer.push_back({state, action, reward, next});
    }
    else
    {
        m_buffer[m_cursor] = {state, action, reward, next};
        m_cursor = (m_cursor + 1) % m_capacity;
    }

    m_steps++;
    if (m_steps % m_trainEvery == 0 && m_buffer.size() >= m_batch)
    {
        TrainBatch();
    }
}

void
CmdpAgent::TrainBatch()
{
    std::uniform_int_distribution<size_t> pick(0, m_buffer.size() - 1);
    m_online.ZeroGrad();

    for (uint32_t b = 0; b < m_batch; ++b)
    {
        const Transition& tr = m_buffer[pick(m_rng)];

        // Double-DQN target: the online network picks the next action, the
        // target network values it. Cheap, and it removes most of the
        // overestimation bias that makes plain DQN unstable on a noisy reward.
        const Vec qNextOnline = m_online.Forward(tr.next);
        uint32_t bestNext = 0;
        for (uint32_t a = 1; a < m_nActions; ++a)
        {
            if (qNextOnline[a] > qNextOnline[bestNext])
            {
                bestNext = a;
            }
        }
        const Vec qNextTarget = m_target.Forward(tr.next);
        const double y = tr.reward + m_gamma * qNextTarget[bestNext];

        const Vec q = m_online.Forward(tr.state);
        Vec grad(m_nActions, 0.0);
        // Huber gradient on the selected action only.
        double err = q[tr.action] - y;
        err = std::max(-1.0, std::min(1.0, err));
        grad[tr.action] = err;
        m_online.Backward(grad);
    }

    m_online.Step(m_lr, m_batch);
    m_trainCalls++;
    if (m_trainCalls % m_targetSync == 0)
    {
        m_target.CopyFrom(m_online);
    }
    else
    {
        m_target.Polyak(m_online, 0.01);
    }
}

void
CmdpAgent::UpdateLambda(double pdrWindow)
{
    const double shortfall = m_pdrFloor - pdrWindow;
    if (shortfall > 0.0)
    {
        m_violations++;
    }
    m_lambda = std::max(0.0, std::min(m_lambdaMax, m_lambda + m_lambdaLr * shortfall));
    m_lambdaPeak = std::max(m_lambdaPeak, m_lambda);
}

} // namespace arEaurp
} // namespace ns3
