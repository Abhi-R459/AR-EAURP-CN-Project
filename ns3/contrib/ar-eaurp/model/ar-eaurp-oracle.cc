#include "ar-eaurp-oracle.h"

#include "ar-eaurp-neighbor.h"
#include "ar-eaurp-packet.h"

#include "ns3/log.h"
#include "ns3/simulator.h"

#include <cmath>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("ArEaurpOracle");

namespace arEaurp
{

Oracle&
Oracle::Get()
{
    static Oracle instance;
    return instance;
}

void
Oracle::Reset(uint32_t nNodes)
{
    m_nNodes = nNodes;
    m_ipToNode.clear();
    m_role.assign(nNodes, ROLE_HONEST);
    m_addr.assign(nNodes, Ipv4Address());

    m_appTx = 0;
    m_appRx = 0;
    m_appTxBytes = 0;
    m_appRxBytes = 0;
    m_delaySum = 0.0;
    m_delaySumSq = 0.0;
    m_hopSum = 0;
    m_forwards = 0;
    m_adversaryDrops = 0;
    m_adversaryDropsLarge = 0;
    m_energyDrops = 0;
    m_noRoute = 0;
    m_controlPackets = 0;
    m_controlBytes = 0;
    m_controlByType.clear();
    m_watchdogArmed = 0;
    m_watchdogConfirmed = 0;
    m_discoveries = 0;
    m_discoveryFailures = 0;
    m_queued = 0;
    m_dequeued = 0;
    m_queueOverflow = 0;
    m_queueExpired = 0;
    m_linkFailures = 0;
    m_linkFailuresData = 0;
    m_localRepairs = 0;

    m_contested.clear();
    m_revocations.clear();

    m_death.assign(nNodes, Seconds(0));
    m_dead = 0;
    m_measurementStart = Seconds(0);
}

void
Oracle::Register(uint32_t nodeId, Ipv4Address addr, uint32_t role)
{
    if (m_role.size() <= nodeId)
    {
        m_role.resize(nodeId + 1, ROLE_HONEST);
        m_addr.resize(nodeId + 1, Ipv4Address());
        m_death.resize(nodeId + 1, Seconds(0));
        m_nNodes = (uint32_t)m_role.size();
    }
    m_ipToNode[addr] = nodeId;
    m_role[nodeId] = role;
    m_addr[nodeId] = addr;
}

uint32_t
Oracle::NodeIdOf(Ipv4Address addr) const
{
    auto i = m_ipToNode.find(addr);
    return (i == m_ipToNode.end()) ? (uint32_t)-1 : i->second;
}

uint32_t
Oracle::RoleOf(Ipv4Address addr) const
{
    const uint32_t id = NodeIdOf(addr);
    return (id == (uint32_t)-1) ? (uint32_t)ROLE_HONEST : m_role[id];
}

bool
Oracle::IsMalicious(Ipv4Address addr) const
{
    return RoleOf(addr) != ROLE_HONEST;
}

bool
Oracle::Measuring() const
{
    return Simulator::Now() >= m_measurementStart;
}

void
Oracle::CountAppTx(uint32_t bytes)
{
    if (!Measuring())
    {
        return;
    }
    m_appTx++;
    m_appTxBytes += bytes;
}

void
Oracle::CountAppRx(uint32_t bytes, Time delay, uint32_t hops)
{
    if (!Measuring())
    {
        return;
    }
    m_appRx++;
    m_appRxBytes += bytes;
    const double d = delay.GetSeconds();
    m_delaySum += d;
    m_delaySumSq += d * d;
    m_hopSum += hops;
}

void
Oracle::CountForward()
{
    if (Measuring())
    {
        m_forwards++;
    }
}

void
Oracle::CountAdversaryDrop(uint32_t bytes, bool large)
{
    if (!Measuring())
    {
        return;
    }
    m_adversaryDrops++;
    if (large)
    {
        m_adversaryDropsLarge++;
    }
}

void
Oracle::CountEnergyDrop()
{
    if (Measuring())
    {
        m_energyDrops++;
    }
}

void
Oracle::CountNoRoute()
{
    if (Measuring())
    {
        m_noRoute++;
    }
}

void
Oracle::CountControl(uint32_t type, uint32_t bytes)
{
    if (!Measuring())
    {
        return;
    }
    m_controlPackets++;
    m_controlBytes += bytes;
    m_controlByType[type]++;
}

void
Oracle::CountWatchdogArmed()
{
    if (Measuring())
    {
        m_watchdogArmed++;
    }
}

void
Oracle::CountWatchdogConfirmed()
{
    if (Measuring())
    {
        m_watchdogConfirmed++;
    }
}

void
Oracle::CountRouteDiscovery(bool succeeded)
{
    if (!Measuring())
    {
        return;
    }
    m_discoveries++;
    if (!succeeded)
    {
        m_discoveryFailures++;
    }
}

void
Oracle::CountQueued()
{
    if (Measuring())
    {
        m_queued++;
    }
}

void
Oracle::CountDequeued()
{
    if (Measuring())
    {
        m_dequeued++;
    }
}

void
Oracle::CountQueueDrop(bool overflow)
{
    if (!Measuring())
    {
        return;
    }
    if (overflow)
    {
        m_queueOverflow++;
    }
    else
    {
        m_queueExpired++;
    }
}

void
Oracle::CountLinkFailure(bool dataFrame)
{
    if (!Measuring())
    {
        return;
    }
    m_linkFailures++;
    if (dataFrame)
    {
        m_linkFailuresData++;
    }
}

void
Oracle::CountLocalRepair()
{
    if (Measuring())
    {
        m_localRepairs++;
    }
}

void
Oracle::ReportContested(Ipv4Address observer, Ipv4Address subject)
{
    m_contested[observer].insert(subject);
}

void
Oracle::ReportRevoked(Ipv4Address observer, Ipv4Address subject)
{
    m_revocations[observer].insert(subject);
}

void
Oracle::DetectionRates(uint32_t minWitnesses,
                       double& truePositiveRate,
                       double& falsePositiveRate,
                       bool useRevocations) const
{
    const auto& source = useRevocations ? m_revocations : m_contested;

    // Count, for every subject, how many *honest* nodes flagged it. An
    // adversary's own accusations must not count towards detection, or a
    // slanderer could manufacture a perfect detection score for its victims.
    std::map<Ipv4Address, uint32_t> witnesses;
    for (const auto& obs : source)
    {
        if (IsMalicious(obs.first))
        {
            continue;
        }
        for (const auto& subject : obs.second)
        {
            witnesses[subject]++;
        }
    }

    uint32_t truePositives = 0;
    uint32_t falsePositives = 0;
    uint32_t positives = 0;
    uint32_t negatives = 0;

    for (uint32_t i = 0; i < m_nNodes; ++i)
    {
        const Ipv4Address addr = m_addr[i];
        if (addr == Ipv4Address())
        {
            continue;
        }
        const bool hostile = (m_role[i] != ROLE_HONEST);
        auto w = witnesses.find(addr);
        const bool flagged = (w != witnesses.end() && w->second >= minWitnesses);
        if (hostile)
        {
            positives++;
            if (flagged)
            {
                truePositives++;
            }
        }
        else
        {
            negatives++;
            if (flagged)
            {
                falsePositives++;
            }
        }
    }

    truePositiveRate = (positives > 0) ? (double)truePositives / positives : 0.0;
    falsePositiveRate = (negatives > 0) ? (double)falsePositives / negatives : 0.0;
}

void
Oracle::ReportNodeDeath(uint32_t nodeId, Time when)
{
    if (nodeId < m_death.size() && m_death[nodeId] == Seconds(0))
    {
        m_death[nodeId] = when;
        m_dead++;
    }
}

Time
Oracle::FirstDeath() const
{
    Time first = Seconds(0);
    for (const Time& t : m_death)
    {
        if (t > Seconds(0) && (first == Seconds(0) || t < first))
        {
            first = t;
        }
    }
    return first;
}

uint32_t
Oracle::DeadNodes() const
{
    return m_dead;
}

void
Oracle::CreateModels(uint32_t seed)
{
    m_detector = std::make_unique<GanAnomalyDetector>(kFeatureDim, 8, 32, seed);
    m_forecaster = std::make_unique<EnergyForecaster>(20, 10, 24, seed + 1);
    m_agent = std::make_unique<CmdpAgent>(ACTION_COUNT, 64, seed + 2);
}

void
Oracle::ClearModels()
{
    m_detector.reset();
    m_forecaster.reset();
    m_agent.reset();
}

std::map<std::string, double>
Oracle::Summary() const
{
    std::map<std::string, double> out;
    out["app_tx"] = (double)m_appTx;
    out["app_rx"] = (double)m_appRx;
    out["pdr"] = (m_appTx > 0) ? (double)m_appRx / (double)m_appTx : 0.0;
    out["mean_delay_s"] = (m_appRx > 0) ? m_delaySum / (double)m_appRx : 0.0;
    if (m_appRx > 1)
    {
        const double mean = m_delaySum / (double)m_appRx;
        const double var = m_delaySumSq / (double)m_appRx - mean * mean;
        out["delay_std_s"] = std::sqrt(std::max(0.0, var));
    }
    else
    {
        out["delay_std_s"] = 0.0;
    }
    out["mean_hops"] = (m_appRx > 0) ? (double)m_hopSum / (double)m_appRx : 0.0;
    out["rx_bytes"] = (double)m_appRxBytes;
    out["forwards"] = (double)m_forwards;
    out["adversary_drops"] = (double)m_adversaryDrops;
    out["adversary_drops_large"] = (double)m_adversaryDropsLarge;
    out["energy_drops"] = (double)m_energyDrops;
    out["no_route_drops"] = (double)m_noRoute;
    out["control_packets"] = (double)m_controlPackets;
    out["control_bytes"] = (double)m_controlBytes;
    out["ctrl_rreq"] = (double)(m_controlByType.count(AREAURP_RREQ) ? m_controlByType.at(AREAURP_RREQ) : 0);
    out["ctrl_rrep"] = (double)(m_controlByType.count(AREAURP_RREP) ? m_controlByType.at(AREAURP_RREP) : 0);
    out["ctrl_rerr"] = (double)(m_controlByType.count(AREAURP_RERR) ? m_controlByType.at(AREAURP_RERR) : 0);
    out["ctrl_nid"] = (double)(m_controlByType.count(AREAURP_NID) ? m_controlByType.at(AREAURP_NID) : 0);
    out["ctrl_gid"] = (double)(m_controlByType.count(AREAURP_GID) ? m_controlByType.at(AREAURP_GID) : 0);
    out["ctrl_crev"] = (double)(m_controlByType.count(AREAURP_CREV) ? m_controlByType.at(AREAURP_CREV) : 0);
    out["watchdog_armed"] = (double)m_watchdogArmed;
    out["watchdog_confirmed"] = (double)m_watchdogConfirmed;
    out["watchdog_observation_rate"] =
        (m_watchdogArmed > 0) ? (double)m_watchdogConfirmed / (double)m_watchdogArmed : 0.0;
    out["local_repairs"] = (double)m_localRepairs;
    out["link_failures"] = (double)m_linkFailures;
    out["link_failures_data"] = (double)m_linkFailuresData;
    out["queued"] = (double)m_queued;
    out["dequeued"] = (double)m_dequeued;
    out["queue_overflow"] = (double)m_queueOverflow;
    out["queue_expired"] = (double)m_queueExpired;
    out["route_discoveries"] = (double)m_discoveries;
    out["route_discovery_failures"] = (double)m_discoveryFailures;
    out["dead_nodes"] = (double)m_dead;
    out["first_death_s"] = FirstDeath().GetSeconds();

    double tpr = 0.0;
    double fpr = 0.0;
    DetectionRates(2, tpr, fpr, false);
    out["detect_tpr"] = tpr;
    out["detect_fpr"] = fpr;
    DetectionRates(1, tpr, fpr, true);
    out["revoke_tpr"] = tpr;
    out["revoke_fpr"] = fpr;
    return out;
}

} // namespace arEaurp
} // namespace ns3
