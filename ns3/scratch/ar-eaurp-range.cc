/*
 * Radio calibration.
 *
 * Both source papers assume a 150 m communication range but neither specifies a
 * PHY, so "150 m" has to be earned from a real radio rather than asserted. This
 * program puts two nodes at a fixed distance, floods 1024-byte frames between
 * them over the same channel model the scenario uses, and reports the fraction
 * that arrive. Running it over a sweep of distances gives the real
 * delivery-versus-distance curve, and the scenario's transmit power and
 * path-loss exponent are chosen so that the curve crosses ~90% delivery at
 * roughly 150 m.
 */

#include "ns3/core-module.h"
#include "ns3/applications-module.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/wifi-module.h"

#include <iomanip>
#include <iostream>

using namespace ns3;

static uint32_t g_received = 0;

static void
RxCallback(Ptr<const Packet> p, const Address& from)
{
    (void)p;
    (void)from;
    g_received++;
}

static double
Measure(double distance,
        double txPower,
        double exponent,
        const std::string& standard,
        const std::string& mode,
        double sensitivity,
        uint32_t packets,
        bool fading)
{
    g_received = 0;
    RngSeedManager::SetSeed(12345);
    RngSeedManager::SetRun(7);

    NodeContainer nodes;
    nodes.Create(2);

    MobilityHelper mobility;
    Ptr<ListPositionAllocator> alloc = CreateObject<ListPositionAllocator>();
    alloc->Add(Vector(0.0, 0.0, 1.5));
    alloc->Add(Vector(distance, 0.0, 1.5));
    mobility.SetPositionAllocator(alloc);
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(nodes);

    YansWifiChannelHelper channel;
    channel.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");
    channel.AddPropagationLoss("ns3::LogDistancePropagationLossModel",
                               "Exponent",
                               DoubleValue(exponent),
                               "ReferenceDistance",
                               DoubleValue(1.0),
                               "ReferenceLoss",
                               DoubleValue(40.05));
    if (fading)
    {
        channel.AddPropagationLoss("ns3::NakagamiPropagationLossModel",
                                   "m0",
                                   DoubleValue(3.0),
                                   "m1",
                                   DoubleValue(2.0),
                                   "m2",
                                   DoubleValue(1.5));
    }

    YansWifiPhyHelper phy;
    phy.SetChannel(channel.Create());
    phy.Set("TxPowerStart", DoubleValue(txPower));
    phy.Set("TxPowerEnd", DoubleValue(txPower));
    phy.Set("RxSensitivity", DoubleValue(sensitivity));
    phy.Set("CcaEdThreshold", DoubleValue(sensitivity + 3.0));
    // The binding constraint on range is preamble detection, not raw
    // sensitivity: ns-3 defaults to a -82 dBm floor, which is far more
    // conservative than a real DSSS receiver. Aligning it with the sensitivity
    // figure is what makes the modelled range match the datasheet range.
    phy.SetPreambleDetectionModel("ns3::ThresholdPreambleDetectionModel",
                                  "MinimumRssi",
                                  DoubleValue(sensitivity + 2.0),
                                  "Threshold",
                                  DoubleValue(4.0));

    WifiHelper wifi;
    wifi.SetStandard(standard == "80211b" ? WIFI_STANDARD_80211b : WIFI_STANDARD_80211g);
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                 "DataMode",
                                 StringValue(mode),
                                 "ControlMode",
                                 StringValue(mode));
    WifiMacHelper mac;
    mac.SetType("ns3::AdhocWifiMac");
    NetDeviceContainer devices = wifi.Install(phy, mac, nodes);

    InternetStackHelper internet;
    internet.Install(nodes);
    Ipv4AddressHelper address;
    address.SetBase("10.9.0.0", "255.255.255.0");
    Ipv4InterfaceContainer interfaces = address.Assign(devices);

    PacketSinkHelper sink("ns3::UdpSocketFactory",
                          InetSocketAddress(Ipv4Address::GetAny(), 8000));
    ApplicationContainer sinkApp = sink.Install(nodes.Get(1));
    sinkApp.Get(0)->TraceConnectWithoutContext("Rx", MakeCallback(&RxCallback));
    sinkApp.Start(Seconds(0.0));

    OnOffHelper source("ns3::UdpSocketFactory",
                       InetSocketAddress(interfaces.GetAddress(1), 8000));
    source.SetAttribute("OnTime", StringValue("ns3::ConstantRandomVariable[Constant=1]"));
    source.SetAttribute("OffTime", StringValue("ns3::ConstantRandomVariable[Constant=0]"));
    source.SetAttribute("PacketSize", UintegerValue(1024));
    source.SetAttribute("DataRate", StringValue("100kb/s"));
    ApplicationContainer sourceApp = source.Install(nodes.Get(0));
    sourceApp.Start(Seconds(1.0));
    sourceApp.Stop(Seconds(1.0 + packets * 1024.0 * 8.0 / 100000.0));

    Simulator::Stop(Seconds(3.0 + packets * 1024.0 * 8.0 / 100000.0));
    Simulator::Run();
    Simulator::Destroy();

    return (double)g_received / (double)packets;
}

int
main(int argc, char* argv[])
{
    double txPower = 16.0206;
    double exponent = 3.0;
    double sensitivity = -96.0;
    std::string standard = "80211b";
    std::string mode = "DsssRate2Mbps";
    uint32_t packets = 200;
    bool fading = true;
    double maxDistance = 400.0;
    double step = 25.0;

    CommandLine cmd(__FILE__);
    cmd.AddValue("txPower", "transmit power, dBm", txPower);
    cmd.AddValue("pathLoss", "log-distance exponent", exponent);
    cmd.AddValue("sensitivity", "receiver sensitivity, dBm", sensitivity);
    cmd.AddValue("standard", "80211b | 80211g", standard);
    cmd.AddValue("mode", "wifi data mode", mode);
    cmd.AddValue("packets", "packets per distance", packets);
    cmd.AddValue("fading", "include Nakagami multipath fading", fading);
    cmd.AddValue("maxDistance", "largest distance to test, m", maxDistance);
    cmd.AddValue("step", "distance step, m", step);
    cmd.Parse(argc, argv);

    std::cout << "standard=" << standard << " mode=" << mode << " tx=" << txPower
              << " dBm n=" << exponent << " sens=" << sensitivity << " dBm" << std::endl;
    std::cout << " distance_m  delivery" << std::endl;
    for (double d = step; d <= maxDistance + 1e-9; d += step)
    {
        const double pdr =
            Measure(d, txPower, exponent, standard, mode, sensitivity, packets, fading);
        std::cout << std::setw(10) << d << "  " << std::fixed << std::setprecision(3) << pdr
                  << std::endl;
    }
    return 0;
}
