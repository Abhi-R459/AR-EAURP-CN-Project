/*
 * Neighbour, watchdog and trust state for one AR-EAURP node.
 *
 * WATCHDOG (base.pdf 3.7). When this node hands a packet to neighbour X for
 * relaying, it arms a watchdog entry and then listens in promiscuous mode for X
 * to transmit that same packet onwards. What is measured is therefore what a
 * real watchdog measures -- including its real failure modes: a collision at the
 * observer, X moving out of range, or the relay happening while the observer's
 * radio is busy all look like a drop. That noise is exactly why base.pdf needs
 * a majority vote and an energy excuse before it revokes anybody.
 *
 * TRUST. PFR = forwarded / requested, smoothed as T <- 0.7*T + 0.3*PFR.
 *
 * FEATURES (AR-EAURP step 1). The same counters are also kept split by packet
 * size, which is what makes a selective-forwarding gray-hole visible: its
 * scalar PFR sits comfortably above the 0.6 revocation threshold while its
 * large-packet drop rate does not.
 */

#ifndef AR_EAURP_NEIGHBOR_H
#define AR_EAURP_NEIGHBOR_H

#include "ns3/callback.h"
#include "ns3/ipv4-address.h"
#include "ns3/mac48-address.h"
#include "ns3/nstime.h"
#include "ns3/simulator.h"

#include <map>
#include <set>
#include <vector>

namespace ns3
{
namespace arEaurp
{

/// Number of behaviour features fed to the anomaly detector.
constexpr uint32_t kFeatureDim = 8;

/// One watched neighbour.
struct NeighborEntry
{
    Ipv4Address addr;
    Mac48Address mac;
    Time expire{Seconds(0)};      //!< neighbour is forgotten after this
    double energyFraction{1.0};   //!< last value advertised in PT_NID
    double surplus{0.0};          //!< last forecast harvest headroom advertised
    double trust{1.0};            //!< smoothed PFR (base.pdf 3.7)

    // Watchdog counters, cumulative over the run.
    double requested{0.0};
    double observed{0.0};
    double requestedLarge{0.0};
    double observedLarge{0.0};
    double requestedSmall{0.0};
    double observedSmall{0.0};
    double latencySum{0.0};
    double latencySumSq{0.0};
    double latencyCount{0.0};

    // Snapshot at the last detection pass, for windowed (delta) features.
    double prevRequested{0.0};
    double prevObserved{0.0};
    double prevRequestedLarge{0.0};
    double prevObservedLarge{0.0};
    double prevRequestedSmall{0.0};
    double prevObservedSmall{0.0};

    // Link sensing.
    double quality{0.0};          //!< smoothed beacon reception rate in [0, 1]
    bool usable{false};           //!< result of the hysteresis test below
    uint32_t beaconsThisWindow{0};
    Time heardMeUntil{Seconds(0)}; //!< the neighbour listed us in its beacon
    std::vector<Ipv4Address> advertised; //!< the neighbours it says it hears

    // AR-EAURP detector state.
    bool contested{false};
    Time contestedUntil{Seconds(0)};
    double anomalyScore{0.0};

    double Pfr() const
    {
        return (requested > 0.0) ? (observed / requested) : 1.0;
    }

    double WindowPfr() const
    {
        const double d = requested - prevRequested;
        return (d > 0.0) ? ((observed - prevObserved) / d) : Pfr();
    }
};

/// A trust opinion published by another node in a PT_GID message.
struct Opinion
{
    double trust{1.0};
    Time received{Seconds(0)};
};

/**
 * \brief Neighbour table, watchdog bookkeeping, trust and consensus for one node.
 */
class NeighborTrust
{
  public:
    NeighborTrust();

    void SetParameters(Time neighbourLifetime,
                       Time watchdogTimeout,
                       double smoothing,
                       double trustThreshold,
                       uint32_t minObservations,
                       uint32_t largePacketThreshold);

    /// Called when a PT_NID (or any packet from a neighbour) is received.
    void Refresh(Ipv4Address addr, Mac48Address mac, double energyFraction, double surplus);

    /// A beacon arrived from this neighbour; heardMe says it listed us in it.
    void NoteBeacon(Ipv4Address addr, bool heardMe, Time symmetryLifetime);

    /// Record the neighbour list a neighbour advertised in its beacon.
    void NoteAdvertisedNeighbours(Ipv4Address addr, const std::vector<Ipv4Address>& links);

    /**
     * \brief How many of our own neighbours the given node does not already
     * reach.
     *
     * Rebroadcasting a flood that covers nobody new is pure interference, and
     * in a dense network most rebroadcasts are exactly that. Because PT_NID
     * already carries each node's neighbour list, every node can work out its
     * own additional coverage for free and stay quiet when it has none. This is
     * the standard neighbour-knowledge (self-pruning) broadcast rule.
     */
    uint32_t AdditionalCoverage(Ipv4Address previousHop, double qualityThreshold) const;

    /**
     * \brief Fold this window's beacon arrivals into each link's quality and
     * re-evaluate whether the link is usable.
     *
     * With hysteresis: a link has to be clearly good to be adopted and clearly
     * bad to be dropped. A single threshold makes links flap in and out of the
     * routing table on ordinary fading, and each flap costs a route discovery.
     * OLSR's link hysteresis exists for the same reason.
     */
    void TickLinkQuality(double weight, double initialQuality, double high, double low);

    /**
     * \brief Is this neighbour a link worth routing over?
     *
     * Both directions have to work and the link has to be reliable, not merely
     * to have delivered one lucky frame. Route discovery floods every link
     * there is, so without this test a path is assembled out of exactly those
     * marginal links that happened to catch a good fade -- and then every data
     * packet sent along it is lost.
     */
    bool IsUsableLink(Ipv4Address addr, double qualityThreshold) const;

    double GetQuality(Ipv4Address addr) const;

    bool IsNeighbor(Ipv4Address addr);
    void Purge();

    /// Arm a watchdog entry: we just asked nextHop to relay this packet.
    void ArmWatchdog(Ipv4Address nextHop, uint64_t digest, uint32_t payloadSize);

    /// A promiscuously overheard transmission matched an armed entry.
    bool ConfirmWatchdog(Mac48Address from, uint64_t digest);

    /// Sweep expired watchdog entries; each one counts as a drop by the relay.
    void ExpireWatchdogs();

    /**
     * \brief Withdraw a watchdog entry whose frame never reached the relay.
     *
     * When our own MAC gives up after its retry limit we know the neighbour
     * never received the packet, so it cannot have dropped it. Counting that
     * as a drop would blame a relay for our own broken link -- the single
     * largest source of false accusations in a watchdog scheme.
     */
    bool CancelWatchdog(Ipv4Address nextHop, uint64_t digest);

    /// T <- smoothing*T + (1-smoothing)*PFR over the nodes we have watched.
    void RefreshTrust();

    double GetTrust(Ipv4Address addr) const;
    double GetEnergyFraction(Ipv4Address addr) const;
    double GetSurplus(Ipv4Address addr) const;
    bool IsContested(Ipv4Address addr) const;
    void SetContested(Ipv4Address addr, Time until, double score);
    void ExpireContested();

    /// Opinions this node publishes in its PT_GID (honest version).
    std::vector<std::pair<Ipv4Address, double>> BuildOpinions() const;

    /// Record an opinion heard from another node.
    void AddOpinion(Ipv4Address observer, Ipv4Address subject, double trust);
    void PurgeOpinions(Time maxAge);

    /**
     * \brief Majority-vote verdict (base.pdf 3.7).
     *
     * A subject is condemned when at least max(minAccusers, ceil(fraction * n))
     * of the nodes that published an opinion about it published a value below
     * the revocation threshold -- unless its advertised battery is at or below
     * the energy threshold, in which case base.pdf's energy excuse applies and
     * the node is presumed flat rather than malicious.
     */
    std::vector<Ipv4Address> Consensus(double fraction,
                                       uint32_t minAccusers,
                                       bool energyExcuse,
                                       double energyThresholdFraction) const;

    void Revoke(Ipv4Address addr);
    bool IsRevoked(Ipv4Address addr) const;

    const std::set<Ipv4Address>& Revoked() const
    {
        return m_revoked;
    }

    /// Behaviour feature vectors, one per subject watched often enough.
    void ExtractFeatures(std::vector<Ipv4Address>& subjects,
                         std::vector<std::vector<double>>& features,
                         bool updateSnapshot);

    /// Bind a MAC address seen on the air to the IP that owns it.
    void BindMac(Mac48Address mac, Ipv4Address addr);
    bool LookupMac(Mac48Address mac, Ipv4Address& addr) const;

    const std::map<Ipv4Address, NeighborEntry>& Table() const
    {
        return m_table;
    }

    uint64_t watchUnknownMac{0};
    uint64_t watchNoPending{0};
    uint64_t watchDigestMiss{0};

    uint32_t WatchdogPending() const
    {
        return (uint32_t)m_pending.size();
    }

    uint32_t LargePacketThreshold() const
    {
        return m_largePacketThreshold;
    }

  private:
    struct PendingWatch
    {
        Ipv4Address nextHop;
        uint64_t digest;
        uint32_t size;
        Time armed;
        Time deadline;
    };

    /// |my published opinion - median of everyone else's| for one subject.
    double Disagreement(Ipv4Address subject) const;

    std::map<Ipv4Address, NeighborEntry> m_table;
    std::map<Mac48Address, Ipv4Address> m_macToIp;
    std::vector<PendingWatch> m_pending;
    std::map<Ipv4Address, std::map<Ipv4Address, Opinion>> m_opinions; // subject -> observer
    std::set<Ipv4Address> m_revoked;

    Time m_neighbourLifetime;
    Time m_watchdogTimeout;
    double m_smoothing;
    double m_trustThreshold;
    uint32_t m_minObservations;
    uint32_t m_largePacketThreshold;
};

} // namespace arEaurp
} // namespace ns3

#endif /* AR_EAURP_NEIGHBOR_H */
