/*
 * Solar + kinetic energy harvester.
 *
 * Power delivered at time t:
 *
 *   P(t) = panel * Ppeak * irradiance(phase) * cloud(t) + kineticGain * speed(t)
 *
 * irradiance is a half-sine over the daylight half of the simulated day, cloud
 * is an AR(1) occlusion process (persistent, as real cloud cover is, rather
 * than white noise, which would average out and be invisible to a forecaster),
 * and the kinetic term is the small amount a moving node recovers from motion.
 *
 * Only a fraction of the nodes carry a panel, so the network is heterogeneous:
 * some relays recharge and some do not, which is the situation the forecaster
 * exists to exploit.
 *
 * TIME COMPRESSION. DayLength is a simulation parameter, not 24 hours: the
 * diurnal cycle is compressed so that a few minutes of simulated time spans a
 * meaningful part of a day. The shape of the cycle, the persistence of the
 * cloud process and the power levels are unchanged; only the clock is scaled.
 */

#ifndef SOLAR_ENERGY_HARVESTER_H
#define SOLAR_ENERGY_HARVESTER_H

#include "ns3/energy-harvester.h"
#include "ns3/event-id.h"
#include "ns3/nstime.h"
#include "ns3/random-variable-stream.h"
#include "ns3/traced-value.h"

namespace ns3
{

class SolarEnergyHarvester : public energy::EnergyHarvester
{
  public:
    static TypeId GetTypeId();
    SolarEnergyHarvester();
    ~SolarEnergyHarvester() override;

    void SetHarvestedPowerUpdateInterval(Time interval);
    Time GetHarvestedPowerUpdateInterval() const;

    double GetTotalEnergyHarvestedJ() const
    {
        return m_totalEnergyHarvestedJ;
    }

    /// Phase of the simulated day in [0, 1).
    double DayPhase() const;

    /// Power the harvester is delivering right now, in watts.
    double CurrentPower() const
    {
        return m_harvestedPower;
    }

    int64_t AssignStreams(int64_t stream);

  private:
    void UpdateHarvestedPower();
    void CalculateHarvestedPower();
    double DoGetPower() const override;
    void DoInitialize() override;
    void DoDispose() override;

    Time m_harvestedPowerUpdateInterval;
    Time m_lastHarvestingUpdateTime;
    EventId m_energyHarvestingUpdateEvent;

    TracedValue<double> m_harvestedPower;
    double m_totalEnergyHarvestedJ;

    bool m_hasPanel;
    double m_peakPower;
    Time m_dayLength;
    double m_phaseOffset;
    double m_cloudRho;
    double m_cloudSigma;
    double m_cloudState;
    double m_kineticGain;

    Ptr<NormalRandomVariable> m_noise;
};

} // namespace ns3

#endif /* SOLAR_ENERGY_HARVESTER_H */
