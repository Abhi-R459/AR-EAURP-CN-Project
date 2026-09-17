/*
 * LSTM energy-harvest forecaster -- AR-EAURP step 3.
 *
 * Each node samples the power its harvester is delivering. From the last
 * kInputLen samples (plus the phase of the day, which a node knows from its
 * own clock) the model predicts the mean power it will harvest over the next
 * horizon. Routing then uses "energy I have now, blended with energy I am
 * about to get" instead of residual charge alone, so a relay that is low but
 * is about to come back into the sun is not written off.
 *
 * One model is trained during the commissioning run on traces from the whole
 * fleet and then frozen and provisioned to every node -- which is how such a
 * model would actually be deployed, and means per-node cost at run time is one
 * forward pass, not training.
 *
 * HONEST BASELINES. Fit() also measures a persistence forecast (next = last)
 * and a seasonal-naive forecast (next = what was seen one day ago) on the same
 * held-out split, because an LSTM that cannot beat "tomorrow looks like today"
 * has not earned its place in the protocol.
 */

#ifndef AR_EAURP_FORECASTER_H
#define AR_EAURP_FORECASTER_H

#include "ar-eaurp-nnet.h"

#include <cstdint>
#include <deque>
#include <vector>

namespace ns3
{
namespace arEaurp
{

class EnergyForecaster
{
  public:
    EnergyForecaster(uint32_t inputLen, uint32_t horizon, uint32_t hidden, uint32_t seed);

    /// Record one harvested-power sample for one node during commissioning.
    void AddSample(uint32_t nodeId, double watts, double dayPhase);

    /// Train on the collected traces. Returns the held-out MAE of the LSTM.
    double Fit(uint32_t epochs, double lr);

    /**
     * \brief Mean power expected over the next horizon, in watts.
     * \param recent  the node's last samples, oldest first
     * \param phase   current phase of the simulated day in [0, 1)
     */
    double Predict(const std::deque<std::pair<double, double>>& recent) const;

    bool IsTrained() const
    {
        return m_trained;
    }

    uint32_t InputLen() const
    {
        return m_inputLen;
    }

    uint32_t Horizon() const
    {
        return m_horizon;
    }

    double LstmMae() const
    {
        return m_lstmMae;
    }

    double PersistenceMae() const
    {
        return m_persistenceMae;
    }

    double SeasonalMae() const
    {
        return m_seasonalMae;
    }

    double Scale() const
    {
        return m_scale;
    }

    size_t TrainingSequences() const
    {
        return m_sequences.size();
    }

  private:
    struct Sample
    {
        double watts;
        double phase;
    };

    uint32_t m_inputLen;
    uint32_t m_horizon;
    uint32_t m_hidden;

    mutable LstmRegressor m_lstm;
    std::vector<std::vector<Sample>> m_traces; //!< one per node
    std::vector<std::pair<std::vector<Vec>, double>> m_sequences;

    double m_scale;          //!< normalisation constant (max observed watts)
    double m_lstmMae;
    double m_persistenceMae;
    double m_seasonalMae;
    bool m_trained;
    uint32_t m_seed;
};

} // namespace arEaurp
} // namespace ns3

#endif /* AR_EAURP_FORECASTER_H */
