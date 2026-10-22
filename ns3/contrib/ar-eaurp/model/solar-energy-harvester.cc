#include "solar-energy-harvester.h"

#include "ns3/double.h"
#include "ns3/boolean.h"
#include "ns3/energy-source.h"
#include "ns3/log.h"
#include "ns3/mobility-model.h"
#include "ns3/node.h"
#include "ns3/simulator.h"
#include "ns3/trace-source-accessor.h"

#include <cmath>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("SolarEnergyHarvester");
NS_OBJECT_ENSURE_REGISTERED(SolarEnergyHarvester);

TypeId
SolarEnergyHarvester::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::SolarEnergyHarvester")
            .SetParent<energy::EnergyHarvester>()
            .SetGroupName("Energy")
            .AddConstructor<SolarEnergyHarvester>()
            .AddAttribute("PeriodicHarvestedPowerUpdateInterval",
                          "Time between two consecutive harvested power updates.",
                          TimeValue(Seconds(1.0)),
                          MakeTimeAccessor(&SolarEnergyHarvester::SetHarvestedPowerUpdateInterval,
                                           &SolarEnergyHarvester::GetHarvestedPowerUpdateInterval),
                          MakeTimeChecker())
            .AddAttribute("HasPanel",
                          "Whether this node carries a photovoltaic panel at all.",
                          BooleanValue(true),
                          MakeBooleanAccessor(&SolarEnergyHarvester::m_hasPanel),
                          MakeBooleanChecker())
            .AddAttribute("PeakPower",
                          "Panel output in full, unoccluded sun (W).",
                          DoubleValue(1.2),
                          MakeDoubleAccessor(&SolarEnergyHarvester::m_peakPower),
                          MakeDoubleChecker<double>())
            .AddAttribute("DayLength",
                          "Length of one simulated diurnal cycle.",
                          TimeValue(Seconds(600.0)),
                          MakeTimeAccessor(&SolarEnergyHarvester::m_dayLength),
                          MakeTimeChecker())
            .AddAttribute("PhaseOffset",
                          "Where in the day the simulation starts, in [0, 1).",
                          DoubleValue(0.3),
                          MakeDoubleAccessor(&SolarEnergyHarvester::m_phaseOffset),
                          MakeDoubleChecker<double>())
            .AddAttribute("CloudRho",
                          "AR(1) persistence of the cloud-occlusion process.",
                          DoubleValue(0.92),
                          MakeDoubleAccessor(&SolarEnergyHarvester::m_cloudRho),
                          MakeDoubleChecker<double>())
            .AddAttribute("CloudSigma",
                          "Innovation standard deviation of the cloud process.",
                          DoubleValue(0.12),
                          MakeDoubleAccessor(&SolarEnergyHarvester::m_cloudSigma),
                          MakeDoubleChecker<double>())
            .AddAttribute("KineticGain",
                          "Power recovered per unit of node speed (W per m/s).",
                          DoubleValue(0.004),
                          MakeDoubleAccessor(&SolarEnergyHarvester::m_kineticGain),
                          MakeDoubleChecker<double>())
            .AddTraceSource("HarvestedPower",
                            "Harvested power, in watts.",
                            MakeTraceSourceAccessor(&SolarEnergyHarvester::m_harvestedPower),
                            "ns3::TracedValueCallback::Double");
    return tid;
}

SolarEnergyHarvester::SolarEnergyHarvester()
    : m_harvestedPowerUpdateInterval(Seconds(1.0)),
      m_lastHarvestingUpdateTime(Seconds(0.0)),
      m_harvestedPower(0.0),
      m_totalEnergyHarvestedJ(0.0),
      m_hasPanel(true),
      m_peakPower(1.2),
      m_dayLength(Seconds(600.0)),
      m_phaseOffset(0.3),
      m_cloudRho(0.92),
      m_cloudSigma(0.12),
      m_cloudState(0.0),
      m_kineticGain(0.004)
{
    m_noise = CreateObject<NormalRandomVariable>();
    m_noise->SetAttribute("Mean", DoubleValue(0.0));
    m_noise->SetAttribute("Variance", DoubleValue(1.0));
}

SolarEnergyHarvester::~SolarEnergyHarvester()
{
}

void
SolarEnergyHarvester::SetHarvestedPowerUpdateInterval(Time interval)
{
    m_harvestedPowerUpdateInterval = interval;
}

Time
SolarEnergyHarvester::GetHarvestedPowerUpdateInterval() const
{
    return m_harvestedPowerUpdateInterval;
}

double
SolarEnergyHarvester::DayPhase() const
{
    const double day = m_dayLength.GetSeconds();
    if (day <= 0.0)
    {
        return 0.0;
    }
    double phase = m_phaseOffset + Simulator::Now().GetSeconds() / day;
    phase -= std::floor(phase);
    return phase;
}

int64_t
SolarEnergyHarvester::AssignStreams(int64_t stream)
{
    m_noise->SetStream(stream);
    return 1;
}

void
SolarEnergyHarvester::CalculateHarvestedPower()
{
    double power = 0.0;

    if (m_hasPanel)
    {
        const double phase = DayPhase();
        double irradiance = 0.0;
        // Daylight occupies the middle half of the cycle; a half sine over it
        // gives the usual dawn-noon-dusk shape.
        if (phase > 0.25 && phase < 0.75)
        {
            irradiance = std::sin(M_PI * (phase - 0.25) / 0.5);
        }

        // Persistent cloud cover: an AR(1) process, clipped to a multiplicative
        // occlusion factor in [0.05, 1].
        m_cloudState = m_cloudRho * m_cloudState + m_cloudSigma * m_noise->GetValue();
        const double occlusion = std::min(1.0, std::max(0.05, 1.0 - std::max(0.0, m_cloudState)));

        power += m_peakPower * irradiance * occlusion;
    }

    // Kinetic recovery from motion -- small, but available at night.
    Ptr<Node> node = GetNode();
    if (node)
    {
        Ptr<MobilityModel> mobility = node->GetObject<MobilityModel>();
        if (mobility)
        {
            const Vector v = mobility->GetVelocity();
            const double speed = std::sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
            power += m_kineticGain * speed;
        }
    }

    m_harvestedPower = power;
}

void
SolarEnergyHarvester::UpdateHarvestedPower()
{
    if (Simulator::IsFinished())
    {
        return;
    }
    const Time duration = Simulator::Now() - m_lastHarvestingUpdateTime;
    m_energyHarvestingUpdateEvent.Cancel();

    CalculateHarvestedPower();
    m_totalEnergyHarvestedJ += duration.GetSeconds() * m_harvestedPower;

    Ptr<energy::EnergySource> source = GetEnergySource();
    if (source)
    {
        source->UpdateEnergySource();
    }
    m_lastHarvestingUpdateTime = Simulator::Now();

    m_energyHarvestingUpdateEvent = Simulator::Schedule(m_harvestedPowerUpdateInterval,
                                                        &SolarEnergyHarvester::UpdateHarvestedPower,
                                                        this);
}

double
SolarEnergyHarvester::DoGetPower() const
{
    return m_harvestedPower;
}

void
SolarEnergyHarvester::DoInitialize()
{
    m_lastHarvestingUpdateTime = Simulator::Now();
    UpdateHarvestedPower();
}

void
SolarEnergyHarvester::DoDispose()
{
    m_energyHarvestingUpdateEvent.Cancel();
    Object::DoDispose();
}

} // namespace ns3
