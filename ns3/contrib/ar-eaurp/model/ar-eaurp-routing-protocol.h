/*
 * AR-EAURP -- a reactive, trust- and energy-aware routing protocol for ns-3.
 *
 * One class implements three protocols, selected by the Variant attribute, so
 * that all three run on exactly the same code path, topology, traffic and
 * radio and any difference between them is a difference of policy only:
 *
 *   VARIANT_AODV      hop-count routing. No trust, no energy gate, no
 *                     revocation: the baseline both source papers compare to.
 *   VARIANT_EAURP     base.pdf as specified. Routes are scored by
 *                     R_Score = a*T + b*E, relays below 20% battery are
 *                     excluded, trust comes from watchdog-observed forwarding
 *                     ratios exchanged in PT_NID, and a majority vote over
 *                     PT_GID revokes a node with PT_CREV.
 *   VARIANT_AR_EAURP  the advancement. Adds a GAN behaviour detector whose
 *                     contested verdict halves a node's trust weight, an LSTM
 *                     harvest forecast that lets routing use energy a node is
 *                     about to have, and a CMDP agent that picks the scoring
 *                     policy under a hard delivery-ratio floor.
 *
 * The same class also implements the three adversaries (Attack attribute), for
 * the same reason: an attacker is an ordinary node with a different forwarding
 * decision, not a different code path.
 *
 * WHAT IS REAL HERE. Route discovery is a real RREQ flood over real 802.11
 * frames with real contention and collisions; the watchdog is real promiscuous
 * overhearing, with all of its real failure modes; trust, votes and
 * revocations travel in real packets that cost real airtime and real energy.
 * Nothing in this protocol reads global state -- every decision a node makes
 * uses only what arrived at that node.
 */

#ifndef AR_EAURP_ROUTING_PROTOCOL_H
#define AR_EAURP_ROUTING_PROTOCOL_H

#include "ar-eaurp-neighbor.h"
#include "ar-eaurp-oracle.h"
#include "ar-eaurp-packet.h"
#include "ar-eaurp-rtable.h"

#include "ns3/ipv4-interface.h"
#include "ns3/ipv4-l3-protocol.h"
#include "ns3/ipv4-routing-protocol.h"
#include "ns3/node.h"
#include "ns3/random-variable-stream.h"
#include "ns3/socket.h"
#include "ns3/timer.h"
#include "ns3/wifi-mac.h"
#include "ns3/wifi-mpdu.h"

#include <deque>
#include <map>
#include <set>
#include <vector>

namespace ns3
{

namespace energy
{
class EnergySource;
}

namespace arEaurp
{

/// A packet waiting for a route to be discovered.
struct QueueEntry
{
    Ptr<const Packet> packet;
    Ipv4Header header;
    Ipv4RoutingProtocol::UnicastForwardCallback ucb;
    Ipv4RoutingProtocol::ErrorCallback ecb;
    Time expire;
};

/// Per-destination bookkeeping for the CMDP agent's delayed reward.
struct PendingDecision
{
    Vec state;
    uint32_t action;
    Time taken;
};

class RoutingProtocol : public Ipv4RoutingProtocol
{
  public:
    static TypeId GetTypeId();
    static const uint32_t AR_EAURP_PORT;

    enum Variant
    {
        VARIANT_AODV = 0,
        VARIANT_EAURP = 1,
        VARIANT_AR_EAURP = 2,
    };

    enum Attack
    {
        ATTACK_NONE = 0,
        ATTACK_BLACKHOLE = 1,
        ATTACK_GRAYHOLE = 2,
        ATTACK_TRUST_POISONING = 3,
    };

    RoutingProtocol();
    ~RoutingProtocol() override;

    // -- Ipv4RoutingProtocol ------------------------------------------------
    Ptr<Ipv4Route> RouteOutput(Ptr<Packet> p,
                               const Ipv4Header& header,
                               Ptr<NetDevice> oif,
                               Socket::SocketErrno& sockerr) override;
    bool RouteInput(Ptr<const Packet> p,
                    const Ipv4Header& header,
                    Ptr<const NetDevice> idev,
                    const UnicastForwardCallback& ucb,
                    const MulticastForwardCallback& mcb,
                    const LocalDeliverCallback& lcb,
                    const ErrorCallback& ecb) override;
    void NotifyInterfaceUp(uint32_t interface) override;
    void NotifyInterfaceDown(uint32_t interface) override;
    void NotifyAddAddress(uint32_t interface, Ipv4InterfaceAddress address) override;
    void NotifyRemoveAddress(uint32_t interface, Ipv4InterfaceAddress address) override;
    void SetIpv4(Ptr<Ipv4> ipv4) override;
    void PrintRoutingTable(Ptr<OutputStreamWrapper> stream,
                           Time::Unit unit = Time::S) const override;

    int64_t AssignStreams(int64_t stream);

    // -- configuration -------------------------------------------------------
    void SetAttack(Attack a)
    {
        m_attack = a;
    }

    Attack GetAttack() const
    {
        return m_attack;
    }

    void SetVariant(Variant v)
    {
        m_variant = v;
    }

    Variant GetVariant() const
    {
        return m_variant;
    }

    /// Called by the traffic application when a flow's packet is (not) acked.
    void NotifyDelivery(Ipv4Address dst, bool delivered, uint32_t hops);

    /// This node's view of its own battery, as a fraction of its initial charge.
    double EnergyFraction() const;

    /// Running delivery ratio over the node's recent acknowledged traffic.
    double WindowPdr() const;

    const NeighborTrust& Neighbors() const
    {
        return m_neighbors;
    }

    /// Neighbours this node currently considers usable for routing.
    uint32_t UsableNeighbours() const;
    double MeanLinkQuality() const;

  protected:
    void DoInitialize() override;
    void DoDispose() override;

  private:
    // -- start-up -------------------------------------------------------------
    void Start();
    Ptr<Socket> CreateSocket(Ipv4InterfaceAddress iface, bool subnetBroadcast);

    // -- route discovery -------------------------------------------------------
    void SendRequest(Ipv4Address dst);
    void ScheduleRreqRetry(Ipv4Address dst, uint8_t ttl);
    void RouteRequestTimerExpire(Ipv4Address dst);
    void RecvArEaurp(Ptr<Socket> socket);
    void RecvRequest(Ptr<Packet> p, Ipv4Address receiver, Ipv4Address src);
    void RecvReply(Ptr<Packet> p, Ipv4Address myAddress, Ipv4Address src);
    void RecvError(Ptr<Packet> p, Ipv4Address src);
    void SendReply(const RreqHeader& rreqHeader, const RoutingTableEntry& toOrigin);
    void SendReplyByIntermediateNode(const RoutingTableEntry& toDst,
                                     const RoutingTableEntry& toOrigin,
                                     const RreqHeader& rreqHeader,
                                     uint32_t costSoFar);
    void SendFakeReply(const RreqHeader& rreqHeader, Ipv4Address src, Ipv4Address receiver);
    void SendRerrWhenBreaksLinkToNextHop(Ipv4Address nextHop);
    void SendRerrMessage(Ptr<Packet> packet, std::vector<Ipv4Address> precursors);
    void SendPacketFromQueue(Ipv4Address dst, Ptr<Ipv4Route> route);
    void SendTo(Ptr<Socket> socket, Ptr<Packet> packet, Ipv4Address destination);
    void DeferredRouteOutput(Ptr<const Packet> p,
                             const Ipv4Header& header,
                             UnicastForwardCallback ucb,
                             ErrorCallback ecb);
    Ptr<Ipv4Route> LoopbackRoute(const Ipv4Header& header, Ptr<NetDevice> oif) const;
    bool Forwarding(Ptr<const Packet> p,
                    const Ipv4Header& header,
                    const UnicastForwardCallback& ucb,
                    const ErrorCallback& ecb);
    void UpdateRouteLifeTime(Ipv4Address addr, Time lifetime);
    void UpdateRouteToNeighbor(Ipv4Address sender, Ipv4Address receiver);
    bool IsMyOwnAddress(Ipv4Address src);
    Ipv4Address MainAddress() const;

    // -- trust plane -----------------------------------------------------------
    void SendNid();
    void SendGid();
    void RecvNid(Ptr<Packet> p, Ipv4Address src);
    void RecvGid(Ptr<Packet> p, Ipv4Address src, Ipv4Address receiver);
    void RecvCrev(Ptr<Packet> p, Ipv4Address src, Ipv4Address receiver);
    void RunConsensus();
    void ApplyRevocation(Ipv4Address subject, uint8_t evidence, bool originator);
    void SweepWatchdogs();
    void PromiscRx(Ptr<NetDevice> device,
                   Ptr<const Packet> packet,
                   uint16_t protocol,
                   const Address& from,
                   const Address& to,
                   NetDevice::PacketType type);
    /**
     * \brief Identify a relayed packet from the frame carrying it.
     *
     * Both sides of a watchdog observation have to compute the same value from
     * the same bytes, so the digest is always taken from a frame that starts at
     * the IP header: the transmitter reads it off its own outgoing frame and
     * the observer off the frame it overhears. (Taking it at RouteOutput
     * instead does not work -- a UDP socket asks for a route *before* it adds
     * its header, so the transmitter would be hashing eight bytes fewer than
     * the observer and no observation would ever match.)
     */
    static uint64_t DigestFromIpFrame(Ptr<const Packet> ipFrame, bool& isControl);

    /// Our own outgoing frame: arm a watchdog entry if we are relaying it.
    void NotifyPhyTx(Ptr<const Packet> frame, double txPowerW);

    /// Our own MAC gave up on a frame: the link to that neighbour is broken.
    void NotifyTxError(WifiMacDropReason reason, Ptr<const WifiMpdu> mpdu);
    bool LookupIpFromMac(Mac48Address mac, Ipv4Address& addr) const;

    /**
     * \brief Install a neighbour's L2/L3 binding straight into the ARP cache.
     *
     * Every PT_NID beacon already proves which MAC address owns which IP, so
     * resolving it again with an ARP exchange is pure waste -- and worse than
     * waste: an ARP request is an unacknowledged broadcast, so in a busy
     * network it is exactly the frame most likely to be lost, and losing it
     * kills the route reply that was waiting behind it. Learning bindings from
     * traffic already seen is what real ad-hoc stacks do.
     */
    void SeedArpCache(Ipv4Address addr, Mac48Address mac);

    // -- AR-EAURP ---------------------------------------------------------------
    void RunDetection();
    void SampleHarvest();
    Vec BuildState() const;
    double PredictedSurplus() const;

    // -- scoring ---------------------------------------------------------------
    /// Cost, in milli-units, of using `neighbour` as a hop under `policy`.
    uint32_t HopCostMilli(Ipv4Address neighbour, uint8_t policy) const;
    void ScoreCoefficients(double& a, double& b) const;
    bool EnergyGateOpen() const;

    // -- adversary --------------------------------------------------------------
    bool ForwardsData(uint32_t payloadSize);
    double PublishedTrust(Ipv4Address subject, double measured) const;

    // -- state ------------------------------------------------------------------
    Ptr<Ipv4> m_ipv4;
    std::map<Ptr<Socket>, Ipv4InterfaceAddress> m_socketAddresses;
    std::map<Ptr<Socket>, Ipv4InterfaceAddress> m_socketSubnetBroadcastAddresses;
    Ptr<NetDevice> m_lo;
    RoutingTable m_routingTable;
    NeighborTrust m_neighbors;
    std::vector<QueueEntry> m_queue;

    Variant m_variant;
    Attack m_attack;

    uint32_t m_requestId;
    uint32_t m_seqNo;
    std::map<std::pair<Ipv4Address, uint32_t>, uint32_t> m_rreqSeen; //!< (origin,id) -> best cost
    std::map<std::pair<Ipv4Address, uint32_t>, uint32_t> m_rreqForwards;
    std::map<std::pair<Ipv4Address, uint32_t>, Time> m_rreqSeenTime;
    uint32_t m_rreqThisSecond;
    Time m_rreqWindowStart;
    std::map<Ipv4Address, uint32_t> m_rreqRetries;
    std::map<Ipv4Address, EventId> m_rreqTimers;
    std::map<Ipv4Address, uint8_t> m_policyInUse;   //!< action chosen per destination
    std::map<Ipv4Address, Ipv4Address> m_lastNextHop;
    std::map<Ipv4Address, PendingDecision> m_pending;
    std::map<Ipv4Address, std::set<Ipv4Address>> m_crevHeard; //!< subject -> issuers
    std::set<std::pair<Ipv4Address, uint32_t>> m_floodSeen;

    // timers
    Timer m_nidTimer;
    Timer m_gidTimer;
    Timer m_detectTimer;
    Timer m_watchdogTimer;
    Timer m_harvestTimer;
    uint32_t m_gidSeq;

    // parameters
    Time m_nidInterval;
    Time m_gidInterval;
    Time m_detectInterval;
    Time m_watchdogTimeout;
    Time m_activeRouteTimeout;
    Time m_pathDiscoveryTime;
    Time m_rreqTimeout;
    Time m_queueTimeout;
    Time m_contestedTtl;
    uint32_t m_rreqRetriesMax;
    Time m_nodeTraversalTime;
    uint32_t m_ttlStart;
    uint32_t m_ttlIncrement;
    uint32_t m_rreqRateLimit;      //!< originated route requests per second
    uint32_t m_rreqMaxForwards;    //!< rebroadcasts allowed per request
    double m_rreqImprovement;      //!< relative cost gain needed to rebroadcast
    uint8_t m_gidTtl;
    uint32_t m_netDiameter;
    uint32_t m_maxQueueLen;
    bool m_localRepair;
    bool m_floodSuppression;
    uint32_t m_minAdditionalCoverage;
    double m_linkQualityThreshold;
    double m_linkQualityWeight;
    double m_linkQualityInitial;
    double m_trustThreshold;
    double m_trustSmoothing;
    uint32_t m_minObservations;
    double m_consensusFraction;
    uint32_t m_minAccusers;
    double m_energyThreshold;
    double m_hopPenalty;
    double m_contestedWeight;
    double m_grayholeDropProb;
    uint32_t m_largePacketThreshold;
    bool m_energyExcuse;
    bool m_energyGate;

    // energy / harvest
    Ptr<energy::EnergySource> m_energySource;
    double m_initialEnergy;
    std::deque<std::pair<double, double>> m_harvestHistory; //!< (watts, day phase)
    double m_lastSurplus;
    bool m_reportedDeath;

    // delivery feedback
    std::deque<bool> m_deliveryWindow;
    uint64_t m_delivered;
    uint64_t m_attempted;

    Ptr<UniformRandomVariable> m_uniform;
};

} // namespace arEaurp
} // namespace ns3

#endif /* AR_EAURP_ROUTING_PROTOCOL_H */
