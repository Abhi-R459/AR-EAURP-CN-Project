/*
 * GAN-based behaviour anomaly detector -- AR-EAURP step 2.
 *
 * A generator learns to imitate the behaviour features of a healthy network
 * while a discriminator learns to tell real observations from imitations. What
 * is kept afterwards is the discriminator: it has learned the shape of normal
 * relaying behaviour, so a node whose behaviour falls outside that shape scores
 * low and is marked *contested*.
 *
 * TRAIN / TEST SEPARATION. The detector is trained during a commissioning run
 * with no adversary present and is then frozen. It never sees an attack before
 * it is asked to score one, so the detection numbers are not the result of
 * having been tuned on the attack being measured.
 *
 * WHY A GAN RATHER THAN A THRESHOLD. A scalar packet forwarding ratio is one
 * number and a threshold on it is trivially evaded by dropping just less than
 * the threshold. The discriminator sees eight correlated features at once,
 * including the split between large and small packet drops, so "forwards
 * everything small, loses a quarter of everything large" is off-manifold even
 * though every individual feature looks defensible.
 */

#ifndef AR_EAURP_DETECTOR_H
#define AR_EAURP_DETECTOR_H

#include "ar-eaurp-nnet.h"

#include <cstdint>
#include <random>
#include <vector>

namespace ns3
{
namespace arEaurp
{

class GanAnomalyDetector
{
  public:
    GanAnomalyDetector(uint32_t featureDim, uint32_t latentDim, uint32_t hidden, uint32_t seed);

    /// Add one clean-phase observation to the training set.
    void AddTrainingSample(const std::vector<double>& features);

    size_t TrainingSamples() const
    {
        return m_train.size();
    }

    /**
     * \brief Adversarial training, then threshold calibration.
     * \param epochs      passes over the collected clean windows
     * \param batch       mini-batch size
     * \param percentile  score quantile of the clean data used as the threshold
     * \return true when there was enough data to train
     */
    bool Fit(uint32_t epochs, uint32_t batch, double percentile);

    /// Anomaly score in [0, 1]; higher means less like healthy behaviour.
    double Score(const std::vector<double>& features) const;

    bool Flag(const std::vector<double>& features) const
    {
        return Score(features) > m_threshold;
    }

    double Threshold() const
    {
        return m_threshold;
    }

    bool IsTrained() const
    {
        return m_trained;
    }

    double LastDiscriminatorLoss() const
    {
        return m_dLoss;
    }

    double LastGeneratorLoss() const
    {
        return m_gLoss;
    }

  private:
    void Standardise(const std::vector<double>& in, Vec& out) const;

    uint32_t m_featureDim;
    uint32_t m_latentDim;
    uint32_t m_hidden;

    mutable Mlp m_discriminator;
    Mlp m_generator;
    std::mt19937 m_rng;

    std::vector<std::vector<double>> m_train;
    Vec m_mean;
    Vec m_scale;

    double m_threshold;
    bool m_trained;
    double m_dLoss;
    double m_gLoss;
};

} // namespace arEaurp
} // namespace ns3

#endif /* AR_EAURP_DETECTOR_H */
