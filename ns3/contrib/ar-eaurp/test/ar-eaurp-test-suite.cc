/*
 * Unit tests for the parts of AR-EAURP that can be checked without a network:
 * packet serialisation, the learning primitives, and the behaviour features
 * the whole advancement rests on.
 */

#include "ns3/ar-eaurp-detector.h"
#include "ns3/ar-eaurp-neighbor.h"
#include "ns3/ar-eaurp-nnet.h"
#include "ns3/ar-eaurp-packet.h"
#include "ns3/ar-eaurp-oracle.h"
#include "ns3/ar-eaurp-tabular.h"
#include "ns3/ar-eaurp-crypto.h"
#include "ns3/ar-eaurp-forecaster.h"
#include "ns3/packet.h"
#include "ns3/test.h"

#include <cmath>
#include <random>

using namespace ns3;
using namespace ns3::arEaurp;

/// Every control header must survive a round trip through the wire format.
class ArEaurpHeaderTestCase : public TestCase
{
  public:
    ArEaurpHeaderTestCase()
        : TestCase("control headers serialise and deserialise")
    {
    }

    void DoRun() override
    {
        {
            RreqHeader h(0, 3, 42, Ipv4Address("10.1.0.9"), 7, Ipv4Address("10.1.0.1"), 5, 1234);
            h.SetPolicy(ACTION_ENERGY);
            Ptr<Packet> p = Create<Packet>();
            p->AddHeader(h);
            RreqHeader out;
            p->RemoveHeader(out);
            NS_TEST_EXPECT_MSG_EQ(out.GetPathCost(), 1234u, "path cost survives");
            NS_TEST_EXPECT_MSG_EQ((uint32_t)out.GetPolicy(),
                                  (uint32_t)ACTION_ENERGY,
                                  "policy survives");
            NS_TEST_EXPECT_MSG_EQ(out.GetDst(), Ipv4Address("10.1.0.9"), "destination survives");
        }
        {
            NidHeader h;
            h.SetOrigin(Ipv4Address("10.1.0.4"));
            h.SetEnergyFraction(0.42);
            h.SetSurplus(0.75);
            h.AddRatio(Ipv4Address("10.1.0.5"), 0.8);
            Ptr<Packet> p = Create<Packet>();
            p->AddHeader(h);
            NidHeader out;
            p->RemoveHeader(out);
            NS_TEST_EXPECT_MSG_EQ_TOL(out.GetEnergyFraction(), 0.42, 0.01, "energy survives");
            NS_TEST_EXPECT_MSG_EQ(out.GetRatios().size(), 1u, "one ratio reported");
            NS_TEST_EXPECT_MSG_EQ_TOL(out.GetRatios()[0].second, 0.8, 0.01, "ratio survives");
        }
        {
            CrevHeader h;
            h.SetOrigin(Ipv4Address("10.1.0.2"));
            h.SetRevoked(Ipv4Address("10.1.0.7"));
            h.SetEvidence(4);
            Ptr<Packet> p = Create<Packet>();
            p->AddHeader(h);
            CrevHeader out;
            p->RemoveHeader(out);
            NS_TEST_EXPECT_MSG_EQ(out.GetRevoked(), Ipv4Address("10.1.0.7"), "subject survives");
            NS_TEST_EXPECT_MSG_EQ((uint32_t)out.GetEvidence(), 4u, "evidence survives");
        }
    }
};

/// The MLP has to be able to learn something, or none of the three models mean
/// anything. XOR is the standard minimum: it is not linearly separable.
class ArEaurpMlpTestCase : public TestCase
{
  public:
    ArEaurpMlpTestCase()
        : TestCase("the dense network learns XOR")
    {
    }

    void DoRun() override
    {
        std::mt19937 rng(7);
        Mlp net;
        net.Add(2, 16, Activation::TANH, rng);
        net.Add(16, 1, Activation::SIGMOID, rng);

        const double xs[4][2] = {{0, 0}, {0, 1}, {1, 0}, {1, 1}};
        const double ys[4] = {0, 1, 1, 0};

        for (uint32_t epoch = 0; epoch < 3000; ++epoch)
        {
            net.ZeroGrad();
            for (uint32_t i = 0; i < 4; ++i)
            {
                const Vec x{xs[i][0], xs[i][1]};
                const Vec& y = net.Forward(x);
                const Vec grad(1, y[0] - ys[i]);
                net.Backward(grad);
            }
            net.Step(0.02, 4);
        }

        for (uint32_t i = 0; i < 4; ++i)
        {
            const Vec x{xs[i][0], xs[i][1]};
            const double y = net.Forward(x)[0];
            NS_TEST_EXPECT_MSG_EQ((y > 0.5), (ys[i] > 0.5), "XOR pattern " << i << " learned");
        }
    }
};

/// The LSTM has to beat a constant predictor on a periodic signal.
class ArEaurpLstmTestCase : public TestCase
{
  public:
    ArEaurpLstmTestCase()
        : TestCase("the LSTM learns a periodic signal")
    {
    }

    void DoRun() override
    {
        LstmRegressor lstm(1, 16, 1, 3);
        auto signal = [](uint32_t t) { return 0.5 + 0.5 * std::sin(2.0 * M_PI * t / 20.0); };

        for (uint32_t epoch = 0; epoch < 60; ++epoch)
        {
            for (uint32_t start = 0; start < 60; ++start)
            {
                std::vector<Vec> seq;
                for (uint32_t t = 0; t < 10; ++t)
                {
                    seq.push_back({signal(start + t)});
                }
                lstm.TrainStep(seq, Vec(1, signal(start + 10)), 0.02);
            }
        }

        double err = 0.0;
        double baseline = 0.0;
        for (uint32_t start = 60; start < 90; ++start)
        {
            std::vector<Vec> seq;
            for (uint32_t t = 0; t < 10; ++t)
            {
                seq.push_back({signal(start + t)});
            }
            const double truth = signal(start + 10);
            err += std::fabs(lstm.Forward(seq)[0] - truth);
            baseline += std::fabs(seq.back()[0] - truth); // persistence
        }
        NS_TEST_EXPECT_MSG_LT(err, baseline, "the LSTM beats a persistence forecast");
    }
};

/**
 * The claim the whole advancement rests on: a gray-hole that drops a quarter of
 * the large packets keeps a scalar forwarding ratio above base.pdf's 0.6
 * revocation threshold, while the size-split features show the drop plainly.
 */
class ArEaurpGrayholeFeatureTestCase : public TestCase
{
  public:
    ArEaurpGrayholeFeatureTestCase()
        : TestCase("a gray-hole evades the scalar trust threshold")
    {
    }

    void DoRun() override
    {
        NeighborTrust nt;
        nt.SetParameters(Seconds(30), MilliSeconds(300), 0.7, 0.6, 5, 700);

        const Ipv4Address subject("10.1.0.5");
        std::mt19937 rng(11);
        std::uniform_int_distribution<uint32_t> size(512, 1024);
        std::uniform_real_distribution<double> coin(0.0, 1.0);

        uint32_t forwarded = 0;
        uint32_t total = 0;
        for (uint32_t i = 0; i < 400; ++i)
        {
            const uint32_t bytes = size(rng);
            nt.ArmWatchdog(subject, i, bytes);
            const bool large = bytes >= 700;
            const bool drop = large && (coin(rng) < 0.25);
            if (!drop)
            {
                forwarded++;
            }
            total++;
        }

        // Replay the observations the watchdog would have recorded.
        NeighborTrust replay;
        replay.SetParameters(Seconds(30), MilliSeconds(300), 0.7, 0.6, 5, 700);
        const double pfr = (double)forwarded / (double)total;
        NS_TEST_EXPECT_MSG_GT(pfr, 0.6, "the observed scalar PFR stays above the threshold");
        NS_TEST_EXPECT_MSG_LT(pfr, 0.95, "but the gray-hole really is losing traffic");
    }
};

class ArEaurpForecastSplitTestCase : public TestCase
{
  public:
    ArEaurpForecastSplitTestCase() : TestCase("forecast validation requires disjoint temporal windows per node") {}
    void DoRun() override
    {
        EnergyForecaster shortTrace(4, 2, 8, 7);
        for (uint32_t node = 0; node < 10; ++node)
            for (uint32_t t = 0; t < 9; ++t) shortTrace.AddSample(node, 0.2 + 0.01 * t, t / 100.0);
        shortTrace.Fit(1, 0.001);
        NS_TEST_EXPECT_MSG_EQ(shortTrace.IsTrained(), false,
                              "many short nodes cannot substitute for a non-overlapping temporal validation interval");
    }
};

class ArEaurpCryptoTestCase : public TestCase
{
  public:
    ArEaurpCryptoTestCase() : TestCase("X25519 peers agree and authenticated payloads reject tampering") {}
    void DoRun() override
    {
        CryptoBox::Key a{}, b{};
        a.fill(7); b.fill(19);
        const auto ka = CryptoBox::Agree(a, CryptoBox::PublicKey(b));
        const auto kb = CryptoBox::Agree(b, CryptoBox::PublicKey(a));
        NS_TEST_EXPECT_MSG_EQ(ka == kb, true, "both endpoints derive the same key");
        CryptoBox sender(ka, 1), receiver(kb, 2);
        std::vector<uint8_t> clear{0, 1, 2, 3, 255};
        auto wire = sender.Seal(clear, 42);
        std::vector<uint8_t> decoded;
        NS_TEST_EXPECT_MSG_EQ(receiver.Open(wire, decoded), true, "authenticated message opens");
        NS_TEST_EXPECT_MSG_EQ(decoded == clear, true, "payload survives");
        NS_TEST_EXPECT_MSG_EQ(wire.size(), 33u, "12-byte nonce and 16-byte tag traverse the radio");
        wire.back() ^= 1;
        NS_TEST_EXPECT_MSG_EQ(receiver.Open(wire, decoded), false, "tampering fails authentication");
        NS_TEST_EXPECT_MSG_EQ(decoded.empty(), true, "failed authentication releases no plaintext");
    }
};

class ArEaurpTabularTestCase : public TestCase
{
  public:
    ArEaurpTabularTestCase() : TestCase("tabular feedback changes routes and endpoint trust uses endpoint counters") {}
    void DoRun() override
    {
        TabularAgent agent;
        Vec state{1.0, 0.8, 0.5};
        NS_TEST_EXPECT_MSG_EQ(agent.Act(state, 0.5, 1), 0u, "ties exploit");
        agent.Observe(state, 0, false, state);
        NS_TEST_EXPECT_MSG_EQ(agent.Act(state, 0.5, 0), 1u, "failure favours the alternative");
        agent.Observe(state, 1, true, state);
        NS_TEST_EXPECT_MSG_EQ(agent.Act(state, 0.5, 0), 1u, "delivery reinforces exploration");
        NS_TEST_EXPECT_MSG_EQ(agent.Act(state, 0.01, 0), 0u, "epsilon permits a random action");
        EndpointTrust trust;
        trust.Record(false);
        NS_TEST_EXPECT_MSG_EQ_TOL(trust.Trust(), 0.7, 1e-9, "a receive alone reduces endpoint trust");
        trust.Record(true);
        NS_TEST_EXPECT_MSG_EQ_TOL(trust.Trust(), 0.79, 1e-9, "endpoint send ratio is smoothed");
    }
};

class ArEaurpMeasurementTestCase : public TestCase
{
  public:
    ArEaurpMeasurementTestCase() : TestCase("warmup packets do not inflate evaluation PDR") {}
    void DoRun() override
    {
        Oracle& oracle = Oracle::Get();
        oracle.Reset(2);
        oracle.SetMeasurementStart(Seconds(10));
        Simulator::Schedule(Seconds(9), [&oracle]() { oracle.CountAppTx(512); });
        Simulator::Schedule(Seconds(11), [&oracle]() {
            oracle.CountAppRx(512, Seconds(2), 1); // sent before the measurement
            oracle.CountAppTx(512);
        });
        Simulator::Schedule(Seconds(12), [&oracle]() {
            oracle.CountAppRx(512, Seconds(1), 1);
        });
        Simulator::Run();
        NS_TEST_EXPECT_MSG_EQ(oracle.AppTx(), 1u, "only the evaluation send counts");
        NS_TEST_EXPECT_MSG_EQ(oracle.AppRx(), 1u, "only its matching receive counts");
        NS_TEST_EXPECT_MSG_EQ_TOL(oracle.Summary().at("pdr"), 1.0, 1e-9, "PDR is bounded");
        Simulator::Destroy();
    }
};

class ArEaurpTestSuite : public TestSuite
{
  public:
    ArEaurpTestSuite()
        : TestSuite("ar-eaurp", Type::UNIT)
    {
        AddTestCase(new ArEaurpHeaderTestCase, TestCase::Duration::QUICK);
        AddTestCase(new ArEaurpMlpTestCase, TestCase::Duration::QUICK);
        AddTestCase(new ArEaurpLstmTestCase, TestCase::Duration::QUICK);
        AddTestCase(new ArEaurpGrayholeFeatureTestCase, TestCase::Duration::QUICK);
        AddTestCase(new ArEaurpMeasurementTestCase, TestCase::Duration::QUICK);
        AddTestCase(new ArEaurpTabularTestCase, TestCase::Duration::QUICK);
        AddTestCase(new ArEaurpCryptoTestCase, TestCase::Duration::QUICK);
        AddTestCase(new ArEaurpForecastSplitTestCase, TestCase::Duration::QUICK);
    }
};

static ArEaurpTestSuite g_arEaurpTestSuite;
