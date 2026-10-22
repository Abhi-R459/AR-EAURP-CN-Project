/*
 * AR-EAURP evaluation scenario.
 *
 * A mobile ad-hoc network of real ns-3 nodes: 802.11b radios on a Yans channel
 * with log-distance path loss and Nakagami fading, random-waypoint mobility at
 * walking-to-vehicle speeds, a real IPv4 stack, UDP flows of realistic packet
 * sizes, a battery per node with the measured current draw of an 802.11 card,
 * and -- for the harvesting experiments -- a photovoltaic panel with a diurnal
 * cycle and persistent cloud cover.
 *
 * Everything the protocol knows, it learns from packets that were actually
 * transmitted. The shared registry provisions learned models and collects
 * measurements; adversary ground truth is used only for scoring detection.
 *
 * Usage:
 *   ./ns3 run "ar-eaurp-sim --protocol=ar-eaurp --attack=grayhole --malicious=0.3"
 */

#include "ns3/applications-module.h"
#include "ns3/ar-eaurp-helper.h"
#include "ar-eaurp-scenario.h"
#include "ns3/ar-eaurp-oracle.h"
#include "ns3/ar-eaurp-routing-protocol.h"
#include "ns3/ar-traffic-app.h"
#include "ns3/ar-traffic-helper.h"
#include "ns3/aodv-module.h"
#include "ns3/basic-energy-source-helper.h"
#include "ns3/core-module.h"
#include "ns3/energy-module.h"
#include "ns3/flow-monitor-helper.h"
#include "ns3/ipv4-flow-classifier.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/netanim-module.h"
#include "ns3/solar-energy-harvester.h"
#include "ns3/wifi-module.h"
#include "ns3/wifi-radio-energy-model-helper.h"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using namespace ns3;
using namespace ns3::arEaurp;

NS_LOG_COMPONENT_DEFINE("ArEaurpSim");

/// IP-layer drop accounting, so that every packet that does not arrive can be
/// attributed to a cause rather than merely being missing.
static std::map<uint32_t, uint64_t> g_ipDrops;

static void
Ipv4DropTrace(const Ipv4Header& header,
              Ptr<const Packet> packet,
              Ipv4L3Protocol::DropReason reason,
              Ptr<Ipv4> ipv4,
              uint32_t interface)
{
    (void)header;
    (void)packet;
    (void)ipv4;
    (void)interface;
    if (Oracle::Get().Measuring()) g_ipDrops[(uint32_t)reason]++;
}

static void
MacTxDropTrace(Ptr<const Packet> packet)
{
    (void)packet;
    if (Oracle::Get().Measuring()) g_ipDrops[100]++;
}

// ns-3.45 reads the source while rescheduling a radio state. That read can
// synchronously call HandleEnergyChanged and create a shutdown event whose ID
// the outer call then overwrites. Guard those nested notifications so there is
// only one shutdown timer. All current accounting remains in ns-3's model.
class StableWifiRadioEnergyModel : public WifiRadioEnergyModel
{
  public:
    void ChangeState(int state) override
    {
        const bool previous = m_busy;
        m_busy = true;
        if (state == static_cast<int>(WifiPhyState::OFF) && !previous &&
            GetCurrentState() != WifiPhyState::OFF)
        {
            // The upstream shutdown timer divides charge by radio power and
            // omits concurrent harvesting. If charge remains, keep drawing
            // current and reschedule instead of silently turning the model
            // off while the PHY stays awake. A source depletion notification
            // during this read can synchronously put the PHY/model OFF.
            const auto current = GetCurrentState();
            const Time remaining = GetMaximumTimeInState(current);
            if (GetCurrentState() != WifiPhyState::OFF && remaining > NanoSeconds(1))
            {
                WifiRadioEnergyModel::ChangeState(static_cast<int>(current));
                m_busy = previous;
                return;
            }
        }
        WifiRadioEnergyModel::ChangeState(state);
        // A quantised exhausted remainder can bypass the source's relative
        // threshold. Shut down the PHY as well as its energy model.
        if (state == static_cast<int>(WifiPhyState::OFF) && !previous)
            HandleEnergyDepletion();
        m_busy = previous;
    }
    void HandleEnergyChanged() override
    {
        if (m_busy) return;
        m_busy = true;
        WifiRadioEnergyModel::HandleEnergyChanged();
        m_busy = false;
    }
  private:
    bool m_busy = false;
};

static constexpr double kDepletionFraction = 1e-9;

// The local viewer consumes the same XML elements that NetAnim writes. A
// dedicated prefix keeps progress logs separate from trace data on stdout.
static void StreamNetanimElement(const char* xml)
{
    std::string line(xml);
    std::replace(line.begin(), line.end(), '\n', ' ');
    std::replace(line.begin(), line.end(), '\r', ' ');
    std::cout << "@NETANIM@" << line << std::endl;
}

static void NetanimEnergyTrace(AnimationInterface* animation,
                               uint32_t counter,
                               uint32_t node,
                               double oldValue,
                               double newValue)
{
    (void)oldValue;
    animation->UpdateNodeCounter(counter, node, std::max(0.0, newValue));
}

static void RecordNetanimCounters(AnimationInterface* animation,
                                  uint32_t txCounter,
                                  uint32_t rxCounter,
                                  uint32_t contestedCounter,
                                  uint32_t revokedCounter,
                                  uint32_t delayCounter,
                                  uint32_t tprCounter,
                                  uint32_t lambdaCounter,
                                  NodeContainer nodes,
                                  Ipv4InterfaceContainer addresses,
                                  double stop)
{
    Oracle& oracle = Oracle::Get();
    for (uint32_t i = 0; i < nodes.GetN(); ++i)
    {
        const uint32_t id = nodes.Get(i)->GetId();
        animation->UpdateNodeCounter(contestedCounter, id,
                                     oracle.HonestWitnesses(addresses.GetAddress(i), false));
        animation->UpdateNodeCounter(revokedCounter, id,
                                     oracle.HonestWitnesses(addresses.GetAddress(i), true));
    }
    animation->UpdateNodeCounter(txCounter, nodes.Get(0)->GetId(), oracle.AppTx());
    animation->UpdateNodeCounter(rxCounter, nodes.Get(0)->GetId(), oracle.AppRx());
    animation->UpdateNodeCounter(delayCounter, nodes.Get(0)->GetId(), oracle.MeanDelayMs());
    double tpr = 0.0, fpr = 0.0;
    oracle.DetectionRates(2, tpr, fpr, false);
    animation->UpdateNodeCounter(tprCounter, nodes.Get(0)->GetId(), tpr);
    animation->UpdateNodeCounter(lambdaCounter, nodes.Get(0)->GetId(),
                                 oracle.Agent() ? oracle.Agent()->Lambda() : 0.0);
    if (Simulator::Now().GetSeconds() + 0.5 <= stop)
        Simulator::Schedule(Seconds(0.5), &RecordNetanimCounters, animation,
                            txCounter, rxCounter, contestedCounter,
                            revokedCounter, delayCounter, tprCounter, lambdaCounter,
                            nodes, addresses, stop);
}

static void DepleteRadio(uint32_t node, Ptr<WifiPhy> phy)
{
    Oracle::Get().ReportNodeDeath(node, Simulator::Now());
    if (!phy->IsStateOff()) phy->SetOffMode();
}

static void EnergyTrace(uint32_t node, double initialEnergy, double oldValue, double newValue)
{
    (void)oldValue;
    // Time quantisation can leave a sub-nanojoule remainder at shutdown.
    if (newValue <= kDepletionFraction * initialEnergy)
        Oracle::Get().ReportNodeDeath(node, Simulator::Now());
}

static const char*
DropReasonName(uint32_t reason)
{
    switch (reason)
    {
    case Ipv4L3Protocol::DROP_TTL_EXPIRED:
        return "ip_drop_ttl_expired";
    case Ipv4L3Protocol::DROP_NO_ROUTE:
        return "ip_drop_no_route";
    case Ipv4L3Protocol::DROP_BAD_CHECKSUM:
        return "ip_drop_bad_checksum";
    case Ipv4L3Protocol::DROP_INTERFACE_DOWN:
        return "ip_drop_interface_down";
    case Ipv4L3Protocol::DROP_ROUTE_ERROR:
        return "ip_drop_route_error";
    case Ipv4L3Protocol::DROP_FRAGMENT_TIMEOUT:
        return "ip_drop_fragment_timeout";
    case Ipv4L3Protocol::DROP_DUPLICATE:
        return "ip_drop_duplicate";
    case 100:
        return "mac_tx_drop";
    default:
        return "ip_drop_other";
    }
}

/// Everything the scenario needs to build one network and run it once.
struct ScenarioConfig
{
    std::string protocol{"ar-eaurp"};
    std::string attack{"none"};
    double malicious{0.0};

    uint32_t nodes{100};
    double area{1000.0};
    double minSpeed{1.0};
    double maxSpeed{20.0};
    double pause{2.0};

    uint32_t flows{40};
    double rate{1.0}; //!< data packets per second per flow
    uint32_t minSize{512};
    uint32_t maxSize{1024};

    double duration{300.0};
    double warmup{30.0};
    double commission{240.0};
    double cooldown{10.0};
    bool useGan{true};
    bool useLstm{true};
    bool useCmdp{true};
    bool energyExcuse{true};
    bool ecc{true};
    double pdrFloor{0.90};
    double cmdpEpsStart{0.30};
    double cmdpEpsEnd{0.05};
    uint32_t ganEpochs{120};
    uint32_t lstmEpochs{30};

    double txPower{16.0206};   //!< 40 mW, the ns-3 default and a common card setting
    double sensitivity{-96.0}; //!< typical 2 Mbit/s DSSS receiver
    double pathLossExponent{3.0};
    double initialEnergy{350.0};

    bool harvest{true};
    double panelFraction{0.7};
    double dayLength{600.0};

    uint32_t seed{1};
    uint32_t run{1};

    bool flowMonitor{false};
    bool verbose{false};
    bool printNeighbours{false};
    std::string netanimPath;
    double netanimStart{0.0};
    double netanimStop{0.0}; //!< zero means through cooldown
    double netanimPoll{0.25};
    uint32_t netanimMaxPackets{100000};
    bool netanimStream{false};
    bool realtime{false};
};

/// Build, run and tear down one network. Returns the measurement summary.
static std::map<std::string, double>
RunOnce(const ScenarioConfig& cfg, bool commissioning, uint32_t runOffset)
{
    RngSeedManager::SetSeed(cfg.seed);
    RngSeedManager::SetRun(cfg.run + runOffset);

    const double duration = commissioning ? cfg.commission : cfg.duration;
    const double warmup = commissioning ? 10.0 : cfg.warmup;

    Oracle& oracle = Oracle::Get();
    oracle.Reset(cfg.nodes);
    oracle.SetPhase(commissioning ? PHASE_COMMISSIONING : PHASE_EVALUATION);
    oracle.SetMeasurementStart(Seconds(warmup));
    oracle.SetMeasurementEnd(Seconds(duration));

    NodeContainer nodes;
    nodes.Create(cfg.nodes);

    // ---------------------------------------------------------- mobility --
    MobilityHelper mobility;
    ObjectFactory position;
    position.SetTypeId("ns3::RandomRectanglePositionAllocator");
    std::ostringstream xBound;
    xBound << "ns3::UniformRandomVariable[Min=0.0|Max=" << cfg.area << "]";
    position.Set("X", StringValue(xBound.str()));
    position.Set("Y", StringValue(xBound.str()));
    Ptr<PositionAllocator> positionAlloc = position.Create()->GetObject<PositionAllocator>();

    std::ostringstream speedBound;
    speedBound << "ns3::UniformRandomVariable[Min=" << cfg.minSpeed << "|Max=" << cfg.maxSpeed
               << "]";
    std::ostringstream pauseBound;
    pauseBound << "ns3::UniformRandomVariable[Min=0.0|Max=" << cfg.pause << "]";

    mobility.SetMobilityModel("ns3::RandomWaypointMobilityModel",
                              "Speed",
                              StringValue(speedBound.str()),
                              "Pause",
                              StringValue(pauseBound.str()),
                              "PositionAllocator",
                              PointerValue(positionAlloc));
    positionAlloc->AssignStreams(200000);
    mobility.SetPositionAllocator(positionAlloc);
    mobility.Install(nodes);

    // -------------------------------------------------------------- radio --
    // 802.11b in ad-hoc mode at a fixed 2 Mbit/s DSSS rate: no rate adaptation
    // confound, and a data rate a multi-hop MANET can actually sustain.
    YansWifiChannelHelper channel;
    channel.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");
    channel.AddPropagationLoss("ns3::LogDistancePropagationLossModel",
                               "Exponent",
                               DoubleValue(cfg.pathLossExponent),
                               "ReferenceDistance",
                               DoubleValue(1.0),
                               "ReferenceLoss",
                               DoubleValue(40.05)); // free-space loss at 1 m, 2.4 GHz
    // Multipath fading, so a link is not a clean disc: this is what makes the
    // watchdog miss transmissions it should have heard, which is the noise the
    // trust machinery has to survive.
    channel.AddPropagationLoss("ns3::NakagamiPropagationLossModel",
                               "m0",
                               DoubleValue(3.0),
                               "m1",
                               DoubleValue(2.0),
                               "m2",
                               DoubleValue(1.5));

    YansWifiPhyHelper phy;
    Ptr<YansWifiChannel> wifiChannel = channel.Create();
    wifiChannel->AssignStreams(1100000);
    phy.SetChannel(wifiChannel);
    phy.Set("TxPowerStart", DoubleValue(cfg.txPower));
    phy.Set("TxPowerEnd", DoubleValue(cfg.txPower));
    phy.Set("RxSensitivity", DoubleValue(cfg.sensitivity));
    phy.Set("CcaEdThreshold", DoubleValue(cfg.sensitivity + 3.0));
    // Preamble detection, not raw sensitivity, is what actually bounds range in
    // ns-3, and its -82 dBm default is far more pessimistic than a real DSSS
    // receiver. With this aligned to the sensitivity figure, the measured
    // delivery-versus-distance curve (scratch/ar-eaurp-range.cc) stays above
    // 99% out to 125 m and degrades through ~175 m -- i.e. the ~150 m
    // communication range both source papers assume, earned from a real PHY.
    phy.SetPreambleDetectionModel("ns3::ThresholdPreambleDetectionModel",
                                  "MinimumRssi",
                                  DoubleValue(cfg.sensitivity + 2.0),
                                  "Threshold",
                                  DoubleValue(4.0));

    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211b);
    // Broadcasts must use the same rate as data. ns-3 defaults non-unicast
    // frames to the lowest basic rate, which here would send route requests at
    // 1 Mbit/s and data at 2 Mbit/s -- the request then travels reliably over
    // links the data cannot use, and route discovery happily builds paths whose
    // every hop fails at the MAC. Matching the rates is what makes a discovered
    // route mean "this link works".
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                 "DataMode",
                                 StringValue("DsssRate2Mbps"),
                                 "ControlMode",
                                 StringValue("DsssRate2Mbps"),
                                 "NonUnicastMode",
                                 StringValue("DsssRate2Mbps"));
    WifiMacHelper mac;
    mac.SetType("ns3::AdhocWifiMac");
    NetDeviceContainer devices = wifi.Install(phy, mac, nodes);
    wifi.AssignStreams(devices, 1000000);

    // ------------------------------------------------------------- stack --
    // ARP in a mobile network: ns-3's defaults keep a failed resolution dead
    // for 100 s, which in a network where neighbours come and go would silently
    // blackhole a perfectly good link long after it came back. These are the
    // usual MANET settings -- resolution is retried quickly and forgotten
    // quickly.
    Config::SetDefault("ns3::ArpCache::DeadTimeout", TimeValue(Seconds(2)));
    Config::SetDefault("ns3::ArpCache::WaitReplyTimeout", TimeValue(MilliSeconds(200)));
    Config::SetDefault("ns3::ArpCache::MaxRetries", UintegerValue(5));
    Config::SetDefault("ns3::ArpCache::AliveTimeout", TimeValue(Seconds(30)));

    InternetStackHelper internet;
    ArEaurpHelper arEaurp;
    AodvHelper aodv;

    if (cfg.protocol == "ns3-aodv")
    {
        internet.SetRoutingHelper(aodv);
    }
    else
    {
        arEaurp.Set("UseGan", BooleanValue(cfg.useGan));
        arEaurp.Set("UseLstm", BooleanValue(cfg.useLstm));
        arEaurp.Set("UseCmdp", BooleanValue(cfg.useCmdp));
        arEaurp.Set("EnergyExcuse", BooleanValue(cfg.energyExcuse));
        arEaurp.Set("LargePacketThreshold", UintegerValue(700 + 8 + (cfg.ecc ? 28 : 0)));
        if (cfg.protocol == "drl-paper")
        {
            arEaurp.Set("Variant", EnumValue(RoutingProtocol::VARIANT_DRL_PAPER));
        }
        else if (cfg.protocol == "drl-senior")
        {
            arEaurp.Set("Variant", EnumValue(RoutingProtocol::VARIANT_DRL_SENIOR));
        }
        else if (cfg.protocol == "aodv")
        {
            arEaurp.Set("Variant", EnumValue(RoutingProtocol::VARIANT_AODV));
        }
        else if (cfg.protocol == "eaurp")
        {
            arEaurp.Set("Variant", EnumValue(RoutingProtocol::VARIANT_EAURP));
        }
        else
        {
            arEaurp.Set("Variant", EnumValue(RoutingProtocol::VARIANT_AR_EAURP));
        }
        internet.SetRoutingHelper(arEaurp);
    }
    internet.Install(nodes);
    // ARP jitter also needs an explicit stream: multiple native scenarios now
    // share a process, whose automatically assigned stream counter advances.
    internet.AssignStreams(nodes, 1200000);

    Ipv4AddressHelper address;
    address.SetBase("10.1.0.0", "255.255.0.0");
    Ipv4InterfaceContainer interfaces = address.Assign(devices);

    // ------------------------------------------------------------ energy --
    BasicEnergySourceHelper energySourceHelper;
    energySourceHelper.Set("BasicEnergySourceInitialEnergyJ", DoubleValue(cfg.initialEnergy));
    energySourceHelper.Set("BasicEnergySupplyVoltageV", DoubleValue(3.0));
    energySourceHelper.Set("BasicEnergyLowBatteryThreshold", DoubleValue(kDepletionFraction));
    energy::EnergySourceContainer sources = energySourceHelper.Install(nodes);
    for (uint32_t i = 0; i < sources.GetN(); ++i)
        sources.Get(i)->TraceConnectWithoutContext("RemainingEnergy", MakeBoundCallback(&EnergyTrace, i, cfg.initialEnergy));

    // Current draws measured from a real 802.11 card, which is what ns-3 ships
    // as the default for this model.
    energy::DeviceEnergyModelContainer radioModels;
    for (uint32_t i = 0; i < devices.GetN(); ++i)
    {
        auto model = CreateObject<StableWifiRadioEnergyModel>();
        model->SetTxCurrentA(0.380);
        model->SetRxCurrentA(0.313);
        model->SetIdleCurrentA(0.273);
        model->SetCcaBusyCurrentA(0.273);
        model->SetSwitchingCurrentA(0.273);
        model->SetSleepCurrentA(0.033);
        auto wifiPhy = DynamicCast<WifiNetDevice>(devices.Get(i))->GetPhy();
        model->SetEnergyDepletionCallback(MakeBoundCallback(&DepleteRadio, i, wifiPhy));
        // Match the original simulator: first depletion is permanent node
        // failure. A reservoir can accumulate charge without restarting its PHY.
        sources.Get(i)->AppendDeviceEnergyModel(model);
        model->SetEnergySource(sources.Get(i));
        wifiPhy->SetWifiRadioEnergyModel(model);
        wifiPhy->RegisterListener(model->GetPhyListener());
        radioModels.Add(model);
    }

    if (cfg.harvest)
    {
        Ptr<UniformRandomVariable> panelRng = CreateObject<UniformRandomVariable>();
        panelRng->SetStream(500000);
        for (uint32_t i = 0; i < nodes.GetN(); ++i)
        {
            Ptr<SolarEnergyHarvester> harvester = CreateObject<SolarEnergyHarvester>();
            const bool hasPanel = panelRng->GetValue(0.0, 1.0) < cfg.panelFraction;
            harvester->SetAttribute("HasPanel", BooleanValue(hasPanel));
            harvester->SetAttribute("PeakPower",
                                    DoubleValue(panelRng->GetValue(0.9, 1.6)));
            harvester->SetAttribute("DayLength", TimeValue(Seconds(cfg.dayLength)));
            harvester->SetAttribute("PhaseOffset", DoubleValue(0.28));
            harvester->SetNode(nodes.Get(i));
            harvester->SetEnergySource(sources.Get(i));
            sources.Get(i)->ConnectEnergyHarvester(harvester);
            harvester->AssignStreams(400000 + i);

            Ptr<energy::EnergyHarvesterContainer> container =
                nodes.Get(i)->GetObject<energy::EnergyHarvesterContainer>();
            if (!container)
            {
                container = CreateObject<energy::EnergyHarvesterContainer>();
                nodes.Get(i)->AggregateObject(container);
            }
            container->Add(harvester);
        }
    }

    // ---------------------------------------------------------- adversary --
    // Placement is drawn before anything else touches this stream, so the same
    // nodes are hostile no matter which protocol is under test.
    Ptr<UniformRandomVariable> advRng = CreateObject<UniformRandomVariable>();
    advRng->SetStream(700000);

    std::set<uint32_t> hostile;
    uint32_t role = ROLE_HONEST;
    RoutingProtocol::Attack attackKind = RoutingProtocol::ATTACK_NONE;
    if (!commissioning && cfg.attack != "none" && cfg.malicious > 0.0)
    {
        if (cfg.attack == "blackhole")
        {
            attackKind = RoutingProtocol::ATTACK_BLACKHOLE;
            role = ROLE_BLACKHOLE;
        }
        else if (cfg.attack == "grayhole")
        {
            attackKind = RoutingProtocol::ATTACK_GRAYHOLE;
            role = ROLE_GRAYHOLE;
        }
        else if (cfg.attack == "trust_poisoning")
        {
            attackKind = RoutingProtocol::ATTACK_TRUST_POISONING;
            role = ROLE_GRAYHOLE | ROLE_SLANDERER;
        }
        const uint32_t count =
            std::min(cfg.nodes, (uint32_t)std::lround(cfg.malicious * cfg.nodes));
        while (hostile.size() < count)
        {
            hostile.insert(advRng->GetInteger(0, cfg.nodes - 1));
        }
    }

    for (uint32_t i = 0; i < nodes.GetN(); ++i)
    {
        const Ipv4Address addr = interfaces.GetAddress(i);
        const bool bad = hostile.count(i) > 0;
        oracle.Register(i, addr, bad ? role : (uint32_t)ROLE_HONEST);
        if (bad)
        {
            Ptr<Ipv4> ipv4 = nodes.Get(i)->GetObject<Ipv4>();
            Ptr<RoutingProtocol> rp = DynamicCast<RoutingProtocol>(ipv4->GetRoutingProtocol());
            if (rp)
            {
                rp->SetAttack(attackKind);
            }
        }
    }

    // ------------------------------------------------------------ traffic --
    Ptr<UniformRandomVariable> flowRng = CreateObject<UniformRandomVariable>();
    flowRng->SetStream(800000);
    Ptr<UniformRandomVariable> keyRng = CreateObject<UniformRandomVariable>();
    keyRng->SetStream(600000);

    ApplicationContainer apps;
    std::vector<uint32_t> sourceFlows(cfg.nodes, 0);
    std::vector<uint32_t> sinkFlows(cfg.nodes, 0);
    for (uint32_t f = 0; f < cfg.flows; ++f)
    {
        uint32_t src = flowRng->GetInteger(0, cfg.nodes - 1);
        uint32_t dst = flowRng->GetInteger(0, cfg.nodes - 1);
        while (dst == src)
        {
            dst = flowRng->GetInteger(0, cfg.nodes - 1);
        }
        ++sourceFlows[src];
        ++sinkFlows[dst];
        const uint16_t port = 9000 + f;

        ArTrafficHelper sink;
        sink.SetAttribute("Port", UintegerValue(port));
        ApplicationContainer receiverApps = sink.Install(nodes.Get(dst));
        apps.Add(receiverApps);

        ArTrafficHelper source;
        source.SetAttribute("Port", UintegerValue(port));
        source.SetAttribute("Remote", Ipv4AddressValue(interfaces.GetAddress(dst)));
        source.SetAttribute("Interval", TimeValue(Seconds(1.0 / cfg.rate)));
        source.SetAttribute("MinSize", UintegerValue(cfg.minSize));
        source.SetAttribute("MaxSize", UintegerValue(cfg.maxSize));
        source.SetAttribute("AckTimeout", TimeValue(Seconds(6.0)));
        ApplicationContainer senderApps = source.Install(nodes.Get(src));
        apps.Add(senderApps);
        if (cfg.ecc)
        {
            CryptoBox::Key a{}, b{};
            for (auto& byte : a) byte = keyRng->GetInteger(0, 255);
            for (auto& byte : b) byte = keyRng->GetInteger(0, 255);
            DynamicCast<ArTrafficApp>(senderApps.Get(0))->SetCipher(CryptoBox::Agree(a, CryptoBox::PublicKey(b)), 1);
            DynamicCast<ArTrafficApp>(receiverApps.Get(0))->SetCipher(CryptoBox::Agree(b, CryptoBox::PublicKey(a)), 2);
        }
    }
    ArTrafficHelper::AssignStreams(apps, 900000);
    apps.Start(Seconds(1.0));
    for (uint32_t i = 0; i < apps.GetN(); ++i)
    {
        auto app = DynamicCast<ArTrafficApp>(apps.Get(i));
        app->SetStopTime(Seconds(duration + cfg.cooldown));
        if (i % 2 == 1) Simulator::Schedule(Seconds(duration), &ArTrafficApp::StopSending, app);
    }

    // Fixed streams, so that two protocols see the same topology and traffic.
    arEaurp.AssignStreams(nodes, 100000);
    mobility.AssignStreams(nodes, 300000);
    if (cfg.protocol == "ns3-aodv") aodv.AssignStreams(nodes, 100000);

    g_ipDrops.clear();
    Config::ConnectWithoutContext("/NodeList/*/$ns3::Ipv4L3Protocol/Drop",
                                  MakeCallback(&Ipv4DropTrace));
    Config::ConnectWithoutContext("/NodeList/*/DeviceList/*/$ns3::WifiNetDevice/Mac/MacTxDrop",
                                  MakeCallback(&MacTxDropTrace));

    FlowMonitorHelper flowHelper;
    Ptr<FlowMonitor> monitor;
    if (cfg.flowMonitor && !commissioning)
    {
        monitor = flowHelper.InstallAll();
    }

    // The trace is attached only to evaluation. Commissioning is a separate
    // simulator run and must never be mixed into the visible attack scenario.
    std::unique_ptr<AnimationInterface> animation;
    std::vector<Callback<void, double, double>> netanimEnergyCallbacks;
    if (!commissioning && !cfg.netanimPath.empty())
    {
        animation = std::make_unique<AnimationInterface>(cfg.netanimPath);
        animation->SetMaxPktsPerTraceFile(cfg.netanimMaxPackets);
        if (cfg.netanimStream)
        {
            animation->SetAnimWriteCallback(&StreamNetanimElement);
            for (uint32_t i = 0; i < nodes.GetN(); ++i)
            {
                const Vector position = nodes.Get(i)->GetObject<MobilityModel>()->GetPosition();
                std::cout << "@NETANIM@<node id=\"" << nodes.Get(i)->GetId()
                          << "\" locX=\"" << position.x << "\" locY=\""
                          << position.y << "\"/>" << std::endl;
            }
        }
        animation->SetMobilityPollInterval(Seconds(cfg.netanimPoll));
        animation->SetStartTime(Seconds(cfg.netanimStart));
        animation->SetStopTime(Seconds(cfg.netanimStop > 0
                                            ? cfg.netanimStop
                                            : duration + cfg.cooldown));
        animation->EnablePacketMetadata(true);
        for (uint32_t i = 0; i < nodes.GetN(); ++i)
        {
            std::ostringstream description;
            description << "Node " << i << " | " << interfaces.GetAddress(i) << " | "
                        << (hostile.count(i) ? cfg.attack : "honest")
                        << " | source flows " << sourceFlows[i]
                        << " | sink flows " << sinkFlows[i]
                        << " | protocol " << cfg.protocol;
            animation->UpdateNodeDescription(nodes.Get(i), description.str());
            if (hostile.count(i))
                animation->UpdateNodeColor(nodes.Get(i), 239, 68, 68);
            else if (sourceFlows[i] && sinkFlows[i])
                animation->UpdateNodeColor(nodes.Get(i), 167, 139, 250);
            else if (sourceFlows[i])
                animation->UpdateNodeColor(nodes.Get(i), 56, 189, 248);
            else if (sinkFlows[i])
                animation->UpdateNodeColor(nodes.Get(i), 244, 114, 182);
            else
                animation->UpdateNodeColor(nodes.Get(i), 74, 222, 128);
        }
        const uint32_t batteryCounter = animation->AddNodeCounter(
            "BatteryJ", AnimationInterface::DOUBLE_COUNTER);
        for (uint32_t i = 0; i < sources.GetN(); ++i)
        {
            const uint32_t id = nodes.Get(i)->GetId();
            animation->UpdateNodeCounter(batteryCounter, id, cfg.initialEnergy);
            auto callback = MakeBoundCallback(&NetanimEnergyTrace,
                                              animation.get(), batteryCounter, id);
            sources.Get(i)->TraceConnectWithoutContext("RemainingEnergy", callback);
            netanimEnergyCallbacks.push_back(callback);
        }
        const uint32_t txCounter = animation->AddNodeCounter(
            "AppTx", AnimationInterface::DOUBLE_COUNTER);
        const uint32_t rxCounter = animation->AddNodeCounter(
            "AppRx", AnimationInterface::DOUBLE_COUNTER);
        const uint32_t contestedCounter = animation->AddNodeCounter(
            "ContestedWitnesses", AnimationInterface::DOUBLE_COUNTER);
        const uint32_t revokedCounter = animation->AddNodeCounter(
            "RevokedWitnesses", AnimationInterface::DOUBLE_COUNTER);
        const uint32_t delayCounter = animation->AddNodeCounter(
            "MeanAppDelayMs", AnimationInterface::DOUBLE_COUNTER);
        const uint32_t tprCounter = animation->AddNodeCounter(
            "DetectTPR", AnimationInterface::DOUBLE_COUNTER);
        const uint32_t lambdaCounter = animation->AddNodeCounter(
            "CmdpLambda", AnimationInterface::DOUBLE_COUNTER);
        Simulator::ScheduleNow(&RecordNetanimCounters, animation.get(),
                               txCounter, rxCounter, contestedCounter,
                               revokedCounter, delayCounter, tprCounter, lambdaCounter,
                               nodes, interfaces,
                               cfg.netanimStop > 0 ? cfg.netanimStop : duration + cfg.cooldown);
    }

    double energyAtEnd = 0.0;
    double harvestedAtEnd = 0.0;
    double radioCurrentAtEnd = 0.0;
    uint32_t radioOffAtEnd = 0;
    Simulator::Schedule(Seconds(duration), [&]() {
        for (uint32_t i = 0; i < sources.GetN(); ++i)
        {
            energyAtEnd += std::max(0.0, sources.Get(i)->GetRemainingEnergy());
            radioCurrentAtEnd += radioModels.Get(i)->GetCurrentA();
            if (DynamicCast<WifiNetDevice>(devices.Get(i))->GetPhy()->IsStateOff())
                ++radioOffAtEnd;
        }
        for (uint32_t i = 0; i < nodes.GetN(); ++i)
        {
            auto container = nodes.Get(i)->GetObject<energy::EnergyHarvesterContainer>();
            if (container && container->GetN())
            {
                auto solar = DynamicCast<SolarEnergyHarvester>(container->Get(0));
                if (solar) harvestedAtEnd += solar->GetTotalEnergyHarvestedJ();
            }
        }
    });
    Simulator::Stop(Seconds(duration + cfg.cooldown));
    Simulator::Run();

    std::map<std::string, double> summary = oracle.Summary();
    for (const auto& kv : g_ipDrops)
    {
        summary[DropReasonName(kv.first)] = (double)kv.second;
    }

    // Residual energy and connectivity, measured on the live network before it
    // is torn down.
    summary["residual_energy_j"] = energyAtEnd;
    summary["mean_residual_fraction"] = energyAtEnd / (cfg.initialEnergy * cfg.nodes);
    summary["harvested_j"] = harvestedAtEnd;
    summary["radio_current_a"] = radioCurrentAtEnd;
    summary["radio_off_nodes"] = radioOffAtEnd;
    summary["measurement_seconds"] = duration - warmup;
    summary["throughput_bps"] = summary["rx_bytes"] * 8.0 / (duration - warmup);
    summary["loss_packets"] = summary["app_tx"] - summary["app_rx"];
    summary["first_death_observed"] = summary["dead_nodes"] > 0.0 ? 1.0 : 0.0;
    summary["lifetime_horizon_s"] = duration;

    // Mean physical degree at the end of the run: the topology the protocol
    // actually had to work with, not the one the parameters imply.
    double degree = 0.0;
    for (uint32_t i = 0; i < nodes.GetN(); ++i)
    {
        Ptr<MobilityModel> a = nodes.Get(i)->GetObject<MobilityModel>();
        for (uint32_t j = 0; j < nodes.GetN(); ++j)
        {
            if (i == j)
            {
                continue;
            }
            Ptr<MobilityModel> b = nodes.Get(j)->GetObject<MobilityModel>();
            if (a->GetDistanceFrom(b) <= 150.0)
            {
                degree += 1.0;
            }
        }
    }
    summary["mean_degree_150m"] = degree / (double)cfg.nodes;

    {
        double known = 0.0;
        double usable = 0.0;
        double quality = 0.0;
        double unknownMac = 0.0;
        double noPending = 0.0;
        double digestMiss = 0.0;
        uint32_t counted = 0;
        double qUpdates = 0.0, qStates = 0.0;
        for (uint32_t i = 0; i < nodes.GetN(); ++i)
        {
            Ptr<Ipv4> ipv4 = nodes.Get(i)->GetObject<Ipv4>();
            Ptr<RoutingProtocol> rp = DynamicCast<RoutingProtocol>(ipv4->GetRoutingProtocol());
            if (!rp)
            {
                continue;
            }
            for (const auto& kv : rp->Neighbors().Table())
            {
                if (kv.second.expire > Simulator::Now())
                {
                    known += 1.0;
                }
            }
            unknownMac += rp->Neighbors().watchUnknownMac;
            noPending += rp->Neighbors().watchNoPending;
            digestMiss += rp->Neighbors().watchDigestMiss;
            usable += rp->UsableNeighbours();
            quality += rp->MeanLinkQuality();
            qUpdates += rp->QUpdates();
            qStates += rp->QStates();
            counted++;
        }
        summary["mean_known_neighbours"] = (counted > 0) ? known / counted : 0.0;
        summary["mean_usable_neighbours"] = (counted > 0) ? usable / counted : 0.0;
        summary["mean_link_quality"] = (counted > 0) ? quality / counted : 0.0;
        summary["watch_unknown_mac"] = unknownMac;
        summary["watch_no_pending"] = noPending;
        summary["watch_digest_miss"] = digestMiss;
        summary["q_updates"] = qUpdates;
        summary["q_states"] = qStates;
    }

    if (monitor)
    {
        monitor->CheckForLostPackets();
        Ptr<Ipv4FlowClassifier> classifier =
            DynamicCast<Ipv4FlowClassifier>(flowHelper.GetClassifier());
        uint64_t tx = 0;
        uint64_t rx = 0;
        for (const auto& kv : monitor->GetFlowStats())
        {
            Ipv4FlowClassifier::FiveTuple t = classifier->FindFlow(kv.first);
            if (t.destinationPort >= 9000 && t.destinationPort < 9000 + (uint16_t)cfg.flows)
            {
                tx += kv.second.txPackets;
                rx += kv.second.rxPackets;
            }
        }
        summary["flowmon_tx"] = (double)tx;
        summary["flowmon_rx"] = (double)rx;
    }

    for (uint32_t i = 0; i < netanimEnergyCallbacks.size(); ++i)
        sources.Get(i)->TraceDisconnectWithoutContext("RemainingEnergy",
                                                      netanimEnergyCallbacks[i]);
    animation.reset();
    Simulator::Destroy();
    return summary;
}

static bool SetString(std::string* target, const std::string& value)
{ *target = value; return true; }

int
ns3::arEaurp::RunScenarioCommand(int argc, char* argv[], Measurements* output)
{
    ScenarioConfig cfg;
    std::string csvPath;
    std::string jsonPath;
    std::string label;
    bool trainModels = true;

    CommandLine cmd(__FILE__);
    cmd.AddValue("protocol", "aodv | eaurp | drl-paper | drl-senior | ar-eaurp | ns3-aodv", MakeBoundCallback(&SetString, &cfg.protocol));
    cmd.AddValue("attack", "none | blackhole | grayhole | trust_poisoning", MakeBoundCallback(&SetString, &cfg.attack));
    cmd.AddValue("malicious", "fraction of nodes that are hostile", cfg.malicious);
    cmd.AddValue("nodes", "number of nodes", cfg.nodes);
    cmd.AddValue("area", "side of the square deployment area, metres", cfg.area);
    cmd.AddValue("minSpeed", "minimum node speed, m/s", cfg.minSpeed);
    cmd.AddValue("maxSpeed", "maximum node speed, m/s", cfg.maxSpeed);
    cmd.AddValue("pause", "maximum waypoint pause, s", cfg.pause);
    cmd.AddValue("flows", "number of CBR flows", cfg.flows);
    cmd.AddValue("rate", "data packets per second per flow", cfg.rate);
    cmd.AddValue("minSize", "smallest payload, bytes", cfg.minSize);
    cmd.AddValue("maxSize", "largest payload, bytes", cfg.maxSize);
    cmd.AddValue("time", "simulated seconds", cfg.duration);
    cmd.AddValue("warmup", "seconds excluded from the measurement", cfg.warmup);
    cmd.AddValue("cooldown", "seconds to drain in-flight traffic after sources stop", cfg.cooldown);
    cmd.AddValue("gan", "enable GAN detector", cfg.useGan);
    cmd.AddValue("lstm", "enable LSTM forecast", cfg.useLstm);
    cmd.AddValue("cmdp", "enable constrained route selection", cfg.useCmdp);
    cmd.AddValue("energyExcuse", "excuse low-energy relays in consensus", cfg.energyExcuse);
    cmd.AddValue("ecc", "protect application messages using X25519/AES-GCM", cfg.ecc);
    cmd.AddValue("pdrFloor", "CMDP delivery constraint", cfg.pdrFloor);
    cmd.AddValue("cmdpEpsStart", "CMDP epsilon at the start of evaluation", cfg.cmdpEpsStart);
    cmd.AddValue("cmdpEpsEnd", "minimum CMDP epsilon during evaluation", cfg.cmdpEpsEnd);
    cmd.AddValue("ganEpochs", "GAN training epochs", cfg.ganEpochs);
    cmd.AddValue("lstmEpochs", "LSTM training epochs", cfg.lstmEpochs);
    cmd.AddValue("json", "write one machine-readable result", MakeBoundCallback(&SetString, &jsonPath));
    cmd.AddValue("commission", "seconds of clean commissioning run", cfg.commission);
    cmd.AddValue("txPower", "transmit power, dBm", cfg.txPower);
    cmd.AddValue("sensitivity", "receiver sensitivity, dBm", cfg.sensitivity);
    cmd.AddValue("pathLoss", "log-distance path-loss exponent", cfg.pathLossExponent);
    cmd.AddValue("energy", "initial battery charge per node, J", cfg.initialEnergy);
    cmd.AddValue("harvest", "attach solar/kinetic harvesters", cfg.harvest);
    cmd.AddValue("panelFraction", "fraction of nodes with a panel", cfg.panelFraction);
    cmd.AddValue("dayLength", "length of one simulated day, s", cfg.dayLength);
    cmd.AddValue("seed", "RNG seed", cfg.seed);
    cmd.AddValue("run", "RNG run number", cfg.run);
    cmd.AddValue("flowMonitor", "also measure with FlowMonitor", cfg.flowMonitor);
    cmd.AddValue("netanim", "write evaluation NetAnim XML to this path", MakeBoundCallback(&SetString, &cfg.netanimPath));
    cmd.AddValue("netanimStart", "first simulated second in the NetAnim trace", cfg.netanimStart);
    cmd.AddValue("netanimStop", "last simulated second in the NetAnim trace (0 = end)", cfg.netanimStop);
    cmd.AddValue("netanimPoll", "node position sampling interval in seconds", cfg.netanimPoll);
    cmd.AddValue("netanimMaxPackets", "packets per NetAnim XML file before splitting", cfg.netanimMaxPackets);
    cmd.AddValue("netanimStream", "stream NetAnim XML elements to stdout for the local viewer", cfg.netanimStream);
    cmd.AddValue("realtime", "pace evaluation against wall time (best effort)", cfg.realtime);
    cmd.AddValue("verbose", "print per-run detail", cfg.verbose);
    cmd.AddValue("neighbours", "report the protocol's own neighbour counts",
                 cfg.printNeighbours);
    cmd.AddValue("train", "run the commissioning phase for AR-EAURP", trainModels);
    cmd.AddValue("csv", "append one result row to this file", MakeBoundCallback(&SetString, &csvPath));
    cmd.AddValue("label", "label written into the result row", MakeBoundCallback(&SetString, &label));
    cmd.Parse(argc, argv);

    const std::set<std::string> protocols{"aodv", "eaurp", "drl-paper", "drl-senior", "ar-eaurp", "ns3-aodv"};
    const std::set<std::string> attacks{"none", "blackhole", "grayhole", "trust_poisoning"};
    if (!protocols.count(cfg.protocol) || !attacks.count(cfg.attack) || cfg.nodes < 2 ||
        cfg.nodes > 1000 || cfg.flows == 0 || cfg.flows > 1000 ||
        !std::isfinite(cfg.malicious) || cfg.malicious < 0 || cfg.malicious > 1 ||
        !std::isfinite(cfg.area) || cfg.area <= 0 ||
        !std::isfinite(cfg.minSpeed) || !std::isfinite(cfg.maxSpeed) ||
        cfg.minSpeed <= 0 || cfg.maxSpeed < cfg.minSpeed ||
        !std::isfinite(cfg.pause) || cfg.pause < 0 ||
        !std::isfinite(cfg.rate) || cfg.rate <= 0 ||
        !std::isfinite(cfg.duration) || !std::isfinite(cfg.warmup) ||
        cfg.warmup < 1 || cfg.duration <= cfg.warmup ||
        !std::isfinite(cfg.cooldown) || cfg.cooldown < 6 ||
        cfg.minSize < 32 || cfg.maxSize < cfg.minSize || cfg.maxSize > 1400 ||
        !std::isfinite(cfg.initialEnergy) || cfg.initialEnergy <= 0 ||
        !std::isfinite(cfg.panelFraction) || cfg.panelFraction < 0 || cfg.panelFraction > 1 ||
        !std::isfinite(cfg.dayLength) || cfg.dayLength <= 0 ||
        !std::isfinite(cfg.pdrFloor) || cfg.pdrFloor < 0 || cfg.pdrFloor > 1 ||
        !std::isfinite(cfg.cmdpEpsStart) || cfg.cmdpEpsStart < 0 || cfg.cmdpEpsStart > 1 ||
        !std::isfinite(cfg.cmdpEpsEnd) || cfg.cmdpEpsEnd < 0 || cfg.cmdpEpsEnd > cfg.cmdpEpsStart ||
        !std::isfinite(cfg.commission) || cfg.commission <= 10 ||
        !std::isfinite(cfg.txPower) || !std::isfinite(cfg.sensitivity) ||
        !std::isfinite(cfg.pathLossExponent) || cfg.pathLossExponent <= 0 ||
        cfg.seed == 0 || cfg.run == 0 || cfg.ganEpochs == 0 || cfg.lstmEpochs == 0 ||
        !std::isfinite(cfg.netanimStart) || cfg.netanimStart < 0 ||
        !std::isfinite(cfg.netanimStop) || cfg.netanimStop < 0 ||
        (cfg.netanimStop > 0 && cfg.netanimStop <= cfg.netanimStart) ||
        !std::isfinite(cfg.netanimPoll) || cfg.netanimPoll <= 0 ||
        cfg.netanimMaxPackets == 0 ||
        (cfg.netanimStream && cfg.netanimPath.empty()) ||
        (cfg.attack == "none" && cfg.malicious > 0) ||
        (cfg.protocol == "ns3-aodv" && cfg.malicious > 0))
    {
        std::cerr << "Invalid scenario configuration. Use --PrintHelp for valid parameters." << std::endl;
        return 2;
    }
    const auto started = std::chrono::steady_clock::now();
    if (cfg.verbose)
    {
        LogComponentEnable("ArEaurpSim", LOG_LEVEL_INFO);
    }

    Oracle& oracle = Oracle::Get();
    std::map<std::string, double> modelStats{
        {"gan_trained", 0.0}, {"lstm_trained", 0.0}, {"gan_train_windows", 0.0},
        {"gan_threshold", 0.0}, {"lstm_mae_w", 0.0}, {"lstm_selected", 0.0}, {"lstm_train_sequences", 0.0}, {"lstm_validation_sequences", 0.0},
        {"lstm_persistence_mae_w", 0.0}, {"lstm_window_mean_mae_w", 0.0}};

    if (cfg.protocol == "ar-eaurp" && trainModels && (cfg.useGan || (cfg.useLstm && cfg.harvest)))
    {
        // Commissioning: a clean network, no adversary, nothing to detect yet.
        // The detector and the forecaster are trained here and then frozen, so
        // neither has seen the attack it is later scored on.
        oracle.CreateModels(cfg.seed * 7919 + 13);
        oracle.Agent()->SetConstraint(cfg.pdrFloor, 5.0, 0.05, 20.0);
        oracle.Agent()->SetExploration(cfg.cmdpEpsStart, cfg.cmdpEpsEnd, 800.0);
        std::cout << "[commissioning] clean run, " << cfg.commission << " s ..." << std::endl;
        RunOnce(cfg, true, 500);

        GanAnomalyDetector* detector = oracle.Detector();
        EnergyForecaster* forecaster = oracle.Forecaster();

        std::cout << "[commissioning] detector: " << detector->TrainingSamples()
                  << " clean behaviour windows" << std::endl;
        modelStats["gan_train_windows"] = detector->TrainingSamples();
        if (cfg.useGan && detector->Fit(cfg.ganEpochs, 16, 95.0))
        {
            std::cout << "[commissioning] detector trained, threshold "
                      << std::fixed << std::setprecision(4) << detector->Threshold()
                      << " (D loss " << detector->LastDiscriminatorLoss() << ", G loss "
                      << detector->LastGeneratorLoss() << ")" << std::endl;
            modelStats["gan_trained"] = 1.0;
            modelStats["gan_threshold"] = detector->Threshold();
            modelStats["gan_train_windows"] = (double)detector->TrainingSamples();
        }
        else
        {
            std::cout << "[commissioning] detector NOT trained (too little data)" << std::endl;
        }

        if (cfg.harvest && cfg.useLstm)
        {
            const double mae = forecaster->Fit(cfg.lstmEpochs, 5e-3);
            modelStats["lstm_trained"] = forecaster->IsTrained() ? 1.0 : 0.0;
            modelStats["lstm_selected"] = forecaster->UsesLstm() ? 1.0 : 0.0;
            modelStats["lstm_train_sequences"] = forecaster->TrainingSequences();
            modelStats["lstm_validation_sequences"] = forecaster->ValidationSequences();
            std::cout << "[commissioning] forecaster: " << forecaster->TrainingSequences()
                      << " sequences, MAE " << mae << " W vs persistence "
                      << forecaster->PersistenceMae() << " W, window mean "
                      << forecaster->SeasonalMae() << " W; selected "
                      << (forecaster->UsesLstm() ? "LSTM" : "persistence") << std::endl;
            modelStats["lstm_mae_w"] = mae;
            modelStats["lstm_persistence_mae_w"] = forecaster->PersistenceMae();
            modelStats["lstm_window_mean_mae_w"] = forecaster->SeasonalMae();
        }
    }
    else if (cfg.protocol == "ar-eaurp")
    {
        oracle.CreateModels(cfg.seed * 7919 + 13);
        oracle.Agent()->SetConstraint(cfg.pdrFloor, 5.0, 0.05, 20.0);
        oracle.Agent()->SetExploration(cfg.cmdpEpsStart, cfg.cmdpEpsEnd, 800.0);
    }

    std::cout << "[evaluation] " << cfg.protocol << " / " << cfg.attack << " @ "
              << (100.0 * cfg.malicious) << "% , " << cfg.nodes << " nodes, " << cfg.duration
              << " s" << std::endl;
    if (cfg.realtime)
        GlobalValue::Bind("SimulatorImplementationType",
                          StringValue("ns3::RealtimeSimulatorImpl"));
    std::map<std::string, double> result = RunOnce(cfg, false, 0);

    for (const auto& kv : modelStats)
    {
        result[kv.first] = kv.second;
    }
    for (const auto* key : {"cmdp_lambda", "cmdp_lambda_peak", "cmdp_violations", "cmdp_decisions", "cmdp_mean_reward"})
        result[key] = 0.0;
    for (uint32_t a = 0; a < ACTION_COUNT; ++a)
        result[std::string("cmdp_action_") + ActionName(a)] = 0.0;
    if (oracle.Agent() && cfg.useCmdp)
    {
        CmdpAgent* agent = oracle.Agent();
        result["cmdp_lambda"] = agent->Lambda();
        result["cmdp_lambda_peak"] = agent->LambdaPeak();
        result["cmdp_violations"] = (double)agent->Violations();
        result["cmdp_decisions"] = (double)agent->Decisions();
        result["cmdp_mean_reward"] = agent->MeanReward();
        for (uint32_t a = 0; a < ACTION_COUNT; ++a)
        {
            result[std::string("cmdp_action_") + ActionName(a)] = (double)agent->ActionCount(a);
        }
    }

    for (uint32_t reason = 0; reason <= 7; ++reason)
        if (std::string(DropReasonName(reason)) != "ip_drop_other") result.try_emplace(DropReasonName(reason), 0.0);
    result.try_emplace("mac_tx_drop", 0.0);
    result.try_emplace("ip_drop_other", 0.0);
    result["wall_clock_seconds"] = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    result["cfg_warmup"] = cfg.warmup;
    result["cfg_cooldown"] = cfg.cooldown;
    result["cfg_gan"] = cfg.useGan;
    result["cfg_lstm"] = cfg.useLstm;
    result["cfg_cmdp"] = cfg.useCmdp;
    result["cfg_energy_excuse"] = cfg.energyExcuse;
    result["cfg_ecc"] = cfg.ecc;
    result["cfg_pdr_floor"] = cfg.pdrFloor;
    result["cfg_nodes"] = cfg.nodes;
    result["cfg_area"] = cfg.area;
    result["cfg_malicious"] = cfg.malicious;
    result["cfg_max_speed"] = cfg.maxSpeed;
    result["cfg_flows"] = cfg.flows;
    result["cfg_rate"] = cfg.rate;
    result["cfg_duration"] = cfg.duration;
    result["cfg_commission"] = cfg.commission;
    result["cfg_gan_epochs"] = cfg.ganEpochs;
    result["cfg_lstm_epochs"] = cfg.lstmEpochs;
    result["cfg_train"] = trainModels ? 1.0 : 0.0;
    result["cfg_realtime"] = cfg.realtime ? 1.0 : 0.0;
    result["cfg_energy_j"] = cfg.initialEnergy;
    result["cfg_harvest"] = cfg.harvest ? 1.0 : 0.0;
    result["cfg_run"] = cfg.run;
    result["cfg_seed"] = cfg.seed;

    std::cout << "---------------------------------------------------------------" << std::endl;
    std::cout << std::fixed << std::setprecision(4);
    for (const auto& kv : result)
    {
        std::cout << "  " << std::left << std::setw(30) << kv.first << " " << kv.second
                  << std::endl;
    }
    std::cout << "---------------------------------------------------------------" << std::endl;

    auto quote = [](const std::string& value) {
        std::string escaped = "\"";
        for (char c : value) { if (c == '"') escaped += '"'; escaped += c; }
        return escaped + "\"";
    };
    if (!jsonPath.empty())
    {
        std::ofstream out(jsonPath);
        if (!out) { std::cerr << "Cannot write JSON: " << jsonPath << std::endl; return 3; }
        out << std::setprecision(17) << "{\n  \"engine\": \"ns-3\",\n  \"ns3_version\": \"3.45\",\n";
        out << "  \"protocol\": \"" << cfg.protocol << "\",\n  \"attack\": \"" << cfg.attack << "\"";
        for (const auto& kv : result) out << ",\n  \"" << kv.first << "\": " << kv.second;
        out << "\n}\n";
        if (!out) return 3;
    }
    if (!csvPath.empty())
    {
        std::ostringstream header;
        header << "label,protocol,attack";
        for (const auto& kv : result) header << "," << kv.first;
        std::ifstream existing(csvPath);
        std::string oldHeader;
        const bool exists = bool(std::getline(existing, oldHeader));
        if (exists && oldHeader != header.str())
        { std::cerr << "CSV schema differs; use a new file." << std::endl; return 3; }
        std::ofstream out(csvPath, std::ios::app);
        if (!out) { std::cerr << "Cannot write CSV: " << csvPath << std::endl; return 3; }
        if (!exists) out << header.str() << "\n";
        out << quote(label) << "," << cfg.protocol << "," << cfg.attack << std::setprecision(17);
        for (const auto& kv : result) out << "," << kv.second;
        out << "\n";
        if (!out) return 3;
    }
    if (output) *output = result;
    oracle.ClearModels();
    return 0;
}
