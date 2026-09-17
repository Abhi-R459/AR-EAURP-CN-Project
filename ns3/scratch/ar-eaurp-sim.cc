/*
 * AR-EAURP evaluation scenario.
 *
 * A mobile ad-hoc network of real ns-3 nodes: 802.11g radios on a Yans channel
 * with log-distance path loss and Nakagami fading, random-waypoint mobility at
 * walking-to-vehicle speeds, a real IPv4 stack, UDP flows of realistic packet
 * sizes, a battery per node with the measured current draw of an 802.11 card,
 * and -- for the harvesting experiments -- a photovoltaic panel with a diurnal
 * cycle and persistent cloud cover.
 *
 * Everything the protocol knows, it learns from packets that were actually
 * transmitted. The only global object is the measurement registry, which the
 * protocol never reads.
 *
 * Usage:
 *   ./ns3 run "ar-eaurp-sim --protocol=ar-eaurp --attack=grayhole --malicious=0.3"
 */

#include "ns3/applications-module.h"
#include "ns3/ar-eaurp-helper.h"
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
#include "ns3/solar-energy-harvester.h"
#include "ns3/wifi-module.h"
#include "ns3/wifi-radio-energy-model-helper.h"

#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
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
    g_ipDrops[(uint32_t)reason]++;
}

static void
MacTxDropTrace(Ptr<const Packet> packet)
{
    (void)packet;
    g_ipDrops[100]++;
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
    double commission{120.0};

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
    mobility.SetPositionAllocator(positionAlloc);
    mobility.Install(nodes);

    // -------------------------------------------------------------- radio --
    // 802.11g in ad-hoc mode at a fixed 6 Mbit/s OFDM rate: no rate adaptation
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
    phy.SetChannel(channel.Create());
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
        if (cfg.protocol == "aodv")
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

    Ipv4AddressHelper address;
    address.SetBase("10.1.0.0", "255.255.0.0");
    Ipv4InterfaceContainer interfaces = address.Assign(devices);

    // ------------------------------------------------------------ energy --
    BasicEnergySourceHelper energySourceHelper;
    energySourceHelper.Set("BasicEnergySourceInitialEnergyJ", DoubleValue(cfg.initialEnergy));
    energySourceHelper.Set("BasicEnergySupplyVoltageV", DoubleValue(3.0));
    energy::EnergySourceContainer sources = energySourceHelper.Install(nodes);

    // Current draws measured from a real 802.11 card, which is what ns-3 ships
    // as the default for this model.
    WifiRadioEnergyModelHelper radioEnergy;
    radioEnergy.Set("TxCurrentA", DoubleValue(0.380));
    radioEnergy.Set("RxCurrentA", DoubleValue(0.313));
    radioEnergy.Set("IdleCurrentA", DoubleValue(0.273));
    radioEnergy.Set("CcaBusyCurrentA", DoubleValue(0.273));
    radioEnergy.Set("SwitchingCurrentA", DoubleValue(0.273));
    radioEnergy.Set("SleepCurrentA", DoubleValue(0.033));
    energy::DeviceEnergyModelContainer deviceModels =
        radioEnergy.Install(devices, sources);

    if (cfg.harvest)
    {
        Ptr<UniformRandomVariable> panelRng = CreateObject<UniformRandomVariable>();
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
            harvester->AssignStreams(4000 + i);

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
    advRng->SetStream(9000);

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
            std::min(cfg.nodes - 2, (uint32_t)std::lround(cfg.malicious * cfg.nodes));
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
    flowRng->SetStream(9100);

    ApplicationContainer apps;
    for (uint32_t f = 0; f < cfg.flows; ++f)
    {
        uint32_t src = flowRng->GetInteger(0, cfg.nodes - 1);
        uint32_t dst = flowRng->GetInteger(0, cfg.nodes - 1);
        while (dst == src)
        {
            dst = flowRng->GetInteger(0, cfg.nodes - 1);
        }
        const uint16_t port = 9000 + f;

        ArTrafficHelper sink;
        sink.SetAttribute("Port", UintegerValue(port));
        apps.Add(sink.Install(nodes.Get(dst)));

        ArTrafficHelper source;
        source.SetAttribute("Port", UintegerValue(port));
        source.SetAttribute("Remote", Ipv4AddressValue(interfaces.GetAddress(dst)));
        source.SetAttribute("Interval", TimeValue(Seconds(1.0 / cfg.rate)));
        source.SetAttribute("MinSize", UintegerValue(cfg.minSize));
        source.SetAttribute("MaxSize", UintegerValue(cfg.maxSize));
        source.SetAttribute("AckTimeout", TimeValue(Seconds(6.0)));
        apps.Add(source.Install(nodes.Get(src)));
    }
    ArTrafficHelper::AssignStreams(apps, 9200);
    apps.Start(Seconds(1.0));
    apps.Stop(Seconds(duration - 1.0));

    // Fixed streams, so that two protocols see the same topology and traffic.
    arEaurp.AssignStreams(nodes, 100);
    mobility.AssignStreams(nodes, 2000);

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

    Simulator::Stop(Seconds(duration));
    Simulator::Run();

    std::map<std::string, double> summary = oracle.Summary();
    for (const auto& kv : g_ipDrops)
    {
        summary[DropReasonName(kv.first)] = (double)kv.second;
    }

    // Residual energy and connectivity, measured on the live network before it
    // is torn down.
    double energyLeft = 0.0;
    double harvested = 0.0;
    for (uint32_t i = 0; i < sources.GetN(); ++i)
    {
        energyLeft += sources.Get(i)->GetRemainingEnergy();
    }
    for (uint32_t i = 0; i < nodes.GetN(); ++i)
    {
        Ptr<energy::EnergyHarvesterContainer> container =
            nodes.Get(i)->GetObject<energy::EnergyHarvesterContainer>();
        if (container && container->GetN() > 0)
        {
            Ptr<SolarEnergyHarvester> solar =
                DynamicCast<SolarEnergyHarvester>(container->Get(0));
            if (solar)
            {
                harvested += solar->GetTotalEnergyHarvestedJ();
            }
        }
    }
    summary["residual_energy_j"] = energyLeft;
    summary["mean_residual_fraction"] = energyLeft / (cfg.initialEnergy * cfg.nodes);
    summary["harvested_j"] = harvested;

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
            counted++;
        }
        summary["mean_known_neighbours"] = (counted > 0) ? known / counted : 0.0;
        summary["mean_usable_neighbours"] = (counted > 0) ? usable / counted : 0.0;
        summary["mean_link_quality"] = (counted > 0) ? quality / counted : 0.0;
        summary["watch_unknown_mac"] = unknownMac;
        summary["watch_no_pending"] = noPending;
        summary["watch_digest_miss"] = digestMiss;
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

    Simulator::Destroy();
    return summary;
}

int
main(int argc, char* argv[])
{
    ScenarioConfig cfg;
    std::string csvPath;
    std::string label;
    bool trainModels = true;

    CommandLine cmd(__FILE__);
    cmd.AddValue("protocol", "aodv | eaurp | ar-eaurp | ns3-aodv", cfg.protocol);
    cmd.AddValue("attack", "none | blackhole | grayhole | trust_poisoning", cfg.attack);
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
    cmd.AddValue("verbose", "print per-run detail", cfg.verbose);
    cmd.AddValue("neighbours", "report the protocol's own neighbour counts",
                 cfg.printNeighbours);
    cmd.AddValue("train", "run the commissioning phase for AR-EAURP", trainModels);
    cmd.AddValue("csv", "append one result row to this file", csvPath);
    cmd.AddValue("label", "label written into the result row", label);
    cmd.Parse(argc, argv);

    if (cfg.verbose)
    {
        LogComponentEnable("ArEaurpSim", LOG_LEVEL_INFO);
    }

    Oracle& oracle = Oracle::Get();
    std::map<std::string, double> modelStats;

    if (cfg.protocol == "ar-eaurp" && trainModels)
    {
        // Commissioning: a clean network, no adversary, nothing to detect yet.
        // The detector and the forecaster are trained here and then frozen, so
        // neither has seen the attack it is later scored on.
        oracle.CreateModels(cfg.seed * 7919 + 13);
        std::cout << "[commissioning] clean run, " << cfg.commission << " s ..." << std::endl;
        RunOnce(cfg, true, 500);

        GanAnomalyDetector* detector = oracle.Detector();
        EnergyForecaster* forecaster = oracle.Forecaster();

        std::cout << "[commissioning] detector: " << detector->TrainingSamples()
                  << " clean behaviour windows" << std::endl;
        if (detector->Fit(120, 16, 95.0))
        {
            std::cout << "[commissioning] detector trained, threshold "
                      << std::fixed << std::setprecision(4) << detector->Threshold()
                      << " (D loss " << detector->LastDiscriminatorLoss() << ", G loss "
                      << detector->LastGeneratorLoss() << ")" << std::endl;
            modelStats["gan_threshold"] = detector->Threshold();
            modelStats["gan_train_windows"] = (double)detector->TrainingSamples();
        }
        else
        {
            std::cout << "[commissioning] detector NOT trained (too little data)" << std::endl;
        }

        if (cfg.harvest)
        {
            const double mae = forecaster->Fit(30, 5e-3);
            std::cout << "[commissioning] forecaster: " << forecaster->TrainingSequences()
                      << " sequences, MAE " << mae << " W vs persistence "
                      << forecaster->PersistenceMae() << " W, window mean "
                      << forecaster->SeasonalMae() << " W" << std::endl;
            modelStats["lstm_mae_w"] = mae;
            modelStats["lstm_persistence_mae_w"] = forecaster->PersistenceMae();
            modelStats["lstm_window_mean_mae_w"] = forecaster->SeasonalMae();
        }
    }
    else if (cfg.protocol == "ar-eaurp")
    {
        oracle.CreateModels(cfg.seed * 7919 + 13);
    }

    std::cout << "[evaluation] " << cfg.protocol << " / " << cfg.attack << " @ "
              << (100.0 * cfg.malicious) << "% , " << cfg.nodes << " nodes, " << cfg.duration
              << " s" << std::endl;
    std::map<std::string, double> result = RunOnce(cfg, false, 0);

    for (const auto& kv : modelStats)
    {
        result[kv.first] = kv.second;
    }
    if (oracle.Agent())
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

    result["cfg_nodes"] = cfg.nodes;
    result["cfg_malicious"] = cfg.malicious;
    result["cfg_max_speed"] = cfg.maxSpeed;
    result["cfg_flows"] = cfg.flows;
    result["cfg_rate"] = cfg.rate;
    result["cfg_duration"] = cfg.duration;
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

    if (!csvPath.empty())
    {
        const bool exists = std::ifstream(csvPath).good();
        std::ofstream out(csvPath, std::ios::app);
        if (!exists)
        {
            out << "label,protocol,attack";
            for (const auto& kv : result)
            {
                out << "," << kv.first;
            }
            out << "\n";
        }
        out << label << "," << cfg.protocol << "," << cfg.attack;
        for (const auto& kv : result)
        {
            out << "," << kv.second;
        }
        out << "\n";
    }

    oracle.ClearModels();
    return 0;
}
