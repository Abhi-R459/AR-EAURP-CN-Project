/*
 * A small, self-contained neural-network toolkit: dense layers with Adam, an
 * MLP, and an LSTM cell trained by backpropagation through time.
 *
 * Everything AR-EAURP learns -- the GAN that scores behaviour, the LSTM that
 * forecasts harvested energy, and the DQN that picks a routing strategy --
 * runs inside the ns-3 process on these primitives. Nothing is imported from a
 * Python run, so what the simulation reports is what the protocol could
 * actually compute on the node.
 *
 * Implementation notes: weights are double precision, gradients accumulate
 * across a mini-batch and are averaged by Step(), and every module takes an
 * explicit seed so a run is reproducible.
 */

#ifndef AR_EAURP_NNET_H
#define AR_EAURP_NNET_H

#include <cstdint>
#include <random>
#include <vector>

namespace ns3
{
namespace arEaurp
{

using Vec = std::vector<double>;

/// Non-linearities available to a dense layer.
enum class Activation
{
    NONE,
    RELU,
    LEAKY_RELU,
    TANH,
    SIGMOID,
};

/**
 * \brief Fully connected layer y = act(W x + b), trained with Adam.
 */
class Dense
{
  public:
    Dense(uint32_t inDim, uint32_t outDim, Activation act, std::mt19937& rng);

    /// Forward pass; caches the input and pre-activation for Backward().
    const Vec& Forward(const Vec& x);

    /**
     * \brief Backward pass.
     * \param gradOut dL/dy for this layer's output
     * \param gradIn  filled with dL/dx (may be empty for the first layer)
     */
    void Backward(const Vec& gradOut, Vec& gradIn);

    void ZeroGrad();
    void Step(double lr, uint32_t batch);

    uint32_t InDim() const
    {
        return m_in;
    }

    uint32_t OutDim() const
    {
        return m_out;
    }

    const Vec& Weights() const
    {
        return m_w;
    }

    void CopyFrom(const Dense& other);

    /// Exponential moving average towards another layer (soft target update).
    void Polyak(const Dense& other, double tau);

  private:
    uint32_t m_in;
    uint32_t m_out;
    Activation m_act;

    Vec m_w;  //!< row-major, m_out x m_in
    Vec m_b;
    Vec m_gw;
    Vec m_gb;

    // Adam moments.
    Vec m_mw;
    Vec m_vw;
    Vec m_mb;
    Vec m_vb;
    uint64_t m_t;

    Vec m_x;   //!< cached input
    Vec m_z;   //!< cached pre-activation
    Vec m_y;   //!< cached output
};

/**
 * \brief A stack of dense layers.
 */
class Mlp
{
  public:
    Mlp() = default;

    void Add(uint32_t inDim, uint32_t outDim, Activation act, std::mt19937& rng);

    const Vec& Forward(const Vec& x);
    void Backward(const Vec& gradOut);
    void ZeroGrad();
    void Step(double lr, uint32_t batch);

    void CopyFrom(const Mlp& other);
    void Polyak(const Mlp& other, double tau);

    /// dL/dx of the first layer, valid after Backward(). The GAN's generator
    /// step needs exactly this: the gradient the discriminator passes back to
    /// the sample it was shown.
    const Vec& InputGradient() const
    {
        return m_gradIn;
    }

    size_t Layers() const
    {
        return m_layers.size();
    }

  private:
    std::vector<Dense> m_layers;
    Vec m_gradIn;
};

/**
 * \brief One LSTM layer plus a linear head, trained by BPTT.
 *
 * Used to forecast a node's harvested power a horizon ahead from the recent
 * harvest history, which is what lets AR-EAURP route through a relay that is
 * low now but is about to recharge.
 */
class LstmRegressor
{
  public:
    LstmRegressor(uint32_t inputDim, uint32_t hidden, uint32_t outputDim, uint32_t seed);

    /// Forward over a whole sequence; returns the prediction at the last step.
    Vec Forward(const std::vector<Vec>& sequence);

    /// One training step on a single sequence with a squared-error target.
    double TrainStep(const std::vector<Vec>& sequence, const Vec& target, double lr);

    uint32_t InputDim() const
    {
        return m_in;
    }

    uint32_t Hidden() const
    {
        return m_hidden;
    }

  private:
    void Reset(size_t steps);

    uint32_t m_in;
    uint32_t m_hidden;
    uint32_t m_out;

    // Gate weights, stacked as [input, forget, cell, output].
    Vec m_wx; //!< 4H x I
    Vec m_wh; //!< 4H x H
    Vec m_bh; //!< 4H
    Vec m_wy; //!< O x H
    Vec m_by; //!< O

    Vec m_gwx;
    Vec m_gwh;
    Vec m_gbh;
    Vec m_gwy;
    Vec m_gby;

    Vec m_mwx, m_vwx, m_mwh, m_vwh, m_mbh, m_vbh, m_mwy, m_vwy, m_mby, m_vby;
    uint64_t m_t;

    // Per-timestep caches for BPTT.
    std::vector<Vec> m_xs;
    std::vector<Vec> m_is;
    std::vector<Vec> m_fs;
    std::vector<Vec> m_gs;
    std::vector<Vec> m_os;
    std::vector<Vec> m_cs;
    std::vector<Vec> m_hs;
};

double Sigmoid(double x);

} // namespace arEaurp
} // namespace ns3

#endif /* AR_EAURP_NNET_H */
