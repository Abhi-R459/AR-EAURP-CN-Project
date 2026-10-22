#include "ar-eaurp-routing-protocol.h"

#include "ns3/adhoc-wifi-mac.h"
#include "ns3/boolean.h"
#include "ns3/double.h"
#include "ns3/energy-source-container.h"
#include "ns3/energy-harvester-container.h"
#include "ns3/enum.h"
#include "ns3/arp-cache.h"
#include "ns3/arp-l3-protocol.h"
#include "ns3/inet-socket-address.h"
#include "ns3/llc-snap-header.h"
#include "ns3/log.h"
#include "ns3/mobility-model.h"
#include "ns3/pointer.h"
#include "ns3/string.h"
#include "ns3/trace-source-accessor.h"
#include "ns3/udp-header.h"
#include "ns3/udp-l4-protocol.h"
#include "ns3/udp-socket-factory.h"
#include "ns3/uinteger.h"
#include "ns3/wifi-mac-header.h"
#include "ns3/wifi-mac-trailer.h"
#include "ns3/wifi-net-device.h"
#include "ns3/wifi-phy.h"

#include "solar-energy-harvester.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("ArEaurpRoutingProtocol");

namespace arEaurp
{

NS_OBJECT_ENSURE_REGISTERED(RoutingProtocol);

const uint32_t RoutingProtocol::AR_EAURP_PORT = 6540;

/**
 * \brief Tag marking a packet that came back from loopback because no route
 * existed yet, exactly as AODV does it: the packet has to be fully formed
 * before route discovery can be started for it.
 */
class DeferredRouteOutputTag : public Tag
{
  public:
    DeferredRouteOutputTag(int32_t o = -1)
        : Tag(),
          m_oif(o)
    {
    }

    static TypeId GetTypeId()
    {
        static TypeId tid = TypeId("ns3::arEaurp::DeferredRouteOutputTag")
                                .SetParent<Tag>()
                                .SetGroupName("ArEaurp")
                                .AddConstructor<DeferredRouteOutputTag>();
        return tid;
    }

    TypeId GetInstanceTypeId() const override
    {
        return GetTypeId();
    }

    int32_t GetInterface() const
    {
        return m_oif;
    }

    void SetInterface(int32_t oif)
    {
        m_oif = oif;
    }

    uint32_t GetSerializedSize() const override
    {
        return sizeof(int32_t);
    }

    void Serialize(TagBuffer i) const override
    {
        i.WriteU32(m_oif);
    }

    void Deserialize(TagBuffer i) override
    {
        m_oif = i.ReadU32();
    }

    void Print(std::ostream& os) const override
    {
        os << "DeferredRouteOutputTag: output interface = " << m_oif;
    }

  private:
    int32_t m_oif;
};

NS_OBJECT_ENSURE_REGISTERED(DeferredRouteOutputTag);

// ---------------------------------------------------------------------------

RoutingProtocol::RoutingProtocol()
    : m_routingTable(Seconds(5)),
      m_variant(VARIANT_AR_EAURP),
      m_attack(ATTACK_NONE),
      m_requestId(0),
      m_seqNo(0),
      m_rreqThisSecond(0),
      m_rreqWindowStart(Seconds(0)),
      m_nidTimer(Timer::CANCEL_ON_DESTROY),
      m_gidTimer(Timer::CANCEL_ON_DESTROY),
      m_detectTimer(Timer::CANCEL_ON_DESTROY),
      m_watchdogTimer(Timer::CANCEL_ON_DESTROY),
      m_harvestTimer(Timer::CANCEL_ON_DESTROY),
      m_gidSeq(0),
      m_nidInterval(Seconds(1)),
      m_gidInterval(Seconds(10)),
      m_detectInterval(Seconds(20)),
      m_watchdogTimeout(Seconds(1)),
      m_activeRouteTimeout(Seconds(20)),
      m_pathDiscoveryTime(Seconds(3)),
      m_rreqTimeout(Seconds(2.5)),
      m_queueTimeout(Seconds(15)),
      m_contestedTtl(Seconds(60)),
      m_rreqRetriesMax(3),
      m_nodeTraversalTime(MilliSeconds(150)),
      m_ttlStart(3),
      m_ttlIncrement(3),
      m_rreqRateLimit(5),
      m_rreqMaxForwards(1),
      m_rreqImprovement(0.05),
      m_gidTtl(1),
      m_netDiameter(10),
      m_maxQueueLen(64),
      m_detectMinWindow(6),
      m_localRepair(true),
      m_floodSuppression(true),
      m_minAdditionalCoverage(1),
      m_linkQualityThreshold(0.6),
      m_linkQualityWeight(0.4),
      m_linkQualityInitial(0.7),
      m_trustThreshold(0.6),
      m_trustSmoothing(0.7),
      m_minObservations(5),
      m_consensusFraction(0.5),
      m_minAccusers(2),
      m_energyThreshold(0.2),
      m_hopPenalty(0.35),
      m_contestedWeight(0.5),
      m_grayholeDropProb(0.25),
      m_largePacketThreshold(700),
      m_energyExcuse(true),
      m_energyGate(true),
      m_initialEnergy(0.0),
      m_lastSurplus(0.0),
      m_reportedDeath(false),
      m_delivered(0),
      m_attempted(0)
{
    m_uniform = CreateObject<UniformRandomVariable>();
}

RoutingProtocol::~RoutingProtocol()
{
}

TypeId
RoutingProtocol::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::arEaurp::RoutingProtocol")
            .SetParent<Ipv4RoutingProtocol>()
            .SetGroupName("ArEaurp")
            .AddConstructor<RoutingProtocol>()
            .AddAttribute("Variant",
                          "Which protocol this node runs.",
                          EnumValue(VARIANT_AR_EAURP),
                          MakeEnumAccessor<Variant>(&RoutingProtocol::m_variant),
                          MakeEnumChecker(VARIANT_AODV,
                                          "AODV",
                                          VARIANT_EAURP,
                                          "EAURP",
                                          VARIANT_AR_EAURP,
                                          "AR-EAURP",
                                          VARIANT_DRL_PAPER,
                                          "DRL-paper",
                                          VARIANT_DRL_SENIOR,
                                          "DRL-senior"))
            .AddAttribute("UseGan", "Enable anomaly detection.", BooleanValue(true),
                          MakeBooleanAccessor(&RoutingProtocol::m_useGan), MakeBooleanChecker())
            .AddAttribute("UseLstm", "Enable learned harvest forecasting.", BooleanValue(true),
                          MakeBooleanAccessor(&RoutingProtocol::m_useLstm), MakeBooleanChecker())
            .AddAttribute("UseCmdp", "Enable constrained route selection.", BooleanValue(true),
                          MakeBooleanAccessor(&RoutingProtocol::m_useCmdp), MakeBooleanChecker())
            .AddAttribute("Attack",
                          "Adversarial behaviour of this node.",
                          EnumValue(ATTACK_NONE),
                          MakeEnumAccessor<Attack>(&RoutingProtocol::m_attack),
                          MakeEnumChecker(ATTACK_NONE,
                                          "none",
                                          ATTACK_BLACKHOLE,
                                          "blackhole",
                                          ATTACK_GRAYHOLE,
                                          "grayhole",
                                          ATTACK_TRUST_POISONING,
                                          "trust_poisoning"))
            .AddAttribute("NidInterval",
                          // One second. Link sensing needs two beacon rounds to
                          // confirm a link works both ways, and at 20 m/s a
                          // link can be gone inside fifteen; a slow beacon
                          // spends most of a link's life deciding whether to
                          // trust it. This is the same order as OLSR's HELLO.
                          "Period of the PT_NID neighbour / trust beacon.",
                          TimeValue(Seconds(1)),
                          MakeTimeAccessor(&RoutingProtocol::m_nidInterval),
                          MakeTimeChecker())
            .AddAttribute("GidInterval",
                          "Period of the PT_GID consensus round.",
                          TimeValue(Seconds(10)),
                          MakeTimeAccessor(&RoutingProtocol::m_gidInterval),
                          MakeTimeChecker())
            .AddAttribute("DetectInterval",
                          "Period of the AR-EAURP anomaly-detection pass.",
                          TimeValue(Seconds(20)),
                          MakeTimeAccessor(&RoutingProtocol::m_detectInterval),
                          MakeTimeChecker())
            .AddAttribute("WatchdogTimeout",
                          "How long the watchdog waits to overhear a relay.",
                          TimeValue(Seconds(1)),
                          MakeTimeAccessor(&RoutingProtocol::m_watchdogTimeout),
                          MakeTimeChecker())
            .AddAttribute("ActiveRouteTimeout",
                          "Lifetime of an active route entry.",
                          TimeValue(Seconds(20)),
                          MakeTimeAccessor(&RoutingProtocol::m_activeRouteTimeout),
                          MakeTimeChecker())
            .AddAttribute("RreqTimeout",
                          // A reply has to travel the whole path back, and every
                          // first hop of it pays for an ARP resolution. Measured
                          // on this scenario that is ~200 ms per hop, so a
                          // one-second timeout gives up while the reply is still
                          // in flight and the retry floods the network again.
                          "How long to wait for a route reply before retrying.",
                          TimeValue(Seconds(2.5)),
                          MakeTimeAccessor(&RoutingProtocol::m_rreqTimeout),
                          MakeTimeChecker())
            .AddAttribute("NodeTraversalTime",
                          "Estimated one-hop latency, used to size the reply wait.",
                          TimeValue(MilliSeconds(150)),
                          MakeTimeAccessor(&RoutingProtocol::m_nodeTraversalTime),
                          MakeTimeChecker())
            .AddAttribute("TtlStart",
                          "Hop budget of the first ring of the expanding search.",
                          UintegerValue(3),
                          MakeUintegerAccessor(&RoutingProtocol::m_ttlStart),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("TtlIncrement",
                          "How much the ring widens on each retry.",
                          UintegerValue(3),
                          MakeUintegerAccessor(&RoutingProtocol::m_ttlIncrement),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("RreqRetries",
                          "Route request attempts before giving up.",
                          UintegerValue(3),
                          MakeUintegerAccessor(&RoutingProtocol::m_rreqRetriesMax),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("RreqRateLimit",
                          "Route requests a node may originate per second (RFC 3561).",
                          UintegerValue(5),
                          MakeUintegerAccessor(&RoutingProtocol::m_rreqRateLimit),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("RreqMaxForwards",
                          "Times one route request may be rebroadcast by one node.",
                          UintegerValue(1),
                          MakeUintegerAccessor(&RoutingProtocol::m_rreqMaxForwards),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("RreqImprovement",
                          "Relative cost gain a repeat request must show to be rebroadcast.",
                          DoubleValue(0.05),
                          MakeDoubleAccessor(&RoutingProtocol::m_rreqImprovement),
                          MakeDoubleChecker<double>())
            .AddAttribute("NetDiameter",
                          "Maximum number of hops a route request may travel.",
                          UintegerValue(10),
                          MakeUintegerAccessor(&RoutingProtocol::m_netDiameter),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("MaxQueueLen",
                          "Packets buffered per node while a route is discovered.",
                          UintegerValue(64),
                          MakeUintegerAccessor(&RoutingProtocol::m_maxQueueLen),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("DetectMinWindow",
                          "Watchdog observations a detection window needs to be usable.",
                          UintegerValue(6),
                          MakeUintegerAccessor(&RoutingProtocol::m_detectMinWindow),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("LocalRepair",
                          "Repair a broken route at the break instead of dropping the packet.",
                          BooleanValue(true),
                          MakeBooleanAccessor(&RoutingProtocol::m_localRepair),
                          MakeBooleanChecker())
            .AddAttribute("FloodSuppression",
                          "Suppress route-request rebroadcasts that cover no new neighbour.",
                          BooleanValue(true),
                          MakeBooleanAccessor(&RoutingProtocol::m_floodSuppression),
                          MakeBooleanChecker())
            .AddAttribute("MinAdditionalCoverage",
                          "Neighbours a rebroadcast must newly reach to be worth sending.",
                          UintegerValue(1),
                          MakeUintegerAccessor(&RoutingProtocol::m_minAdditionalCoverage),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("LinkQualityThreshold",
                          "Smoothed beacon reception rate a link must reach to carry a route.",
                          DoubleValue(0.6),
                          MakeDoubleAccessor(&RoutingProtocol::m_linkQualityThreshold),
                          MakeDoubleChecker<double>())
            .AddAttribute("LinkQualityWeight",
                          "Weight of the newest window in the link-quality average.",
                          DoubleValue(0.4),
                          MakeDoubleAccessor(&RoutingProtocol::m_linkQualityWeight),
                          MakeDoubleChecker<double>())
            .AddAttribute("LinkQualityInitial",
                          "Quality credited to a link on its first beacon.",
                          DoubleValue(0.7),
                          MakeDoubleAccessor(&RoutingProtocol::m_linkQualityInitial),
                          MakeDoubleChecker<double>())
            .AddAttribute("TrustThreshold",
                          "PFR below which a node is reported suspicious (base.pdf 3.7).",
                          DoubleValue(0.6),
                          MakeDoubleAccessor(&RoutingProtocol::m_trustThreshold),
                          MakeDoubleChecker<double>())
            .AddAttribute("TrustSmoothing",
                          "Weight of the previous trust value in T <- w*T + (1-w)*PFR.",
                          DoubleValue(0.7),
                          MakeDoubleAccessor(&RoutingProtocol::m_trustSmoothing),
                          MakeDoubleChecker<double>())
            .AddAttribute("MinObservations",
                          "Watchdog observations required before an opinion is published.",
                          UintegerValue(5),
                          MakeUintegerAccessor(&RoutingProtocol::m_minObservations),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("ConsensusFraction",
                          "Fraction of a node's watchers that must accuse it.",
                          DoubleValue(0.5),
                          MakeDoubleAccessor(&RoutingProtocol::m_consensusFraction),
                          MakeDoubleChecker<double>())
            .AddAttribute("MinAccusers",
                          "Minimum number of accusers regardless of the fraction.",
                          UintegerValue(2),
                          MakeUintegerAccessor(&RoutingProtocol::m_minAccusers),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("EnergyThreshold",
                          "Battery fraction below which a node stops relaying (base.pdf 3.5).",
                          DoubleValue(0.2),
                          MakeDoubleAccessor(&RoutingProtocol::m_energyThreshold),
                          MakeDoubleChecker<double>())
            .AddAttribute("HopPenalty",
                          "Per-hop term added to the route cost.",
                          DoubleValue(0.35),
                          MakeDoubleAccessor(&RoutingProtocol::m_hopPenalty),
                          MakeDoubleChecker<double>())
            .AddAttribute("ContestedWeight",
                          "Trust multiplier applied to a GAN-contested node.",
                          DoubleValue(0.5),
                          MakeDoubleAccessor(&RoutingProtocol::m_contestedWeight),
                          MakeDoubleChecker<double>())
            .AddAttribute("ContestedTtl",
                          "How long a contested verdict lasts.",
                          TimeValue(Seconds(60)),
                          MakeTimeAccessor(&RoutingProtocol::m_contestedTtl),
                          MakeTimeChecker())
            .AddAttribute("GrayholeDropProb",
                          "Probability a gray-hole drops a large packet it should relay.",
                          DoubleValue(0.25),
                          MakeDoubleAccessor(&RoutingProtocol::m_grayholeDropProb),
                          MakeDoubleChecker<double>())
            .AddAttribute("LargePacketThreshold",
                          "Payload size at or above which a packet counts as large.",
                          UintegerValue(700),
                          MakeUintegerAccessor(&RoutingProtocol::m_largePacketThreshold),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("EnergyExcuse",
                          "Check the battery before blaming a node (base.pdf 3.7).",
                          BooleanValue(true),
                          MakeBooleanAccessor(&RoutingProtocol::m_energyExcuse),
                          MakeBooleanChecker())
            .AddAttribute("EnergyGate",
                          "Refuse to relay below the energy threshold (base.pdf 3.5).",
                          BooleanValue(true),
                          MakeBooleanAccessor(&RoutingProtocol::m_energyGate),
                          MakeBooleanChecker());
    return tid;
}

void
RoutingProtocol::DoInitialize()
{
    Start();
    Ipv4RoutingProtocol::DoInitialize();
}

void
RoutingProtocol::DoDispose()
{
    m_ipv4 = nullptr;
    for (auto i = m_socketAddresses.begin(); i != m_socketAddresses.end(); ++i)
    {
        i->first->Close();
    }
    m_socketAddresses.clear();
    for (auto i = m_socketSubnetBroadcastAddresses.begin();
         i != m_socketSubnetBroadcastAddresses.end();
         ++i)
    {
        i->first->Close();
    }
    m_socketSubnetBroadcastAddresses.clear();
    m_nidTimer.Cancel();
    m_gidTimer.Cancel();
    m_detectTimer.Cancel();
    m_watchdogTimer.Cancel();
    m_harvestTimer.Cancel();
    for (auto& t : m_rreqTimers)
    {
        t.second.Cancel();
    }
    m_energySource = nullptr;
    Ipv4RoutingProtocol::DoDispose();
}

int64_t
RoutingProtocol::AssignStreams(int64_t stream)
{
    m_uniform->SetStream(stream);
    return 1;
}

void
RoutingProtocol::Start()
{
    m_neighbors.SetParameters(4 * m_nidInterval,
                              m_watchdogTimeout,
                              m_trustSmoothing,
                              m_trustThreshold,
                              m_minObservations,
                              m_largePacketThreshold);

    Ptr<Node> node = m_ipv4->GetObject<Node>();
    Ptr<energy::EnergySourceContainer> sources =
        node->GetObject<energy::EnergySourceContainer>();
    if (sources && sources->GetN() > 0)
    {
        m_energySource = sources->Get(0);
        m_initialEnergy = m_energySource->GetInitialEnergy();
    }

    // Beacons and consensus rounds are jittered so that a hundred nodes do not
    // all transmit into the same microsecond and wipe each other out.
    m_nidTimer.SetFunction(&RoutingProtocol::SendNid, this);
    m_nidTimer.Schedule(MilliSeconds(m_uniform->GetInteger(0, 1000)));
    m_gidTimer.SetFunction(&RoutingProtocol::SendGid, this);
    m_gidTimer.Schedule(m_gidInterval + MilliSeconds(m_uniform->GetInteger(0, 2000)));
    m_detectTimer.SetFunction(&RoutingProtocol::RunDetection, this);
    m_detectTimer.Schedule(m_detectInterval + MilliSeconds(m_uniform->GetInteger(0, 2000)));
    m_watchdogTimer.SetFunction(&RoutingProtocol::SweepWatchdogs, this);
    m_watchdogTimer.Schedule(MilliSeconds(200));
    m_harvestTimer.SetFunction(&RoutingProtocol::SampleHarvest, this);
    m_harvestTimer.Schedule(Seconds(1) + MilliSeconds(m_uniform->GetInteger(0, 500)));
}

void
RoutingProtocol::SetIpv4(Ptr<Ipv4> ipv4)
{
    NS_ASSERT(ipv4);
    NS_ASSERT(!m_ipv4);
    m_ipv4 = ipv4;

    // The loopback interface is what deferred (route-less) packets travel over
    // before route discovery starts.
    NS_ASSERT(m_ipv4->GetNInterfaces() == 1 &&
              m_ipv4->GetAddress(0, 0).GetLocal() == Ipv4Address("127.0.0.1"));
    m_lo = m_ipv4->GetNetDevice(0);
    NS_ASSERT(m_lo);
}

Ipv4Address
RoutingProtocol::MainAddress() const
{
    if (m_socketAddresses.empty())
    {
        return Ipv4Address();
    }
    return m_socketAddresses.begin()->second.GetLocal();
}

bool
RoutingProtocol::IsMyOwnAddress(Ipv4Address src)
{
    for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
    {
        if (src == j->second.GetLocal())
        {
            return true;
        }
    }
    return false;
}

Ptr<Socket>
RoutingProtocol::CreateSocket(Ipv4InterfaceAddress iface, bool subnetBroadcast)
{
    Ptr<Node> node = m_ipv4->GetObject<Node>();
    Ptr<Socket> socket = Socket::CreateSocket(node, UdpSocketFactory::GetTypeId());
    NS_ASSERT(socket);
    socket->SetRecvCallback(MakeCallback(&RoutingProtocol::RecvArEaurp, this));
    socket->BindToNetDevice(m_ipv4->GetNetDevice(m_ipv4->GetInterfaceForAddress(iface.GetLocal())));
    const Ipv4Address bindTo = subnetBroadcast ? iface.GetBroadcast() : iface.GetLocal();
    socket->Bind(InetSocketAddress(bindTo, AR_EAURP_PORT));
    socket->SetAllowBroadcast(true);
    socket->SetIpRecvTtl(true);
    return socket;
}

void
RoutingProtocol::NotifyInterfaceUp(uint32_t i)
{
    Ptr<Ipv4L3Protocol> l3 = m_ipv4->GetObject<Ipv4L3Protocol>();
    if (l3->GetNAddresses(i) > 1)
    {
        NS_LOG_WARN("AR-EAURP uses only the first address of each interface");
    }
    Ipv4InterfaceAddress iface = l3->GetAddress(i, 0);
    if (iface.GetLocal() == Ipv4Address("127.0.0.1"))
    {
        return;
    }

    m_socketAddresses.insert(std::make_pair(CreateSocket(iface, false), iface));
    m_socketSubnetBroadcastAddresses.insert(std::make_pair(CreateSocket(iface, true), iface));

    // A route to ourselves, so that local delivery and the loopback trick work.
    RoutingTableEntry rt(m_ipv4->GetNetDevice(i),
                         iface.GetLocal(),
                         true,
                         0,
                         iface,
                         1,
                         iface.GetLocal(),
                         Simulator::GetMaximumSimulationTime());
    m_routingTable.AddRoute(rt);

    // Promiscuous reception is what makes a watchdog a watchdog: the node has
    // to overhear frames that are not addressed to it.
    Ptr<NetDevice> dev = m_ipv4->GetNetDevice(i);
    Ptr<WifiNetDevice> wifi = DynamicCast<WifiNetDevice>(dev);
    if (wifi)
    {
        Ptr<Node> node = m_ipv4->GetObject<Node>();
        node->RegisterProtocolHandler(MakeCallback(&RoutingProtocol::PromiscRx, this),
                                      Ipv4L3Protocol::PROT_NUMBER,
                                      dev,
                                      true);

        // Without this the routing layer never learns that a link has failed.
        // Data traffic refreshes a route's lifetime every time it is used, so a
        // route whose next hop has walked out of range would be kept alive by
        // the very packets it is swallowing -- the flow would keep feeding a
        // link that no longer exists until it stopped sending.
        Ptr<WifiMac> mac = wifi->GetMac();
        if (mac)
        {
            mac->TraceConnectWithoutContext(
                "DroppedMpdu",
                MakeCallback(&RoutingProtocol::NotifyTxError, this));
        }

        // Watch our own transmissions, so that a watchdog entry is armed from
        // exactly the frame the neighbours will overhear being relayed.
        Ptr<WifiPhy> phy = wifi->GetPhy();
        if (phy)
        {
            phy->TraceConnectWithoutContext("PhyTxBegin",
                                            MakeCallback(&RoutingProtocol::NotifyPhyTx, this));
        }
    }
}

void
RoutingProtocol::NotifyInterfaceDown(uint32_t i)
{
    Ptr<Socket> socket = nullptr;
    for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
    {
        if (m_ipv4->GetInterfaceForAddress(j->second.GetLocal()) == (int32_t)i)
        {
            socket = j->first;
            break;
        }
    }
    if (socket)
    {
        socket->Close();
        m_socketAddresses.erase(socket);
    }
    m_routingTable.DeleteAllRoutesFromInterface(m_ipv4->GetAddress(i, 0));
}

void
RoutingProtocol::NotifyAddAddress(uint32_t i, Ipv4InterfaceAddress address)
{
    Ptr<Ipv4L3Protocol> l3 = m_ipv4->GetObject<Ipv4L3Protocol>();
    if (!l3->IsUp(i))
    {
        return;
    }
    if (l3->GetNAddresses(i) != 1)
    {
        return;
    }
    Ipv4InterfaceAddress iface = l3->GetAddress(i, 0);
    if (iface.GetLocal() == Ipv4Address("127.0.0.1"))
    {
        return;
    }
    bool known = false;
    for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
    {
        if (j->second == iface)
        {
            known = true;
        }
    }
    if (!known)
    {
        m_socketAddresses.insert(std::make_pair(CreateSocket(iface, false), iface));
        m_socketSubnetBroadcastAddresses.insert(std::make_pair(CreateSocket(iface, true), iface));
    }
}

void
RoutingProtocol::NotifyRemoveAddress(uint32_t i, Ipv4InterfaceAddress address)
{
    (void)i;
    (void)address;
}

void
RoutingProtocol::PrintRoutingTable(Ptr<OutputStreamWrapper> stream, Time::Unit unit) const
{
    (void)unit;
    *stream->GetStream() << "Node: " << m_ipv4->GetObject<Node>()->GetId()
                         << " Time: " << Simulator::Now().As(Time::S) << "\n";
    m_routingTable.Print(stream);
}

// --------------------------------------------------------------- scoring ---

void
RoutingProtocol::ScoreCoefficients(double& a, double& b) const
{
    // base.pdf 3.3: b is the network's mean normalised energy, a = 1 - b.
    // A node cannot see the whole network, so it estimates from the batteries
    // its neighbours advertise in PT_NID, plus its own.
    double sum = EnergyFraction();
    uint32_t count = 1;
    for (const auto& kv : m_neighbors.Table())
    {
        if (kv.second.expire > Simulator::Now())
        {
            sum += kv.second.energyFraction;
            count++;
        }
    }
    b = std::min(1.0, std::max(0.0, sum / (double)count));
    a = 1.0 - b;
}

uint32_t
RoutingProtocol::HopCostMilli(Ipv4Address neighbour, uint8_t policy) const
{
    if (m_variant == VARIANT_AODV)
    {
        return 1000; // plain hop count: every hop costs the same
    }

    double trust = m_neighbors.GetTrust(neighbour);
    if (m_variant == VARIANT_DRL_SENIOR)
    {
        auto report = m_endpointReports.find(neighbour);
        trust = report == m_endpointReports.end() ? 1.0 : report->second;
    }
    const double energy = m_neighbors.GetEnergyFraction(neighbour);
    const double surplus = m_neighbors.GetSurplus(neighbour);

    if (m_variant == VARIANT_AR_EAURP && m_neighbors.IsContested(neighbour))
    {
        // The contested down-weight is applied to the trust term itself, after
        // any value the neighbour advertised, so a node that lies about its own
        // quality still loses the weight its behaviour has cost it.
        trust *= m_contestedWeight;
    }

    double a;
    double b;
    ScoreCoefficients(a, b);
    double effectiveEnergy = energy;

    switch (policy)
    {
    case ACTION_TRUST:
        a = 1.0;
        b = 0.0;
        break;
    case ACTION_ENERGY:
        a = 0.3;
        b = 0.7;
        // Energy a node is about to harvest counts, which is the whole point of
        // the forecast: a relay that is low now but is coming back into the sun
        // is a better bet than one that is low and staying low.
        effectiveEnergy = std::min(1.0, 0.5 * energy + 0.5 * surplus);
        break;
    case ACTION_BALANCED:
    case ACTION_DIVERSE:
    default:
        break;
    }

    const double rScore = std::min(1.0, std::max(0.0, a * trust + b * effectiveEnergy));
    const double cost = (1.0 - rScore) + m_hopPenalty;
    return (uint32_t)std::lround(cost * 1000.0);
}

double
RoutingProtocol::EnergyFraction() const
{
    if (!m_energySource)
    {
        return 1.0;
    }
    return std::min(1.0, std::max(0.0, m_energySource->GetEnergyFraction()));
}

bool
RoutingProtocol::EnergyGateOpen() const
{
    if (!m_energyGate || m_variant == VARIANT_AODV)
    {
        return true; // plain AODV is energy blind, which is the point of it
    }
    return EnergyFraction() > m_energyThreshold;
}

double
RoutingProtocol::WindowPdr() const
{
    if (m_deliveryWindow.empty())
    {
        return 1.0;
    }
    uint32_t ok = 0;
    for (bool b : m_deliveryWindow)
    {
        if (b)
        {
            ok++;
        }
    }
    return (double)ok / (double)m_deliveryWindow.size();
}

// -------------------------------------------------------------- adversary ---

bool
RoutingProtocol::ForwardsData(uint32_t payloadSize)
{
    switch (m_attack)
    {
    case ATTACK_BLACKHOLE:
        return false; // swallows everything it is asked to relay
    case ATTACK_GRAYHOLE:
    case ATTACK_TRUST_POISONING:
        if (payloadSize < m_largePacketThreshold)
        {
            return true; // small packets pass, which keeps the scalar PFR high
        }
        return m_uniform->GetValue(0.0, 1.0) >= m_grayholeDropProb;
    case ATTACK_NONE:
    default:
        return true;
    }
}

double
RoutingProtocol::PublishedTrust(Ipv4Address subject, double measured) const
{
    if (m_attack != ATTACK_TRUST_POISONING)
    {
        return measured;
    }
    // Colluders recognise each other -- they were deployed together -- so a
    // slanderer vouches for its own kind and accuses the honest nodes its
    // neighbours trust most. This is the one place the simulation's ground
    // truth is read by a node, and it is read by an attacker, who by
    // assumption knows who its confederates are.
    if (Oracle::Get().IsMalicious(subject))
    {
        return 1.0;
    }
    return 0.15;
}

// ------------------------------------------------------------ route output ---

Ptr<Ipv4Route>
RoutingProtocol::LoopbackRoute(const Ipv4Header& hdr, Ptr<NetDevice> oif) const
{
    NS_ASSERT(m_lo);
    Ptr<Ipv4Route> rt = Create<Ipv4Route>();
    rt->SetDestination(hdr.GetDestination());

    auto j = m_socketAddresses.begin();
    if (oif)
    {
        for (; j != m_socketAddresses.end(); ++j)
        {
            Ipv4Address addr = j->second.GetLocal();
            int32_t interface = m_ipv4->GetInterfaceForAddress(addr);
            if (oif == m_ipv4->GetNetDevice(static_cast<uint32_t>(interface)))
            {
                rt->SetSource(addr);
                break;
            }
        }
    }
    if (j == m_socketAddresses.end())
    {
        j = m_socketAddresses.begin();
    }
    NS_ASSERT_MSG(j != m_socketAddresses.end(), "AR-EAURP has no running interface");
    rt->SetSource(j->second.GetLocal());
    rt->SetGateway(Ipv4Address("127.0.0.1"));
    rt->SetOutputDevice(m_lo);
    return rt;
}

Ptr<Ipv4Route>
RoutingProtocol::RouteOutput(Ptr<Packet> p,
                             const Ipv4Header& header,
                             Ptr<NetDevice> oif,
                             Socket::SocketErrno& sockerr)
{
    if (!p)
    {
        return LoopbackRoute(header, oif);
    }
    if (m_socketAddresses.empty())
    {
        sockerr = Socket::ERROR_NOROUTETOHOST;
        return nullptr;
    }
    sockerr = Socket::ERROR_NOTERROR;
    Ipv4Address dst = header.GetDestination();

    RoutingTableEntry rt;
    if (m_routingTable.LookupValidRoute(dst, rt))
    {
        Ptr<Ipv4Route> route = rt.GetRoute();
        if (oif && route->GetOutputDevice() != oif)
        {
            sockerr = Socket::ERROR_NOROUTETOHOST;
            return Ptr<Ipv4Route>();
        }
        UpdateRouteLifeTime(dst, m_activeRouteTimeout);
        UpdateRouteLifeTime(route->GetGateway(), m_activeRouteTimeout);

        return route;
    }

    const int32_t iif = (oif ? m_ipv4->GetInterfaceForDevice(oif) : -1);
    DeferredRouteOutputTag tag(iif);
    if (!p->PeekPacketTag(tag))
    {
        p->AddPacketTag(tag);
    }
    return LoopbackRoute(header, oif);
}

void
RoutingProtocol::DeferredRouteOutput(Ptr<const Packet> p,
                                     const Ipv4Header& header,
                                     UnicastForwardCallback ucb,
                                     ErrorCallback ecb)
{
    if (m_queue.size() >= m_maxQueueLen)
    {
        // Drop the oldest: a stale packet is worth less than a fresh one.
        m_queue.erase(m_queue.begin());
        Oracle::Get().CountQueueDrop(true);
    }
    Oracle::Get().CountQueued();
    QueueEntry e;
    e.packet = p;
    e.header = header;
    e.ucb = ucb;
    e.ecb = ecb;
    e.expire = Simulator::Now() + m_queueTimeout;
    m_queue.push_back(e);

    RoutingTableEntry rt;
    const bool result = m_routingTable.LookupRoute(header.GetDestination(), rt);
    if (!result || ((rt.GetFlag() != IN_SEARCH) && result))
    {
        SendRequest(header.GetDestination());
    }
}

// ------------------------------------------------------------- route input ---

bool
RoutingProtocol::RouteInput(Ptr<const Packet> p,
                            const Ipv4Header& header,
                            Ptr<const NetDevice> idev,
                            const UnicastForwardCallback& ucb,
                            const MulticastForwardCallback& mcb,
                            const LocalDeliverCallback& lcb,
                            const ErrorCallback& ecb)
{
    (void)mcb;
    if (m_socketAddresses.empty())
    {
        return false;
    }
    NS_ASSERT(m_ipv4);
    NS_ASSERT(p);
    NS_ASSERT(m_ipv4->GetInterfaceForDevice(idev) >= 0);
    const int32_t iif = m_ipv4->GetInterfaceForDevice(idev);

    const Ipv4Address dst = header.GetDestination();
    const Ipv4Address origin = header.GetSource();

    if (idev == m_lo)
    {
        DeferredRouteOutputTag tag;
        if (p->PeekPacketTag(tag))
        {
            // Loopback dispatch is an internal queue, not a network hop.
            // Ipv4 forwarding decrements TTL again when dequeuing it.
            Ipv4Header queuedHeader = header;
            queuedHeader.SetTtl(header.GetTtl() + 1);
            DeferredRouteOutput(p, queuedHeader, ucb, ecb);
            return true;
        }
    }

    if (IsMyOwnAddress(origin))
    {
        return true;
    }
    if (dst.IsMulticast())
    {
        return false;
    }

    // Broadcast: deliver locally, and let the control plane's own flooding
    // rules decide about retransmission (we never blindly reflood).
    for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
    {
        Ipv4InterfaceAddress iface = j->second;
        if (m_ipv4->GetInterfaceForAddress(iface.GetLocal()) == iif)
        {
            if (dst == iface.GetBroadcast() || dst.IsBroadcast())
            {
                UpdateRouteLifeTime(origin, m_activeRouteTimeout);
                if (!lcb.IsNull())
                {
                    lcb(p, header, iif);
                }
                return true;
            }
        }
    }

    // Unicast, for us.
    if (m_ipv4->IsDestinationAddress(dst, iif))
    {
        UpdateRouteLifeTime(origin, m_activeRouteTimeout);
        RoutingTableEntry toOrigin;
        if (m_routingTable.LookupValidRoute(origin, toOrigin))
        {
            UpdateRouteLifeTime(toOrigin.GetNextHop(), m_activeRouteTimeout);
        }
        if (!lcb.IsNull())
        {
            lcb(p, header, iif);
        }
        else
        {
            ecb(p, header, Socket::ERROR_NOROUTETOHOST);
        }
        return true;
    }

    if (!m_ipv4->IsForwarding(iif))
    {
        ecb(p, header, Socket::ERROR_NOROUTETOHOST);
        return true;
    }
    return Forwarding(p, header, ucb, ecb);
}

bool
RoutingProtocol::Forwarding(Ptr<const Packet> p,
                            const Ipv4Header& header,
                            const UnicastForwardCallback& ucb,
                            const ErrorCallback& ecb)
{
    const Ipv4Address dst = header.GetDestination();
    const Ipv4Address origin = header.GetSource();
    m_routingTable.Purge();

    RoutingTableEntry toDst;
    if (m_routingTable.LookupRoute(dst, toDst) && toDst.GetFlag() == VALID)
    {
        // base.pdf 3.5: a relay below the energy threshold takes itself out of
        // service rather than spending its last joules on other people's
        // traffic. Its neighbours will watch it drop packets, which is exactly
        // why 3.7 makes them check its battery before calling it malicious.
        if (!EnergyGateOpen())
        {
            Oracle::Get().CountEnergyDrop();
            SendRerrWhenBreaksLinkToNextHop(MainAddress());
            ecb(p, header, Socket::ERROR_NOROUTETOHOST);
            return true;
        }

        if (!ForwardsData(p->GetSize()))
        {
            // The adversary drops it. Nothing is sent, nothing is signalled:
            // from the network's point of view the packet simply vanishes,
            // which is what makes the watchdog the only way to notice.
            Oracle::Get().CountAdversaryDrop(p->GetSize(),
                                             p->GetSize() >= m_largePacketThreshold);
            return true;
        }

        Ptr<Ipv4Route> route = toDst.GetRoute();
        UpdateRouteLifeTime(origin, m_activeRouteTimeout);
        UpdateRouteLifeTime(dst, m_activeRouteTimeout);
        UpdateRouteLifeTime(route->GetGateway(), m_activeRouteTimeout);

        RoutingTableEntry toOrigin;
        if (m_routingTable.LookupRoute(origin, toOrigin))
        {
            toDst.InsertPrecursor(toOrigin.GetNextHop());
            m_routingTable.Update(toDst);
        }

        Oracle::Get().CountForward();
        ucb(route, p, header);
        return true;
    }

    // Local repair (RFC 3561 6.12). The route broke under us, in the middle of
    // somebody else's flow. Dropping the packet and telling the source to start
    // again throws away everything already spent carrying it this far, and the
    // source's rediscovery floods the whole network; repairing locally usually
    // needs a two-hop search and keeps the packet.
    if (m_localRepair)
    {
        Oracle::Get().CountLocalRepair();
        DeferredRouteOutput(p, header, ucb, ecb);
        return true;
    }

    // No usable route: tell the upstream node so it can rediscover.
    Oracle::Get().CountNoRoute();
    RoutingTableEntry toOrigin;
    if (m_routingTable.LookupValidRoute(origin, toOrigin))
    {
        RerrHeader rerrHeader;
        rerrHeader.AddUnDestination(dst, toDst.GetSeqNo());
        Ptr<Packet> packet = Create<Packet>();
        packet->AddHeader(rerrHeader);
        packet->AddHeader(TypeHeader(AREAURP_RERR));
        std::vector<Ipv4Address> precursors;
        precursors.push_back(toOrigin.GetNextHop());
        SendRerrMessage(packet, precursors);
    }
    return false;
}

void
RoutingProtocol::UpdateRouteLifeTime(Ipv4Address addr, Time lifetime)
{
    RoutingTableEntry rt;
    if (m_routingTable.LookupRoute(addr, rt))
    {
        if (rt.GetFlag() == VALID)
        {
            if (rt.GetLifeTime() < lifetime)
            {
                rt.SetLifeTime(lifetime);
            }
            m_routingTable.Update(rt);
        }
    }
}

void
RoutingProtocol::UpdateRouteToNeighbor(Ipv4Address sender, Ipv4Address receiver)
{
    RoutingTableEntry toNeighbor;
    if (!m_routingTable.LookupRoute(sender, toNeighbor))
    {
        Ptr<NetDevice> dev = m_ipv4->GetNetDevice(m_ipv4->GetInterfaceForAddress(receiver));
        RoutingTableEntry newEntry(dev,
                                   sender,
                                   false,
                                   0,
                                   m_ipv4->GetAddress(m_ipv4->GetInterfaceForAddress(receiver), 0),
                                   1,
                                   sender,
                                   m_activeRouteTimeout);
        m_routingTable.AddRoute(newEntry);
    }
    else
    {
        Ptr<NetDevice> dev = m_ipv4->GetNetDevice(m_ipv4->GetInterfaceForAddress(receiver));
        if (toNeighbor.GetValidSeqNo() && (toNeighbor.GetHop() == 1) &&
            (toNeighbor.GetOutputDevice() == dev))
        {
            toNeighbor.SetLifeTime(std::max(m_activeRouteTimeout, toNeighbor.GetLifeTime()));
        }
        else
        {
            RoutingTableEntry newEntry(
                dev,
                sender,
                false,
                0,
                m_ipv4->GetAddress(m_ipv4->GetInterfaceForAddress(receiver), 0),
                1,
                sender,
                std::max(m_activeRouteTimeout, toNeighbor.GetLifeTime()));
            toNeighbor = newEntry;
        }
        toNeighbor.SetFlag(VALID);
        m_routingTable.Update(toNeighbor);
    }
}

// ------------------------------------------------------------- discovery ---

void
RoutingProtocol::SendRequest(Ipv4Address dst)
{
    if (m_socketAddresses.empty())
    {
        return;
    }

    // RFC 3561's RREQ_RATELIMIT. Without it a node whose destination is
    // unreachable can flood the whole network flat out, and the flood costs
    // far more airtime than the traffic it is trying to carry.
    if (Simulator::Now() - m_rreqWindowStart >= Seconds(1))
    {
        m_rreqWindowStart = Simulator::Now();
        m_rreqThisSecond = 0;
    }
    if (m_rreqThisSecond >= m_rreqRateLimit)
    {
        ScheduleRreqRetry(dst, (uint8_t)m_netDiameter);
        return;
    }
    m_rreqThisSecond++;

    // AR-EAURP: the constrained agent picks the scoring policy for this
    // discovery, from the node's own view of trust, energy and recent delivery.
    uint8_t policy = ACTION_BALANCED;
    RoutingTableEntry searching;
    const bool retry = m_routingTable.LookupRoute(dst, searching) &&
                       searching.GetFlag() == IN_SEARCH && m_pending.count(dst);
    if (retry) policy = m_policyInUse[dst];
    else if (m_variant == VARIANT_AR_EAURP && m_useCmdp && Oracle::Get().Agent() &&
        (Oracle::Get().Phase() == PHASE_EVALUATION ||
         Oracle::Get().Phase() == PHASE_COMMISSIONING))
    {
        const Vec state = BuildState();
        const uint32_t action = Oracle::Get().Agent()->Act(state);
        policy = (uint8_t)action;
        PendingDecision pd;
        pd.state = state;
        pd.action = action;
        pd.taken = Simulator::Now();
        pd.id = ++m_nextDecision;
        m_pending[dst] = pd;
        m_decisionHistory[pd.id] = pd;
    }
    else if (m_variant == VARIANT_DRL_PAPER || m_variant == VARIANT_DRL_SENIOR)
    {
        Vec state = BuildState();
        const uint32_t action = m_tabular.Act(state, m_uniform->GetValue(), m_uniform->GetInteger(0, 1));
        policy = action == 0 ? ACTION_TRUST : ACTION_DIVERSE;
        PendingDecision pd{state, action, Simulator::Now(), ++m_nextDecision};
        m_pending[dst] = pd;
        m_decisionHistory[pd.id] = pd;
    }
    // Decisions older than two ACK horizons cannot have outstanding rewards.
    for (auto i = m_decisionHistory.begin(); i != m_decisionHistory.end();)
    {
        if (Simulator::Now() - i->second.taken > Seconds(12) &&
            std::none_of(m_pending.begin(), m_pending.end(), [&](const auto& entry) { return entry.second.id == i->first; }))
            i = m_decisionHistory.erase(i);
        else ++i;
    }
    m_policyInUse[dst] = policy;

    RreqHeader rreqHeader;
    rreqHeader.SetDst(dst);
    rreqHeader.SetHopCount(0);
    rreqHeader.SetPathCost(0);

    RoutingTableEntry rt;
    if (m_routingTable.LookupRoute(dst, rt))
    {
        rreqHeader.SetDstSeqno(rt.GetSeqNo());
        rreqHeader.SetUnknownSeqno(!rt.GetValidSeqNo());
        rt.IncrementRreqCnt();
        rt.SetFlag(IN_SEARCH);
        rt.SetLifeTime(m_pathDiscoveryTime);
        m_routingTable.Update(rt);
    }
    else
    {
        rreqHeader.SetUnknownSeqno(true);
        Ptr<NetDevice> dev = nullptr;
        RoutingTableEntry newEntry(dev,
                                   dst,
                                   false,
                                   0,
                                   m_socketAddresses.begin()->second,
                                   0,
                                   Ipv4Address(),
                                   m_pathDiscoveryTime);
        newEntry.SetFlag(IN_SEARCH);
        newEntry.IncrementRreqCnt();
        m_routingTable.AddRoute(newEntry);
    }

    NS_LOG_DEBUG(MainAddress() << " RREQ for " << dst << " id " << (m_requestId + 1));
    // Expanding ring search (RFC 3561 6.4). Most destinations are two or three
    // hops away, so flooding the whole network on the first attempt wastes the
    // airtime of every node in it. Start small, and only widen the ring when
    // the small search comes back empty. On this scenario that is what takes
    // the control plane from ~200 rebroadcasts per discovery to ~30.
    uint8_t ttl = m_ttlStart;
    RoutingTableEntry known;
    if (m_routingTable.LookupRoute(dst, known))
    {
        if (known.GetHop() > 0)
        {
            ttl = (uint8_t)std::min<uint32_t>(m_netDiameter, known.GetHop() + m_ttlIncrement);
        }
        const uint32_t attempt = known.GetRreqCnt();
        ttl = (uint8_t)std::min<uint32_t>(m_netDiameter, ttl + attempt * m_ttlIncrement);
        if (attempt >= 2)
        {
            ttl = (uint8_t)m_netDiameter;
        }
    }

    rreqHeader.SetId(++m_requestId);
    rreqHeader.SetTtl(ttl);
    rreqHeader.SetPolicy(policy);
    m_seqNo++;
    rreqHeader.SetOriginSeqno(m_seqNo);

    for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
    {
        Ptr<Socket> socket = j->first;
        Ipv4InterfaceAddress iface = j->second;
        rreqHeader.SetOrigin(iface.GetLocal());
        m_rreqSeen[std::make_pair(iface.GetLocal(), m_requestId)] = 0;
        m_rreqSeenTime[std::make_pair(iface.GetLocal(), m_requestId)] = Simulator::Now();

        Ptr<Packet> packet = Create<Packet>();
        packet->AddHeader(rreqHeader);
        packet->AddHeader(TypeHeader(AREAURP_RREQ));
        Ipv4Address destination = (iface.GetMask() == Ipv4Mask::GetOnes())
                                      ? Ipv4Address("255.255.255.255")
                                      : iface.GetBroadcast();
        Oracle::Get().CountControl(AREAURP_RREQ, packet->GetSize());
        Simulator::Schedule(MilliSeconds(m_uniform->GetInteger(0, 10)),
                            &RoutingProtocol::SendTo,
                            this,
                            socket,
                            packet,
                            destination);
    }
    ScheduleRreqRetry(dst, ttl);
}

void
RoutingProtocol::SendTo(Ptr<Socket> socket, Ptr<Packet> packet, Ipv4Address destination)
{
    socket->SendTo(packet, 0, InetSocketAddress(destination, AR_EAURP_PORT));
}

void
RoutingProtocol::ScheduleRreqRetry(Ipv4Address dst, uint8_t ttl)
{
    // The reply has to travel the whole ring back, so the wait has to scale
    // with the ring, not be a constant (RFC 3561's RING_TRAVERSAL_TIME).
    const Time wait = std::min(m_rreqTimeout,
                               2 * m_nodeTraversalTime * (int64_t)(ttl + 2));
    auto i = m_rreqTimers.find(dst);
    if (i == m_rreqTimers.end())
    {
        m_rreqTimers[dst] = EventId();
    }
    else
    {
        i->second.Cancel();
    }
    m_rreqTimers[dst] =
        Simulator::Schedule(wait, &RoutingProtocol::RouteRequestTimerExpire, this, dst);
}

void
RoutingProtocol::RouteRequestTimerExpire(Ipv4Address dst)
{
    RoutingTableEntry rt;
    if (m_routingTable.LookupValidRoute(dst, rt))
    {
        return; // a reply arrived in the meantime
    }
    if (m_routingTable.LookupRoute(dst, rt) && rt.GetRreqCnt() < m_rreqRetriesMax)
    {
        SendRequest(dst);
        return;
    }

    // Give up: fail every packet still waiting for this destination.
    NS_LOG_DEBUG(MainAddress() << " giving up on route to " << dst);
    Oracle::Get().CountRouteDiscovery(false);
    for (auto i = m_queue.begin(); i != m_queue.end();)
    {
        if (i->header.GetDestination() == dst)
        {
            if (!i->ecb.IsNull())
            {
                i->ecb(i->packet, i->header, Socket::ERROR_NOROUTETOHOST);
            }
            i = m_queue.erase(i);
        }
        else
        {
            ++i;
        }
    }
    m_routingTable.SetEntryState(dst, INVALID);
    m_pending.erase(dst);
}

void
RoutingProtocol::RecvArEaurp(Ptr<Socket> socket)
{
    Address sourceAddress;
    Ptr<Packet> packet = socket->RecvFrom(sourceAddress);
    if (!packet)
    {
        return;
    }
    InetSocketAddress inetSourceAddr = InetSocketAddress::ConvertFrom(sourceAddress);
    Ipv4Address sender = inetSourceAddr.GetIpv4();
    Ipv4Address receiver;

    if (m_socketAddresses.find(socket) != m_socketAddresses.end())
    {
        receiver = m_socketAddresses[socket].GetLocal();
    }
    else if (m_socketSubnetBroadcastAddresses.find(socket) !=
             m_socketSubnetBroadcastAddresses.end())
    {
        receiver = m_socketSubnetBroadcastAddresses[socket].GetLocal();
    }
    else
    {
        return;
    }

    // base.pdf 3.8: nothing is accepted from a node that has been revoked.
    if (m_neighbors.IsRevoked(sender))
    {
        return;
    }

    TypeHeader tHeader(AREAURP_RREQ);
    packet->RemoveHeader(tHeader);
    if (!tHeader.IsValid())
    {
        return;
    }

    switch (tHeader.Get())
    {
    case AREAURP_RREQ:
        RecvRequest(packet, receiver, sender);
        break;
    case AREAURP_RREP:
        RecvReply(packet, receiver, sender);
        break;
    case AREAURP_RERR:
        RecvError(packet, sender);
        break;
    case AREAURP_NID:
        RecvNid(packet, sender);
        break;
    case AREAURP_GID:
        RecvGid(packet, sender, receiver);
        break;
    case AREAURP_CREV:
        RecvCrev(packet, sender, receiver);
        break;
    default:
        break;
    }
}

void
RoutingProtocol::RecvRequest(Ptr<Packet> p, Ipv4Address receiver, Ipv4Address src)
{
    RreqHeader rreqHeader;
    p->RemoveHeader(rreqHeader);

    const Ipv4Address origin = rreqHeader.GetOrigin();
    if (IsMyOwnAddress(origin))
    {
        return;
    }

    // Only build a route over a link we have evidence actually works in both
    // directions. A request that arrives over a marginal link is still useful
    // as a sign the originator exists, but it must not become a route.
    if (!m_neighbors.IsUsableLink(src, m_linkQualityThreshold))
    {
        NS_LOG_DEBUG(MainAddress() << " REJECT-RREQ link to " << src << " unusable (q="
                                   << m_neighbors.GetQuality(src) << ")");
        return;
    }

    const uint8_t policy = rreqHeader.GetPolicy();
    // The cost of the hop we have just traversed, scored with *this* node's own
    // measurements of the neighbour it came from. A node never scores itself.
    const uint32_t cost = rreqHeader.GetPathCost() + HopCostMilli(src, policy);
    const auto key = std::make_pair(origin, rreqHeader.GetId());

    // Plain AODV forwards a request once and never looks at it again; scoring
    // routes by cost means a later copy can genuinely be better, so a repeat is
    // allowed -- but only when it is materially cheaper, and only a bounded
    // number of times. Without both limits the improvement rule turns one
    // discovery into hundreds of rebroadcasts and the flood costs more airtime
    // than the data it is finding a route for.
    auto seen = m_rreqSeen.find(key);
    const bool repeat = (seen != m_rreqSeen.end());
    if (repeat && cost >= seen->second * (1.0 - m_rreqImprovement))
    {
        return;
    }
    const bool mayForward =
        !repeat || (m_rreqForwards[key] < m_rreqMaxForwards);
    m_rreqSeen[key] = cost;
    m_rreqSeenTime[key] = Simulator::Now();
    if (m_rreqSeen.size() > 4096)
    {
        // Bound the cache: drop everything older than one path-discovery time.
        const Time cutoff = Simulator::Now() - 10 * m_pathDiscoveryTime;
        for (auto i = m_rreqSeenTime.begin(); i != m_rreqSeenTime.end();)
        {
            if (i->second < cutoff)
            {
                m_rreqSeen.erase(i->first);
                m_rreqForwards.erase(i->first);
                i = m_rreqSeenTime.erase(i);
            }
            else
            {
                ++i;
            }
        }
    }

    UpdateRouteToNeighbor(src, receiver);
    m_neighbors.Refresh(src, Mac48Address(), m_neighbors.GetEnergyFraction(src),
                        m_neighbors.GetSurplus(src));

    // Reverse route to the originator, through the neighbour we heard this from.
    RoutingTableEntry toOrigin;
    Ptr<NetDevice> dev = m_ipv4->GetNetDevice(m_ipv4->GetInterfaceForAddress(receiver));
    Ipv4InterfaceAddress iface = m_ipv4->GetAddress(m_ipv4->GetInterfaceForAddress(receiver), 0);
    const uint16_t hops = rreqHeader.GetHopCount() + 1;
    if (!m_routingTable.LookupRoute(origin, toOrigin))
    {
        RoutingTableEntry newEntry(dev,
                                   origin,
                                   true,
                                   rreqHeader.GetOriginSeqno(),
                                   iface,
                                   hops,
                                   src,
                                   m_activeRouteTimeout,
                                   cost);
        m_routingTable.AddRoute(newEntry);
    }
    else
    {
        // Accept the reverse route when it is fresher, or equally fresh and
        // cheaper under the policy this request is being scored with.
        const bool fresher = (int32_t)(rreqHeader.GetOriginSeqno() - toOrigin.GetSeqNo()) > 0;
        const bool cheaper = (rreqHeader.GetOriginSeqno() == toOrigin.GetSeqNo()) &&
                             (cost < toOrigin.GetPathCost());
        if (fresher || cheaper || toOrigin.GetFlag() != VALID)
        {
            toOrigin.SetSeqNo(rreqHeader.GetOriginSeqno());
            toOrigin.SetValidSeqNo(true);
            toOrigin.SetNextHop(src);
            toOrigin.SetOutputDevice(dev);
            toOrigin.SetInterface(iface);
            toOrigin.SetHop(hops);
            toOrigin.SetPathCost(cost);
            toOrigin.SetFlag(VALID);
            toOrigin.SetLifeTime(
                std::max(m_activeRouteTimeout, toOrigin.GetLifeTime()));
            m_routingTable.Update(toOrigin);
        }
        else
        {
            toOrigin.SetLifeTime(std::max(m_activeRouteTimeout, toOrigin.GetLifeTime()));
            m_routingTable.Update(toOrigin);
        }
    }
    m_routingTable.LookupRoute(origin, toOrigin);

    // A black-hole answers every request itself, claiming a one-hop route with
    // an unbeatable cost, and never forwards the request onward.
    if (m_attack == ATTACK_BLACKHOLE && !IsMyOwnAddress(rreqHeader.GetDst()))
    {
        SendFakeReply(rreqHeader, src, receiver);
        return;
    }

    if (IsMyOwnAddress(rreqHeader.GetDst()))
    {
        if (rreqHeader.GetDstSeqno() == m_seqNo + 1 || rreqHeader.GetUnknownSeqno())
        {
            m_seqNo++;
        }
        NS_LOG_DEBUG(MainAddress() << " is the destination of RREQ " << rreqHeader.GetId()
                                   << " from " << origin << ", replying via "
                                   << toOrigin.GetNextHop());
        SendReply(rreqHeader, toOrigin);
        return;
    }

    // base.pdf 3.5: a node below the energy threshold does not relay requests,
    // so it never ends up on a new route.
    if (!EnergyGateOpen())
    {
        return;
    }
    if (hops >= std::min<uint32_t>(m_netDiameter, rreqHeader.GetTtl()) || !mayForward)
    {
        return;
    }

    // Self-pruning: stay quiet when every neighbour we could reach has already
    // heard this request from the node we heard it from.
    if (m_floodSuppression &&
        m_neighbors.AdditionalCoverage(src, m_linkQualityThreshold) < m_minAdditionalCoverage)
    {
        return;
    }
    m_rreqForwards[key]++;

    rreqHeader.SetHopCount(hops);
    rreqHeader.SetPathCost(cost);
    for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
    {
        Ptr<Socket> socket = j->first;
        Ipv4InterfaceAddress ifaceOut = j->second;
        Ptr<Packet> packet = Create<Packet>();
        packet->AddHeader(rreqHeader);
        packet->AddHeader(TypeHeader(AREAURP_RREQ));
        Ipv4Address destination = (ifaceOut.GetMask() == Ipv4Mask::GetOnes())
                                      ? Ipv4Address("255.255.255.255")
                                      : ifaceOut.GetBroadcast();
        Oracle::Get().CountControl(AREAURP_RREQ, packet->GetSize());
        Simulator::Schedule(MilliSeconds(m_uniform->GetInteger(0, 10)),
                            &RoutingProtocol::SendTo,
                            this,
                            socket,
                            packet,
                            destination);
    }
}

void
RoutingProtocol::SendReply(const RreqHeader& rreqHeader, const RoutingTableEntry& toOrigin)
{
    RrepHeader rrepHeader(0,
                          0,
                          rreqHeader.GetDst(),
                          m_seqNo,
                          toOrigin.GetDestination(),
                          m_activeRouteTimeout,
                          0);
    rrepHeader.SetPolicy(rreqHeader.GetPolicy());
    Ptr<Packet> packet = Create<Packet>();
    packet->AddHeader(rrepHeader);
    packet->AddHeader(TypeHeader(AREAURP_RREP));

    Ptr<Socket> socket = nullptr;
    for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
    {
        if (j->second.GetLocal() == toOrigin.GetInterface().GetLocal())
        {
            socket = j->first;
            break;
        }
    }
    if (!socket)
    {
        NS_LOG_DEBUG("no socket matching interface " << toOrigin.GetInterface().GetLocal());
        return;
    }
    Oracle::Get().CountControl(AREAURP_RREP, packet->GetSize());
    socket->SendTo(packet, 0, InetSocketAddress(toOrigin.GetNextHop(), AR_EAURP_PORT));
}

void
RoutingProtocol::SendReplyByIntermediateNode(const RoutingTableEntry& toDst,
                                             const RoutingTableEntry& toOrigin,
                                             const RreqHeader& rreqHeader,
                                             uint32_t costSoFar)
{
    RrepHeader rrepHeader(0,
                          toDst.GetHop(),
                          toDst.GetDestination(),
                          toDst.GetSeqNo(),
                          toOrigin.GetDestination(),
                          toDst.GetLifeTime(),
                          costSoFar + toDst.GetPathCost());
    rrepHeader.SetPolicy(rreqHeader.GetPolicy());

    Ptr<Packet> packet = Create<Packet>();
    packet->AddHeader(rrepHeader);
    packet->AddHeader(TypeHeader(AREAURP_RREP));

    Ptr<Socket> socket = nullptr;
    for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
    {
        if (j->second.GetLocal() == toOrigin.GetInterface().GetLocal())
        {
            socket = j->first;
            break;
        }
    }
    if (!socket)
    {
        return;
    }

    // Remember that the originator's side of the path now depends on us, so a
    // later break on our side can be reported back to it.
    RoutingTableEntry entry = toDst;
    entry.InsertPrecursor(toOrigin.GetNextHop());
    m_routingTable.Update(entry);

    Oracle::Get().CountControl(AREAURP_RREP, packet->GetSize());
    socket->SendTo(packet, 0, InetSocketAddress(toOrigin.GetNextHop(), AR_EAURP_PORT));
}

void
RoutingProtocol::SendFakeReply(const RreqHeader& rreqHeader, Ipv4Address src, Ipv4Address receiver)
{
    // The lie: "I am one hop from the destination, on a perfect path." The
    // sequence number is bumped well past anything the originator has seen so
    // that the reply also looks fresher than the truth.
    RrepHeader rrepHeader(0,
                          1,
                          rreqHeader.GetDst(),
                          rreqHeader.GetDstSeqno() + 100,
                          rreqHeader.GetOrigin(),
                          m_activeRouteTimeout,
                          0);
    rrepHeader.SetPolicy(rreqHeader.GetPolicy());
    Ptr<Packet> packet = Create<Packet>();
    packet->AddHeader(rrepHeader);
    packet->AddHeader(TypeHeader(AREAURP_RREP));

    Ptr<Socket> socket = nullptr;
    for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
    {
        if (j->second.GetLocal() == receiver)
        {
            socket = j->first;
            break;
        }
    }
    if (!socket)
    {
        return;
    }
    Oracle::Get().CountControl(AREAURP_RREP, packet->GetSize());
    socket->SendTo(packet, 0, InetSocketAddress(src, AR_EAURP_PORT));
}

void
RoutingProtocol::RecvReply(Ptr<Packet> p, Ipv4Address receiver, Ipv4Address sender)
{
    RrepHeader rrepHeader;
    p->RemoveHeader(rrepHeader);

    if (!m_neighbors.IsUsableLink(sender, m_linkQualityThreshold))
    {
        NS_LOG_DEBUG(MainAddress() << " REJECT-RREP link to " << sender << " unusable (q="
                                   << m_neighbors.GetQuality(sender) << ")");
        return;
    }

    const uint8_t policy = rrepHeader.GetPolicy();
    const uint16_t hops = rrepHeader.GetHopCount() + 1;
    const uint32_t cost = rrepHeader.GetPathCost() + HopCostMilli(sender, policy);
    const Ipv4Address dst = rrepHeader.GetDst();

    UpdateRouteToNeighbor(sender, receiver);

    Ptr<NetDevice> dev = m_ipv4->GetNetDevice(m_ipv4->GetInterfaceForAddress(receiver));
    Ipv4InterfaceAddress iface = m_ipv4->GetAddress(m_ipv4->GetInterfaceForAddress(receiver), 0);

    const bool amOrigin = IsMyOwnAddress(rrepHeader.GetOrigin());

    // Route diversification: when the agent asked for a different path, the
    // originator refuses to reinstall the relay it was already using -- unless
    // this is the last attempt, in which case any route beats none.
    if (amOrigin && policy == ACTION_DIVERSE)
    {
        auto last = m_lastNextHop.find(dst);
        RoutingTableEntry probe;
        const bool lastTry =
            m_routingTable.LookupRoute(dst, probe) && probe.GetRreqCnt() >= m_rreqRetriesMax;
        if (last != m_lastNextHop.end() && last->second == sender && !lastTry)
        {
            return;
        }
    }

    RoutingTableEntry toDst;
    RoutingTableEntry newEntry(dev,
                               dst,
                               true,
                               rrepHeader.GetDstSeqno(),
                               iface,
                               hops,
                               sender,
                               rrepHeader.GetLifeTime(),
                               cost);
    bool installed = false;
    if (!m_routingTable.LookupRoute(dst, toDst))
    {
        m_routingTable.AddRoute(newEntry);
        installed = true;
    }
    else
    {
        const bool fresher = (int32_t)(rrepHeader.GetDstSeqno() - toDst.GetSeqNo()) > 0;
        const bool cheaper = (rrepHeader.GetDstSeqno() == toDst.GetSeqNo()) &&
                             (cost < toDst.GetPathCost());
        if (toDst.GetFlag() != VALID || fresher || cheaper)
        {
            m_routingTable.Update(newEntry);
            installed = true;
        }
    }

    NS_LOG_DEBUG(MainAddress() << " RREP for " << dst << " from " << sender << " origin "
                               << rrepHeader.GetOrigin() << " amOrigin=" << amOrigin
                               << " hops=" << hops);
    if (amOrigin)
    {
        if (installed)
        {
            auto timer = m_rreqTimers.find(dst);
            if (timer != m_rreqTimers.end())
            {
                timer->second.Cancel();
            }
            m_lastNextHop[dst] = sender;
            Oracle::Get().CountRouteDiscovery(true);
            RoutingTableEntry rt;
            if (m_routingTable.LookupValidRoute(dst, rt))
            {
                SendPacketFromQueue(dst, rt.GetRoute());
            }
        }
        return;
    }

    // Forward the reply back along the reverse path.
    RoutingTableEntry toOrigin;
    if (!m_routingTable.LookupValidRoute(rrepHeader.GetOrigin(), toOrigin))
    {
        NS_LOG_DEBUG(MainAddress() << " cannot forward RREP: no reverse route to "
                                   << rrepHeader.GetOrigin());
        return;
    }
    if (!EnergyGateOpen())
    {
        return;
    }
    if (toOrigin.GetFlag() == VALID)
    {
        RoutingTableEntry precursorEntry;
        if (m_routingTable.LookupRoute(dst, precursorEntry))
        {
            precursorEntry.InsertPrecursor(toOrigin.GetNextHop());
            m_routingTable.Update(precursorEntry);
        }
    }

    rrepHeader.SetHopCount(hops);
    rrepHeader.SetPathCost(cost);
    Ptr<Packet> packet = Create<Packet>();
    packet->AddHeader(rrepHeader);
    packet->AddHeader(TypeHeader(AREAURP_RREP));

    Ptr<Socket> socket = nullptr;
    for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
    {
        if (j->second.GetLocal() == toOrigin.GetInterface().GetLocal())
        {
            socket = j->first;
            break;
        }
    }
    if (!socket)
    {
        return;
    }
    Oracle::Get().CountControl(AREAURP_RREP, packet->GetSize());
    socket->SendTo(packet, 0, InetSocketAddress(toOrigin.GetNextHop(), AR_EAURP_PORT));
}

void
RoutingProtocol::SendPacketFromQueue(Ipv4Address dst, Ptr<Ipv4Route> route)
{
    for (auto i = m_queue.begin(); i != m_queue.end();)
    {
        if (i->header.GetDestination() != dst || i->expire < Simulator::Now())
        {
            if (i->expire < Simulator::Now())
            {
                Oracle::Get().CountQueueDrop(false);
                i = m_queue.erase(i);
                continue;
            }
            ++i;
            continue;
        }
        QueueEntry e = *i;
        i = m_queue.erase(i);
        if (e.header.GetSource().IsBroadcast() || e.header.GetSource().IsMulticast())
        {
            continue;
        }
        if (!e.ucb.IsNull())
        {
            Oracle::Get().CountDequeued();
            e.ucb(route, e.packet, e.header);
        }
    }
}

void
RoutingProtocol::RecvError(Ptr<Packet> p, Ipv4Address src)
{
    RerrHeader rerrHeader;
    p->RemoveHeader(rerrHeader);

    std::map<Ipv4Address, uint32_t> unreachable;
    m_routingTable.GetListOfDestinationWithNextHop(src, unreachable);

    std::pair<Ipv4Address, uint32_t> un;
    while (rerrHeader.RemoveUnDestination(un))
    {
        for (auto i = unreachable.begin(); i != unreachable.end();)
        {
            if (i->first == un.first)
            {
                i = unreachable.erase(i);
            }
            else
            {
                ++i;
            }
        }
        RoutingTableEntry toDst;
        if (m_routingTable.LookupValidRoute(un.first, toDst) && toDst.GetNextHop() == src)
        {
            toDst.Invalidate(m_routingTable.GetBadLinkLifetime());
            m_routingTable.Update(toDst);
        }
    }
    m_routingTable.InvalidateRoutesWithDst(unreachable);
}

void
RoutingProtocol::SendRerrWhenBreaksLinkToNextHop(Ipv4Address nextHop)
{
    RerrHeader rerrHeader;
    std::map<Ipv4Address, uint32_t> unreachable;
    m_routingTable.GetListOfDestinationWithNextHop(nextHop, unreachable);
    if (unreachable.empty())
    {
        return;
    }

    std::vector<Ipv4Address> precursors;
    for (auto i = unreachable.begin(); i != unreachable.end(); ++i)
    {
        rerrHeader.AddUnDestination(i->first, i->second);
        RoutingTableEntry entry;
        if (m_routingTable.LookupRoute(i->first, entry))
        {
            entry.GetPrecursors(precursors);
        }
    }
    if (rerrHeader.GetDestCount() == 0)
    {
        return;
    }
    Ptr<Packet> packet = Create<Packet>();
    packet->AddHeader(rerrHeader);
    packet->AddHeader(TypeHeader(AREAURP_RERR));
    SendRerrMessage(packet, precursors);
    m_routingTable.InvalidateRoutesWithNextHop(nextHop, m_routingTable.GetBadLinkLifetime());
}

void
RoutingProtocol::SendRerrMessage(Ptr<Packet> packet, std::vector<Ipv4Address> precursors)
{
    if (precursors.empty())
    {
        return;
    }
    Oracle::Get().CountControl(AREAURP_RERR, packet->GetSize());

    if (precursors.size() == 1)
    {
        RoutingTableEntry toPrecursor;
        if (m_routingTable.LookupValidRoute(precursors.front(), toPrecursor))
        {
            Ptr<Socket> socket = nullptr;
            for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
            {
                if (j->second.GetLocal() == toPrecursor.GetInterface().GetLocal())
                {
                    socket = j->first;
                    break;
                }
            }
            if (socket)
            {
                socket->SendTo(packet->Copy(), 0, InetSocketAddress(precursors.front(), AR_EAURP_PORT));
            }
        }
        return;
    }

    for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
    {
        Ptr<Socket> socket = j->first;
        Ipv4InterfaceAddress iface = j->second;
        Ipv4Address destination = (iface.GetMask() == Ipv4Mask::GetOnes())
                                      ? Ipv4Address("255.255.255.255")
                                      : iface.GetBroadcast();
        socket->SendTo(packet->Copy(), 0, InetSocketAddress(destination, AR_EAURP_PORT));
    }
}

// ------------------------------------------------------------ trust plane ---

void
RoutingProtocol::SendNid()
{
    // Node death: once the battery is empty the radio is gone, and so is the
    // node. Recorded once, for the lifetime metric.
    if (m_energySource && !m_reportedDeath && m_energySource->GetRemainingEnergy() <= 0.0)
    {
        m_reportedDeath = true;
        Oracle::Get().ReportNodeDeath(m_ipv4->GetObject<Node>()->GetId(), Simulator::Now());
    }

    // Link sensing. A neighbour that has stopped beaconing is gone, and every
    // route through it is stale. Saying so costs one RERR; not saying so costs
    // every packet the flow sends into the gap until the route times out.
    if (m_variant != VARIANT_AODV)
    {
        std::vector<Ipv4Address> lost;
        for (const auto& kv : m_neighbors.Table())
        {
            if (kv.second.expire > Seconds(0) && kv.second.expire <= Simulator::Now())
            {
                lost.push_back(kv.first);
            }
        }
        for (const Ipv4Address& gone : lost)
        {
            SendRerrWhenBreaksLinkToNextHop(gone);
        }
    }

    m_neighbors.Purge();
    m_neighbors.RefreshTrust();
    m_neighbors.ExpireContested();

    m_neighbors.TickLinkQuality(m_linkQualityWeight,
                                m_linkQualityInitial,
                                m_linkQualityThreshold,
                                m_linkQualityThreshold * 0.6);

    {
        // Every variant beacons. For plain AODV this is exactly RFC 3561's
        // HELLO -- neighbour presence and nothing else; the trust plane adds
        // the forwarding ratios on top of the same packet.
        NidHeader nid;
        nid.SetOrigin(MainAddress());
        nid.SetEnergyFraction(EnergyFraction());
        nid.SetSurplus(PredictedSurplus());
        if (m_variant == VARIANT_DRL_SENIOR)
        {
            nid.AddRatio(MainAddress(), m_endpointTrust.Trust());
        }

        for (const auto& kv : m_neighbors.Table())
        {
            if (kv.second.expire > Simulator::Now())
            {
                // Link sensing: tell this neighbour we can hear it, so it can
                // tell whether the link works in both directions.
                nid.AddLink(kv.first);
            }
            // base.pdf 3.6: the forwarding ratios this node has measured. A
            // slanderer publishes something else.
            if (m_variant != VARIANT_AODV && m_variant != VARIANT_DRL_SENIOR &&
                kv.second.requested >= (double)m_minObservations)
            {
                nid.AddRatio(kv.first, PublishedTrust(kv.first, kv.second.trust));
            }
        }

        for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
        {
            Ptr<Socket> socket = j->first;
            Ipv4InterfaceAddress iface = j->second;
            Ptr<Packet> packet = Create<Packet>();
            packet->AddHeader(nid);
            packet->AddHeader(TypeHeader(AREAURP_NID));
            Ipv4Address destination = (iface.GetMask() == Ipv4Mask::GetOnes())
                                          ? Ipv4Address("255.255.255.255")
                                          : iface.GetBroadcast();
            Oracle::Get().CountControl(AREAURP_NID, packet->GetSize());
            Simulator::Schedule(MilliSeconds(m_uniform->GetInteger(0, 50)),
                                &RoutingProtocol::SendTo,
                                this,
                                socket,
                                packet,
                                destination);
        }
    }
    m_nidTimer.Schedule(m_nidInterval + MilliSeconds(m_uniform->GetInteger(0, 200)));
}

void
RoutingProtocol::RecvNid(Ptr<Packet> p, Ipv4Address src)
{
    NidHeader nid;
    p->RemoveHeader(nid);

    m_neighbors.Refresh(nid.GetOrigin(), Mac48Address(), nid.GetEnergyFraction(), nid.GetSurplus());

    bool heardMe = false;
    for (const Ipv4Address& l : nid.GetLinks())
    {
        if (IsMyOwnAddress(l))
        {
            heardMe = true;
            break;
        }
    }
    m_neighbors.NoteBeacon(nid.GetOrigin(), heardMe, 3 * m_nidInterval);
    m_neighbors.NoteAdvertisedNeighbours(nid.GetOrigin(), nid.GetLinks());

    for (const auto& r : nid.GetRatios())
    {
        if (m_variant == VARIANT_DRL_SENIOR && r.first == nid.GetOrigin())
        {
            m_endpointReports[nid.GetOrigin()] = r.second;
            continue;
        }
        if (!IsMyOwnAddress(r.first))
        {
            m_neighbors.AddOpinion(nid.GetOrigin(), r.first, r.second);
        }
    }
    (void)src;
}

void
RoutingProtocol::SendGid()
{
    if (m_variant == VARIANT_AODV || m_variant == VARIANT_DRL_SENIOR)
    {
        m_gidTimer.Schedule(m_gidInterval);
        return;
    }

    GidHeader gid;
    gid.SetOrigin(MainAddress());
    gid.SetSeq(++m_gidSeq);
    // One hop. A node's accusers are by definition its neighbours, and in a
    // unit-disk graph two neighbours of the same node are themselves adjacent
    // about half the time, so a one-hop vote reaches enough corroborators to
    // work. A two-hop scoped flood would have every node rebroadcasting every
    // other node's vote -- O(N^2) transmissions per round, which on a 2 Mbit/s
    // shared channel costs more than the traffic the protocol exists to carry.
    gid.SetTtl(m_gidTtl);

    for (const auto& kv : m_neighbors.Table())
    {
        if (kv.second.requested >= (double)m_minObservations)
        {
            gid.AddOpinion(kv.first, PublishedTrust(kv.first, kv.second.trust));
        }
    }

    if (gid.GetOpinions().empty())
    {
        RunConsensus();
        m_gidTimer.Schedule(m_gidInterval + MilliSeconds(m_uniform->GetInteger(0, 1000)));
        return;
    }

    m_floodSeen.insert(std::make_pair(gid.GetOrigin(), gid.GetSeq()));
    for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
    {
        Ptr<Socket> socket = j->first;
        Ipv4InterfaceAddress iface = j->second;
        Ptr<Packet> packet = Create<Packet>();
        packet->AddHeader(gid);
        packet->AddHeader(TypeHeader(AREAURP_GID));
        Ipv4Address destination = (iface.GetMask() == Ipv4Mask::GetOnes())
                                      ? Ipv4Address("255.255.255.255")
                                      : iface.GetBroadcast();
        Oracle::Get().CountControl(AREAURP_GID, packet->GetSize());
        Simulator::Schedule(MilliSeconds(m_uniform->GetInteger(0, 50)),
                            &RoutingProtocol::SendTo,
                            this,
                            socket,
                            packet,
                            destination);
    }

    RunConsensus();
    m_gidTimer.Schedule(m_gidInterval + MilliSeconds(m_uniform->GetInteger(0, 1000)));
}

void
RoutingProtocol::RecvGid(Ptr<Packet> p, Ipv4Address src, Ipv4Address receiver)
{
    GidHeader gid;
    p->RemoveHeader(gid);

    const auto key = std::make_pair(gid.GetOrigin(), gid.GetSeq());
    if (m_floodSeen.count(key))
    {
        return;
    }
    m_floodSeen.insert(key);

    for (const auto& o : gid.GetOpinions())
    {
        if (!IsMyOwnAddress(o.first))
        {
            m_neighbors.AddOpinion(gid.GetOrigin(), o.first, o.second);
        }
    }

    // Scoped reflood so that every watcher of an accused node hears the vote,
    // even when two watchers cannot hear each other directly.
    if (gid.GetTtl() > 1 && EnergyGateOpen())
    {
        gid.SetTtl(gid.GetTtl() - 1);
        for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
        {
            Ptr<Socket> socket = j->first;
            Ipv4InterfaceAddress iface = j->second;
            Ptr<Packet> packet = Create<Packet>();
            packet->AddHeader(gid);
            packet->AddHeader(TypeHeader(AREAURP_GID));
            Ipv4Address destination = (iface.GetMask() == Ipv4Mask::GetOnes())
                                          ? Ipv4Address("255.255.255.255")
                                          : iface.GetBroadcast();
            Oracle::Get().CountControl(AREAURP_GID, packet->GetSize());
            Simulator::Schedule(MilliSeconds(m_uniform->GetInteger(0, 30)),
                                &RoutingProtocol::SendTo,
                                this,
                                socket,
                                packet,
                                destination);
        }
    }
    (void)src;
    (void)receiver;
}

void
RoutingProtocol::RunConsensus()
{
    if (m_variant == VARIANT_AODV || m_variant == VARIANT_DRL_SENIOR) return;
    // Opinions go stale: a vote must be about recent behaviour.
    m_neighbors.PurgeOpinions(4 * m_gidInterval);

    // Our own measurements count as one vote, like everybody else's.
    for (const auto& kv : m_neighbors.Table())
    {
        if (kv.second.requested >= (double)m_minObservations)
        {
            m_neighbors.AddOpinion(MainAddress(), kv.first, kv.second.trust);
        }
    }

    const std::vector<Ipv4Address> condemned = m_neighbors.Consensus(m_consensusFraction,
                                                                    m_minAccusers,
                                                                    m_energyExcuse,
                                                                    m_energyThreshold);
    for (const Ipv4Address& subject : condemned)
    {
        ApplyRevocation(subject, (uint8_t)m_minAccusers, true);
    }
}

void
RoutingProtocol::ApplyRevocation(Ipv4Address subject, uint8_t evidence, bool originator)
{
    if (m_neighbors.IsRevoked(subject) || IsMyOwnAddress(subject))
    {
        return;
    }
    m_neighbors.Revoke(subject);
    Oracle::Get().ReportRevoked(MainAddress(), subject);

    // base.pdf 3.8: every route through a revoked node is torn down at once.
    SendRerrWhenBreaksLinkToNextHop(subject);
    m_routingTable.InvalidateRoutesWithNextHop(subject, m_routingTable.GetBadLinkLifetime());

    if (!originator)
    {
        return;
    }

    CrevHeader crev;
    crev.SetOrigin(MainAddress());
    crev.SetRevoked(subject);
    crev.SetSeq(++m_gidSeq);
    crev.SetTtl(6);
    crev.SetEvidence(evidence);
    m_floodSeen.insert(std::make_pair(crev.GetOrigin(), crev.GetSeq()));

    for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
    {
        Ptr<Socket> socket = j->first;
        Ipv4InterfaceAddress iface = j->second;
        Ptr<Packet> packet = Create<Packet>();
        packet->AddHeader(crev);
        packet->AddHeader(TypeHeader(AREAURP_CREV));
        Ipv4Address destination = (iface.GetMask() == Ipv4Mask::GetOnes())
                                      ? Ipv4Address("255.255.255.255")
                                      : iface.GetBroadcast();
        Oracle::Get().CountControl(AREAURP_CREV, packet->GetSize());
        Simulator::Schedule(MilliSeconds(m_uniform->GetInteger(0, 30)),
                            &RoutingProtocol::SendTo,
                            this,
                            socket,
                            packet,
                            destination);
    }
}

void
RoutingProtocol::RecvCrev(Ptr<Packet> p, Ipv4Address src, Ipv4Address receiver)
{
    if (m_variant == VARIANT_AODV || m_variant == VARIANT_DRL_SENIOR) return;
    CrevHeader crev;
    p->RemoveHeader(crev);

    const auto key = std::make_pair(crev.GetOrigin(), crev.GetSeq());
    if (m_floodSeen.count(key))
    {
        return;
    }
    m_floodSeen.insert(key);

    const Ipv4Address subject = crev.GetRevoked();
    if (!IsMyOwnAddress(subject))
    {
        m_crevHeard[subject].insert(crev.GetOrigin());

        // A revocation is not accepted on one node's say-so: either we have
        // watched the accused misbehave ourselves, or at least two independent
        // nodes have issued the same revocation. Otherwise a single slanderer
        // could revoke anybody it liked simply by shouting.
        const bool corroborated =
            (m_neighbors.GetTrust(subject) < m_trustThreshold) || (m_crevHeard[subject].size() >= 2);
        if (corroborated)
        {
            ApplyRevocation(subject, crev.GetEvidence(), false);
        }
    }

    if (crev.GetTtl() > 1 && EnergyGateOpen())
    {
        crev.SetTtl(crev.GetTtl() - 1);
        for (auto j = m_socketAddresses.begin(); j != m_socketAddresses.end(); ++j)
        {
            Ptr<Socket> socket = j->first;
            Ipv4InterfaceAddress iface = j->second;
            Ptr<Packet> packet = Create<Packet>();
            packet->AddHeader(crev);
            packet->AddHeader(TypeHeader(AREAURP_CREV));
            Ipv4Address destination = (iface.GetMask() == Ipv4Mask::GetOnes())
                                          ? Ipv4Address("255.255.255.255")
                                          : iface.GetBroadcast();
            Oracle::Get().CountControl(AREAURP_CREV, packet->GetSize());
            Simulator::Schedule(MilliSeconds(m_uniform->GetInteger(0, 30)),
                                &RoutingProtocol::SendTo,
                                this,
                                socket,
                                packet,
                                destination);
        }
    }
    (void)src;
    (void)receiver;
}

// ---------------------------------------------------------------- watchdog ---

uint64_t
RoutingProtocol::DigestFromIpFrame(Ptr<const Packet> ipFrame, bool& isControl)
{
    isControl = false;
    Ptr<Packet> copy = ipFrame->Copy();
    Ipv4Header ip;
    if (copy->GetSize() < ip.GetSerializedSize())
    {
        return 0;
    }
    copy->RemoveHeader(ip);

    if (ip.GetProtocol() == UdpL4Protocol::PROT_NUMBER)
    {
        UdpHeader udp;
        Ptr<Packet> probe = copy->Copy();
        if (probe->GetSize() >= udp.GetSerializedSize())
        {
            probe->RemoveHeader(udp);
            if (udp.GetDestinationPort() == AR_EAURP_PORT)
            {
                isControl = true;
                return 0;
            }
        }
    }

    // FNV-1a over the endpoints, the payload length and its first bytes. Those
    // bytes survive forwarding untouched -- only the IP TTL and checksum
    // change -- so the relay's copy hashes to the same value as ours.
    uint64_t h = 1469598103934665603ULL;
    auto mix = [&h](uint64_t v) {
        for (int i = 0; i < 8; ++i)
        {
            h ^= (v >> (8 * i)) & 0xFF;
            h *= 1099511628211ULL;
        }
    };
    mix(ip.GetSource().Get());
    mix(ip.GetDestination().Get());
    mix(copy->GetSize());

    uint8_t buffer[16] = {0};
    const uint32_t n = std::min<uint32_t>(16, copy->GetSize());
    copy->CopyData(buffer, n);
    for (uint32_t i = 0; i < n; ++i)
    {
        h ^= buffer[i];
        h *= 1099511628211ULL;
    }
    return h;
}

void
RoutingProtocol::NotifyPhyTx(Ptr<const Packet> frame, double txPowerW)
{
    (void)txPowerW;
    if (m_variant == VARIANT_AODV)
    {
        return;
    }

    Ptr<Packet> copy = frame->Copy();
    WifiMacHeader mac;
    if (copy->GetSize() < mac.GetSerializedSize())
    {
        return;
    }
    copy->RemoveHeader(mac);
    // The PSDU carries the 802.11 FCS trailer; the observer's copy will not,
    // because the device strips it before handing the frame up. Remove it here
    // or the two sides hash different lengths and no observation ever matches.
    WifiMacTrailer fcs;
    if (copy->GetSize() >= fcs.GetSerializedSize())
    {
        copy->RemoveTrailer(fcs);
    }
    if (!mac.IsData() || mac.IsRetry())
    {
        return; // retransmissions are the same packet, not a new request
    }
    if (mac.GetAddr1().IsBroadcast() || mac.GetAddr1().IsGroup())
    {
        return;
    }

    Ipv4Address nextHop;
    if (!LookupIpFromMac(mac.GetAddr1(), nextHop))
    {
        return;
    }

    LlcSnapHeader llc;
    if (copy->GetSize() < llc.GetSerializedSize())
    {
        return;
    }
    copy->RemoveHeader(llc);
    if (llc.GetType() != Ipv4L3Protocol::PROT_NUMBER)
    {
        return;
    }

    Ipv4Header ip;
    Ptr<Packet> probe = copy->Copy();
    if (probe->GetSize() < ip.GetSerializedSize())
    {
        return;
    }
    probe->PeekHeader(ip);
    if (ip.GetDestination() == nextHop)
    {
        return; // the next hop is the destination: there is nothing to relay
    }

    bool isControl = false;
    const uint64_t digest = DigestFromIpFrame(copy, isControl);
    if (isControl || digest == 0)
    {
        return;
    }

    NS_LOG_DEBUG("ARM " << MainAddress() << " -> " << nextHop << " ipsrc=" << ip.GetSource()
                        << " ipdst=" << ip.GetDestination() << " framesize=" << copy->GetSize()
                        << " digest=" << digest);
    m_neighbors.ArmWatchdog(nextHop, digest, copy->GetSize() - ip.GetSerializedSize());
    Oracle::Get().CountWatchdogArmed();
}

void
RoutingProtocol::PromiscRx(Ptr<NetDevice> device,
                           Ptr<const Packet> packet,
                           uint16_t protocol,
                           const Address& from,
                           const Address& to,
                           NetDevice::PacketType type)
{
    (void)device;
    (void)to;
    (void)type;
    if (protocol != Ipv4L3Protocol::PROT_NUMBER || m_variant == VARIANT_AODV)
    {
        return;
    }
    if (!Mac48Address::IsMatchingType(from))
    {
        return;
    }
    const Mac48Address sender = Mac48Address::ConvertFrom(from);

    Ptr<Packet> copy = packet->Copy();
    Ipv4Header ipHeader;
    if (copy->GetSize() < ipHeader.GetSerializedSize())
    {
        return;
    }
    copy->RemoveHeader(ipHeader);

    // Learn which MAC belongs to which neighbour from its PT_NID beacon; the
    // watchdog needs that binding to know who just transmitted.
    if (ipHeader.GetProtocol() == UdpL4Protocol::PROT_NUMBER)
    {
        UdpHeader udp;
        Ptr<Packet> probe = copy->Copy();
        probe->RemoveHeader(udp);
        if (udp.GetDestinationPort() == AR_EAURP_PORT)
        {
            TypeHeader th(AREAURP_RREQ);
            probe->RemoveHeader(th);
            if (th.IsValid() && th.Get() == AREAURP_NID)
            {
                NidHeader nid;
                probe->RemoveHeader(nid);
                m_neighbors.BindMac(sender, nid.GetOrigin());
                SeedArpCache(nid.GetOrigin(), sender);
            }
            return; // control traffic is not what the watchdog counts
        }
    }

    // A data frame: does it match something we asked this neighbour to relay?
    bool isControl = false;
    const uint64_t digest = DigestFromIpFrame(packet, isControl);
    if (!isControl && digest != 0)
    {
        NS_LOG_DEBUG("HEAR " << MainAddress() << " from mac " << sender
                             << " ipsrc=" << ipHeader.GetSource()
                             << " ipdst=" << ipHeader.GetDestination()
                             << " framesize=" << packet->GetSize() << " digest=" << digest);
    }
    if (!isControl && digest != 0 && m_neighbors.ConfirmWatchdog(sender, digest))
    {
        Oracle::Get().CountWatchdogConfirmed();
    }
}

bool
RoutingProtocol::LookupIpFromMac(Mac48Address mac, Ipv4Address& addr) const
{
    if (m_neighbors.LookupMac(mac, addr))
    {
        return true;
    }
    // Fall back to the ARP cache, which is populated for every neighbour we
    // have actually sent a unicast frame to -- including in the plain-AODV
    // variant, which sends no PT_NID beacons to learn bindings from.
    Ptr<Ipv4L3Protocol> l3 = m_ipv4->GetObject<Ipv4L3Protocol>();
    if (!l3)
    {
        return false;
    }
    for (uint32_t i = 0; i < l3->GetNInterfaces(); ++i)
    {
        Ptr<ArpCache> cache = l3->GetInterface(i)->GetArpCache();
        if (!cache)
        {
            continue;
        }
        std::list<ArpCache::Entry*> entries = cache->LookupInverse(mac);
        if (!entries.empty() && entries.front())
        {
            addr = entries.front()->GetIpv4Address();
            return true;
        }
    }
    return false;
}

void
RoutingProtocol::SeedArpCache(Ipv4Address addr, Mac48Address mac)
{
    Ptr<Ipv4L3Protocol> l3 = m_ipv4->GetObject<Ipv4L3Protocol>();
    if (!l3)
    {
        return;
    }
    for (uint32_t i = 0; i < l3->GetNInterfaces(); ++i)
    {
        Ptr<Ipv4Interface> iface = l3->GetInterface(i);
        if (!iface)
        {
            continue;
        }
        Ptr<ArpCache> cache = iface->GetArpCache();
        if (!cache)
        {
            continue;
        }
        ArpCache::Entry* entry = cache->Lookup(addr);
        if (!entry)
        {
            entry = cache->Add(addr);
            entry->SetMacAddress(mac);
            entry->MarkAutoGenerated();
        }
        else if (!entry->IsAlive() && !entry->IsPermanent())
        {
            entry->SetMacAddress(mac);
            entry->MarkAutoGenerated();
        }
    }
}

void
RoutingProtocol::NotifyTxError(WifiMacDropReason reason, Ptr<const WifiMpdu> mpdu)
{
    if (reason != WIFI_MAC_DROP_REACHED_RETRY_LIMIT)
    {
        return;
    }
    const WifiMacHeader& hdr = mpdu->GetHeader();
    if (hdr.GetAddr1().IsBroadcast() || hdr.GetAddr1().IsGroup())
    {
        return;
    }
    Ipv4Address peer;
    if (!LookupIpFromMac(hdr.GetAddr1(), peer))
    {
        Oracle::Get().CountLinkFailure(false);
        return;
    }
    Oracle::Get().CountLinkFailure(true);

    // The frame never reached the neighbour, so withdraw the watchdog entry we
    // armed for it: this was our link failing, not the relay misbehaving.
    Ptr<Packet> copy = mpdu->GetPacket()->Copy();
    LlcSnapHeader llc;
    if (copy->GetSize() > llc.GetSerializedSize())
    {
        copy->RemoveHeader(llc);
        if (llc.GetType() == Ipv4L3Protocol::PROT_NUMBER)
        {
            bool isControl = false;
            const uint64_t digest = DigestFromIpFrame(copy, isControl);
            if (!isControl && digest != 0)
            {
                m_neighbors.CancelWatchdog(peer, digest);
            }
        }
    }

    SendRerrWhenBreaksLinkToNextHop(peer);
}

void
RoutingProtocol::SweepWatchdogs()
{
    m_neighbors.ExpireWatchdogs();
    m_watchdogTimer.Schedule(MilliSeconds(200));
}

// --------------------------------------------------------------- AR-EAURP ---

void
RoutingProtocol::SampleHarvest()
{
    Ptr<Node> node = m_ipv4->GetObject<Node>();
    Ptr<energy::EnergyHarvesterContainer> harvesters =
        node->GetObject<energy::EnergyHarvesterContainer>();
    if (harvesters && harvesters->GetN() > 0)
    {
        Ptr<SolarEnergyHarvester> solar = DynamicCast<SolarEnergyHarvester>(harvesters->Get(0));
        if (solar)
        {
            const double watts = solar->CurrentPower();
            const double phase = solar->DayPhase();
            m_harvestHistory.emplace_back(watts, phase);
            if (m_harvestHistory.size() > 64)
            {
                m_harvestHistory.pop_front();
            }
            EnergyForecaster* forecaster = Oracle::Get().Forecaster();
            if (forecaster && Oracle::Get().Phase() == PHASE_COMMISSIONING)
            {
                forecaster->AddSample(node->GetId(), watts, phase);
            }
            else if (m_useLstm && forecaster && forecaster->IsTrained())
            {
                m_lastSurplus = forecaster->Predict(m_harvestHistory);
            }
        }
    }
    m_harvestTimer.Schedule(Seconds(1));
}

double
RoutingProtocol::PredictedSurplus() const
{
    if (m_variant != VARIANT_AR_EAURP || !m_useLstm)
    {
        return 0.0;
    }
    // Normalised against a nominal 1.5 W panel so that it shares a scale with
    // the battery fraction it is blended with.
    return std::min(1.0, m_lastSurplus / 1.5);
}

void
RoutingProtocol::RunDetection()
{
    if (m_variant != VARIANT_AR_EAURP || !m_useGan)
    {
        m_detectTimer.Schedule(m_detectInterval);
        return;
    }

    std::vector<Ipv4Address> subjects;
    std::vector<std::vector<double>> features;
    m_neighbors.ExtractFeatures(subjects, features, true, m_detectMinWindow);

    GanAnomalyDetector* detector = Oracle::Get().Detector();
    if (detector && Oracle::Get().Phase() == PHASE_COMMISSIONING)
    {
        // Commissioning: this is what healthy behaviour looks like.
        for (const auto& f : features)
        {
            detector->AddTrainingSample(f);
        }
    }
    else if (detector && detector->IsTrained())
    {
        for (size_t i = 0; i < subjects.size(); ++i)
        {
            const double score = detector->Score(features[i]);
            // Measurement only: the score paired with the ground truth, so the
            // detector can be scored as a classifier afterwards. The protocol
            // itself never sees the label.
            Oracle::Get().RecordDetectorScore(score, Oracle::Get().IsMalicious(subjects[i]));
            if (score > detector->Threshold())
            {
                m_neighbors.SetContested(subjects[i], Simulator::Now() + m_contestedTtl, score);
                Oracle::Get().ReportContested(MainAddress(), subjects[i]);
            }
        }
    }
    m_detectTimer.Schedule(m_detectInterval + MilliSeconds(m_uniform->GetInteger(0, 1000)));
}

uint32_t
RoutingProtocol::UsableNeighbours() const
{
    uint32_t count = 0;
    for (const auto& kv : m_neighbors.Table())
    {
        if (m_neighbors.IsUsableLink(kv.first, m_linkQualityThreshold))
        {
            count++;
        }
    }
    return count;
}

double
RoutingProtocol::MeanLinkQuality() const
{
    double sum = 0.0;
    uint32_t count = 0;
    for (const auto& kv : m_neighbors.Table())
    {
        if (kv.second.expire > Simulator::Now())
        {
            sum += kv.second.quality;
            count++;
        }
    }
    return (count > 0) ? sum / count : 0.0;
}

Vec
RoutingProtocol::BuildState() const
{
    double trustSum = 0.0;
    double contested = 0.0;
    uint32_t count = 0;
    for (const auto& kv : m_neighbors.Table())
    {
        if (kv.second.expire > Simulator::Now())
        {
            auto report = m_endpointReports.find(kv.first);
            trustSum += m_variant == VARIANT_DRL_SENIOR
                ? (report == m_endpointReports.end() ? 1.0 : report->second) : kv.second.trust;
            contested += kv.second.contested ? 1.0 : 0.0;
            count++;
        }
    }

    double speed = 0.0;
    Ptr<Node> node = m_ipv4->GetObject<Node>();
    Ptr<MobilityModel> mobility = node ? node->GetObject<MobilityModel>() : nullptr;
    if (mobility)
    {
        const Vector v = mobility->GetVelocity();
        speed = std::sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
    }

    Vec state(kStateDim, 0.0);
    state[0] = (count > 0) ? trustSum / count : 1.0;
    state[1] = EnergyFraction();
    state[2] = std::min(1.0, speed / 20.0);
    if (m_variant == VARIANT_DRL_PAPER || m_variant == VARIANT_DRL_SENIOR)
        state[2] = 1.0 - state[2];
    state[3] = PredictedSurplus();
    state[4] = (count > 0) ? contested / count : 0.0;
    state[5] = WindowPdr();
    return state;
}

void
RoutingProtocol::NotifyDelivery(Ipv4Address dst, bool delivered, uint32_t hops, uint64_t decisionId)
{
    (void)dst;
    m_attempted++;
    if (delivered)
    {
        m_delivered++;
    }
    m_deliveryWindow.push_back(delivered);
    if (m_deliveryWindow.size() > 100)
    {
        m_deliveryWindow.pop_front();
    }

    if (m_variant == VARIANT_DRL_PAPER || m_variant == VARIANT_DRL_SENIOR)
    {
        auto pending = m_decisionHistory.find(decisionId);
        if (pending != m_decisionHistory.end())
            m_tabular.Observe(pending->second.state, pending->second.action, delivered, BuildState());
        return;
    }
    if (m_variant != VARIANT_AR_EAURP || !m_useCmdp)
    {
        return;
    }
    CmdpAgent* agent = Oracle::Get().Agent();
    if (!agent || (Oracle::Get().Phase() != PHASE_EVALUATION &&
                   Oracle::Get().Phase() != PHASE_COMMISSIONING))
    {
        return;
    }

    auto i = m_decisionHistory.find(decisionId);
    if (i == m_decisionHistory.end())
    {
        return;
    }

    // Per-hop energy proxy for the reward. Battery reporting separately uses
    // the real Wi-Fi energy model; this estimate is not a battery measurement.
    const double perHopJoules = 2.0e-3;
    const double energyCost = (double)hops * perHopJoules * 1000.0;

    bool violated = false;
    const double reward = agent->ShapedReward(delivered, energyCost, WindowPdr(), violated);
    agent->Observe(i->second.state, i->second.action, reward, BuildState());

    if (m_attempted % 10 == 0)
    {
        agent->UpdateLambda(WindowPdr());
    }
}

} // namespace arEaurp
} // namespace ns3
