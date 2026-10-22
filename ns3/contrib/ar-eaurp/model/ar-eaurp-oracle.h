/*
 * Measurement and model registry.
 *
 * Two jobs, deliberately kept apart from the protocol itself:
 *
 * 1. MEASUREMENT. Ground truth about which nodes are hostile, and the counters
 *    a protocol cannot legitimately see (who really dropped what). Nothing in
 *    the routing code ever reads the ground truth -- it is only used to score
 *    detection after the fact. Detection metrics computed any other way would
 *    be circular.
 *
 * 2. FLEET MODELS. The GAN detector, the energy forecaster and the CMDP agent
 *    are trained once, at commissioning, and shared by every node (parameter
 *    sharing). The registry owns them so that a node can run inference without
 *    every node paying to train its own copy.
 */

#ifndef AR_EAURP_ORACLE_H
#define AR_EAURP_ORACLE_H

#include "ar-eaurp-cmdp.h"
#include "ar-eaurp-detector.h"
#include "ar-eaurp-forecaster.h"

#include "ns3/ipv4-address.h"
#include "ns3/nstime.h"

#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>

namespace ns3
{
namespace arEaurp
{

/// How a node behaves when asked to relay.
enum AttackRole
{
    ROLE_HONEST = 0,
    ROLE_BLACKHOLE = 1,
    ROLE_GRAYHOLE = 2,
    ROLE_SLANDERER = 4,
};

/// The phase a run is in; the detector only collects training data in COMMISSIONING.
enum RunPhase
{
    PHASE_COMMISSIONING = 0,
    PHASE_EVALUATION = 1,
};

class Oracle
{
  public:
    static Oracle& Get();

    void Reset(uint32_t nNodes);

    // -- identity -----------------------------------------------------------
    void Register(uint32_t nodeId, Ipv4Address addr, uint32_t role);
    uint32_t NodeIdOf(Ipv4Address addr) const;
    uint32_t RoleOf(Ipv4Address addr) const;
    bool IsMalicious(Ipv4Address addr) const;

    uint32_t NodeCount() const
    {
        return m_nNodes;
    }

    // -- phase --------------------------------------------------------------
    void SetPhase(RunPhase p)
    {
        m_phase = p;
    }

    RunPhase Phase() const
    {
        return m_phase;
    }

    /// Statistics are only accumulated after this time (warm-up is excluded).
    void SetMeasurementStart(Time t)
    {
        m_measurementStart = t;
    }
    void SetMeasurementEnd(Time t) { m_measurementEnd = t; }

    bool Measuring() const;

    // -- data plane counters -------------------------------------------------
    void CountAppTx(uint32_t bytes);
    void CountAppRx(uint32_t bytes, Time delay, uint32_t hops);
    void CountAppFeedback(bool delivered, Time sent);
    void CountForward();
    void CountAdversaryDrop(uint32_t bytes, bool large);
    void CountEnergyDrop();
    void CountNoRoute();
    void CountControl(uint32_t type, uint32_t bytes);
    void CountWatchdogArmed();
    void CountWatchdogConfirmed();
    void CountRouteDiscovery(bool succeeded);
    void CountQueued();
    void CountDequeued();
    void CountQueueDrop(bool overflow);
    void CountLinkFailure(bool dataFrame);
    void CountLocalRepair();
    void CountCryptoTx(uint32_t overhead);
    void CountCryptoFailure();

    // -- detection accounting ------------------------------------------------
    /// Store one (anomaly score, ground truth) pair for detector evaluation.
    void RecordDetectorScore(double score, bool malicious);

    /// Area under the ROC curve of the recorded scores; 0.5 means no better
    /// than guessing.
    double DetectorAuc() const;

    void ReportContested(Ipv4Address observer, Ipv4Address subject);
    void ReportRevoked(Ipv4Address observer, Ipv4Address subject);
    uint32_t HonestWitnesses(Ipv4Address subject, bool revoked) const;

    /// Fraction of malicious nodes flagged by at least minWitnesses honest nodes.
    void DetectionRates(uint32_t minWitnesses,
                        double& truePositiveRate,
                        double& falsePositiveRate,
                        bool useRevocations) const;

    // -- energy --------------------------------------------------------------
    void ReportNodeDeath(uint32_t nodeId, Time when);
    Time FirstDeath() const;
    uint32_t DeadNodes() const;

    // -- fleet models ---------------------------------------------------------
    GanAnomalyDetector* Detector()
    {
        return m_detector.get();
    }

    EnergyForecaster* Forecaster()
    {
        return m_forecaster.get();
    }

    CmdpAgent* Agent()
    {
        return m_agent.get();
    }

    void CreateModels(uint32_t seed);
    void ClearModels();

    // -- report ---------------------------------------------------------------
    std::map<std::string, double> Summary() const;

    uint64_t AppTx() const
    {
        return m_appTx;
    }

    uint64_t AppRx() const
    {
        return m_appRx;
    }
    double MeanDelayMs() const
    {
        return m_appRx ? 1000.0 * m_delaySum / static_cast<double>(m_appRx) : 0.0;
    }

  private:
    Oracle() = default;

    uint32_t m_nNodes{0};
    RunPhase m_phase{PHASE_EVALUATION};
    Time m_measurementStart{Seconds(0)};
    Time m_measurementEnd{Time::Max()};

    std::map<Ipv4Address, uint32_t> m_ipToNode;
    std::vector<uint32_t> m_role;
    std::vector<Ipv4Address> m_addr;

    uint64_t m_appTx{0};
    uint64_t m_appRx{0};
    uint64_t m_feedbackSuccess{0};
    uint64_t m_feedbackTimeout{0};
    uint64_t m_appTxBytes{0};
    uint64_t m_appRxBytes{0};
    double m_delaySum{0.0};
    double m_delaySumSq{0.0};
    uint64_t m_hopSum{0};
    uint64_t m_forwards{0};
    uint64_t m_adversaryDrops{0};
    uint64_t m_adversaryDropsLarge{0};
    uint64_t m_energyDrops{0};
    uint64_t m_noRoute{0};
    uint64_t m_controlPackets{0};
    uint64_t m_controlBytes{0};
    std::map<uint32_t, uint64_t> m_controlByType;
    uint64_t m_watchdogArmed{0};
    uint64_t m_watchdogConfirmed{0};
    uint64_t m_discoveries{0};
    uint64_t m_discoveryFailures{0};
    uint64_t m_queued{0};
    uint64_t m_dequeued{0};
    uint64_t m_queueOverflow{0};
    uint64_t m_queueExpired{0};
    uint64_t m_linkFailures{0};
    uint64_t m_linkFailuresData{0};
    uint64_t m_localRepairs{0};
    uint64_t m_cryptoPackets{0};
    uint64_t m_cryptoBytes{0};
    uint64_t m_cryptoFailures{0};

    // observer -> subjects it flagged
    std::map<Ipv4Address, std::set<Ipv4Address>> m_contested;
    std::map<Ipv4Address, std::set<Ipv4Address>> m_revocations;

    std::vector<std::pair<double, bool>> m_detectorScores;
    std::vector<Time> m_death;
    uint32_t m_dead{0};

    std::unique_ptr<GanAnomalyDetector> m_detector;
    std::unique_ptr<EnergyForecaster> m_forecaster;
    std::unique_ptr<CmdpAgent> m_agent;
};

} // namespace arEaurp
} // namespace ns3

#endif /* AR_EAURP_ORACLE_H */
