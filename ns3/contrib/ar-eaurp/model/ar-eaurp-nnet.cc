#include "ar-eaurp-nnet.h"

#include <algorithm>
#include <cmath>

namespace ns3
{
namespace arEaurp
{

namespace
{
constexpr double kBeta1 = 0.9;
constexpr double kBeta2 = 0.999;
constexpr double kEps = 1e-8;
constexpr double kGradClip = 5.0;

double
Apply(Activation a, double z)
{
    switch (a)
    {
    case Activation::RELU:
        return z > 0.0 ? z : 0.0;
    case Activation::LEAKY_RELU:
        return z > 0.0 ? z : 0.01 * z;
    case Activation::TANH:
        return std::tanh(z);
    case Activation::SIGMOID:
        return 1.0 / (1.0 + std::exp(-z));
    case Activation::NONE:
    default:
        return z;
    }
}

/// Derivative expressed in terms of the pre-activation z and output y.
double
Derivative(Activation a, double z, double y)
{
    switch (a)
    {
    case Activation::RELU:
        return z > 0.0 ? 1.0 : 0.0;
    case Activation::LEAKY_RELU:
        return z > 0.0 ? 1.0 : 0.01;
    case Activation::TANH:
        return 1.0 - y * y;
    case Activation::SIGMOID:
        return y * (1.0 - y);
    case Activation::NONE:
    default:
        return 1.0;
    }
}

void
AdamUpdate(Vec& p, Vec& g, Vec& m, Vec& v, double lr, uint64_t t, uint32_t batch)
{
    const double scale = (batch > 0) ? 1.0 / (double)batch : 1.0;
    const double bc1 = 1.0 - std::pow(kBeta1, (double)t);
    const double bc2 = 1.0 - std::pow(kBeta2, (double)t);
    for (size_t i = 0; i < p.size(); ++i)
    {
        double grad = g[i] * scale;
        grad = std::max(-kGradClip, std::min(kGradClip, grad));
        m[i] = kBeta1 * m[i] + (1.0 - kBeta1) * grad;
        v[i] = kBeta2 * v[i] + (1.0 - kBeta2) * grad * grad;
        const double mh = m[i] / bc1;
        const double vh = v[i] / bc2;
        p[i] -= lr * mh / (std::sqrt(vh) + kEps);
    }
}
} // namespace

double
Sigmoid(double x)
{
    return 1.0 / (1.0 + std::exp(-x));
}

// --------------------------------------------------------------------- Dense

Dense::Dense(uint32_t inDim, uint32_t outDim, Activation act, std::mt19937& rng)
    : m_in(inDim),
      m_out(outDim),
      m_act(act),
      m_w(inDim * outDim, 0.0),
      m_b(outDim, 0.0),
      m_gw(inDim * outDim, 0.0),
      m_gb(outDim, 0.0),
      m_mw(inDim * outDim, 0.0),
      m_vw(inDim * outDim, 0.0),
      m_mb(outDim, 0.0),
      m_vb(outDim, 0.0),
      m_t(0)
{
    // He initialisation for rectifiers, Xavier otherwise.
    const bool rectifier = (act == Activation::RELU || act == Activation::LEAKY_RELU);
    const double limit = rectifier ? std::sqrt(2.0 / (double)inDim)
                                   : std::sqrt(6.0 / (double)(inDim + outDim));
    std::normal_distribution<double> normal(0.0, limit);
    std::uniform_real_distribution<double> uniform(-limit, limit);
    for (auto& w : m_w)
    {
        w = rectifier ? normal(rng) : uniform(rng);
    }
}

const Vec&
Dense::Forward(const Vec& x)
{
    m_x = x;
    m_z.assign(m_out, 0.0);
    m_y.assign(m_out, 0.0);
    for (uint32_t o = 0; o < m_out; ++o)
    {
        double acc = m_b[o];
        const double* row = &m_w[(size_t)o * m_in];
        for (uint32_t i = 0; i < m_in; ++i)
        {
            acc += row[i] * x[i];
        }
        m_z[o] = acc;
        m_y[o] = Apply(m_act, acc);
    }
    return m_y;
}

void
Dense::Backward(const Vec& gradOut, Vec& gradIn)
{
    gradIn.assign(m_in, 0.0);
    for (uint32_t o = 0; o < m_out; ++o)
    {
        const double delta = gradOut[o] * Derivative(m_act, m_z[o], m_y[o]);
        m_gb[o] += delta;
        double* row = &m_gw[(size_t)o * m_in];
        const double* w = &m_w[(size_t)o * m_in];
        for (uint32_t i = 0; i < m_in; ++i)
        {
            row[i] += delta * m_x[i];
            gradIn[i] += delta * w[i];
        }
    }
}

void
Dense::ZeroGrad()
{
    std::fill(m_gw.begin(), m_gw.end(), 0.0);
    std::fill(m_gb.begin(), m_gb.end(), 0.0);
}

void
Dense::Step(double lr, uint32_t batch)
{
    m_t++;
    AdamUpdate(m_w, m_gw, m_mw, m_vw, lr, m_t, batch);
    AdamUpdate(m_b, m_gb, m_mb, m_vb, lr, m_t, batch);
}

void
Dense::CopyFrom(const Dense& other)
{
    m_w = other.m_w;
    m_b = other.m_b;
}

void
Dense::Polyak(const Dense& other, double tau)
{
    for (size_t i = 0; i < m_w.size(); ++i)
    {
        m_w[i] = (1.0 - tau) * m_w[i] + tau * other.m_w[i];
    }
    for (size_t i = 0; i < m_b.size(); ++i)
    {
        m_b[i] = (1.0 - tau) * m_b[i] + tau * other.m_b[i];
    }
}

// ----------------------------------------------------------------------- Mlp

void
Mlp::Add(uint32_t inDim, uint32_t outDim, Activation act, std::mt19937& rng)
{
    m_layers.emplace_back(inDim, outDim, act, rng);
}

const Vec&
Mlp::Forward(const Vec& x)
{
    const Vec* cur = &x;
    for (auto& layer : m_layers)
    {
        cur = &layer.Forward(*cur);
    }
    return *cur;
}

void
Mlp::Backward(const Vec& gradOut)
{
    Vec grad = gradOut;
    for (auto it = m_layers.rbegin(); it != m_layers.rend(); ++it)
    {
        it->Backward(grad, m_gradIn);
        grad = m_gradIn;
    }
}

void
Mlp::ZeroGrad()
{
    for (auto& layer : m_layers)
    {
        layer.ZeroGrad();
    }
}

void
Mlp::Step(double lr, uint32_t batch)
{
    for (auto& layer : m_layers)
    {
        layer.Step(lr, batch);
    }
}

void
Mlp::CopyFrom(const Mlp& other)
{
    for (size_t i = 0; i < m_layers.size() && i < other.m_layers.size(); ++i)
    {
        m_layers[i].CopyFrom(other.m_layers[i]);
    }
}

void
Mlp::Polyak(const Mlp& other, double tau)
{
    for (size_t i = 0; i < m_layers.size() && i < other.m_layers.size(); ++i)
    {
        m_layers[i].Polyak(other.m_layers[i], tau);
    }
}

// ------------------------------------------------------------- LstmRegressor

LstmRegressor::LstmRegressor(uint32_t inputDim, uint32_t hidden, uint32_t outputDim, uint32_t seed)
    : m_in(inputDim),
      m_hidden(hidden),
      m_out(outputDim),
      m_wx(4 * hidden * inputDim, 0.0),
      m_wh(4 * hidden * hidden, 0.0),
      m_bh(4 * hidden, 0.0),
      m_wy(outputDim * hidden, 0.0),
      m_by(outputDim, 0.0),
      m_gwx(4 * hidden * inputDim, 0.0),
      m_gwh(4 * hidden * hidden, 0.0),
      m_gbh(4 * hidden, 0.0),
      m_gwy(outputDim * hidden, 0.0),
      m_gby(outputDim, 0.0),
      m_mwx(4 * hidden * inputDim, 0.0),
      m_vwx(4 * hidden * inputDim, 0.0),
      m_mwh(4 * hidden * hidden, 0.0),
      m_vwh(4 * hidden * hidden, 0.0),
      m_mbh(4 * hidden, 0.0),
      m_vbh(4 * hidden, 0.0),
      m_mwy(outputDim * hidden, 0.0),
      m_vwy(outputDim * hidden, 0.0),
      m_mby(outputDim, 0.0),
      m_vby(outputDim, 0.0),
      m_t(0)
{
    std::mt19937 rng(seed);
    const double lx = std::sqrt(1.0 / (double)inputDim);
    const double lh = std::sqrt(1.0 / (double)hidden);
    std::uniform_real_distribution<double> ux(-lx, lx);
    std::uniform_real_distribution<double> uh(-lh, lh);
    for (auto& w : m_wx)
    {
        w = ux(rng);
    }
    for (auto& w : m_wh)
    {
        w = uh(rng);
    }
    for (auto& w : m_wy)
    {
        w = uh(rng);
    }
    // Forget-gate bias of 1: the standard trick that stops an untrained LSTM
    // from forgetting everything before it has learnt anything.
    for (uint32_t h = 0; h < m_hidden; ++h)
    {
        m_bh[m_hidden + h] = 1.0;
    }
}

void
LstmRegressor::Reset(size_t steps)
{
    m_xs.assign(steps, Vec(m_in, 0.0));
    m_is.assign(steps, Vec(m_hidden, 0.0));
    m_fs.assign(steps, Vec(m_hidden, 0.0));
    m_gs.assign(steps, Vec(m_hidden, 0.0));
    m_os.assign(steps, Vec(m_hidden, 0.0));
    m_cs.assign(steps, Vec(m_hidden, 0.0));
    m_hs.assign(steps, Vec(m_hidden, 0.0));
}

Vec
LstmRegressor::Forward(const std::vector<Vec>& sequence)
{
    const size_t T = sequence.size();
    Reset(T);
    Vec hPrev(m_hidden, 0.0);
    Vec cPrev(m_hidden, 0.0);

    for (size_t t = 0; t < T; ++t)
    {
        m_xs[t] = sequence[t];
        for (uint32_t h = 0; h < m_hidden; ++h)
        {
            double gate[4];
            for (uint32_t k = 0; k < 4; ++k)
            {
                const uint32_t row = k * m_hidden + h;
                double acc = m_bh[row];
                const double* wx = &m_wx[(size_t)row * m_in];
                for (uint32_t i = 0; i < m_in; ++i)
                {
                    acc += wx[i] * m_xs[t][i];
                }
                const double* wh = &m_wh[(size_t)row * m_hidden];
                for (uint32_t i = 0; i < m_hidden; ++i)
                {
                    acc += wh[i] * hPrev[i];
                }
                gate[k] = acc;
            }
            const double i_t = Sigmoid(gate[0]);
            const double f_t = Sigmoid(gate[1]);
            const double g_t = std::tanh(gate[2]);
            const double o_t = Sigmoid(gate[3]);
            const double c_t = f_t * cPrev[h] + i_t * g_t;
            const double h_t = o_t * std::tanh(c_t);

            m_is[t][h] = i_t;
            m_fs[t][h] = f_t;
            m_gs[t][h] = g_t;
            m_os[t][h] = o_t;
            m_cs[t][h] = c_t;
            m_hs[t][h] = h_t;
        }
        hPrev = m_hs[t];
        cPrev = m_cs[t];
    }

    Vec y(m_out, 0.0);
    for (uint32_t o = 0; o < m_out; ++o)
    {
        double acc = m_by[o];
        const double* row = &m_wy[(size_t)o * m_hidden];
        for (uint32_t h = 0; h < m_hidden; ++h)
        {
            acc += row[h] * hPrev[h];
        }
        y[o] = acc;
    }
    return y;
}

double
LstmRegressor::TrainStep(const std::vector<Vec>& sequence, const Vec& target, double lr)
{
    const size_t T = sequence.size();
    if (T == 0)
    {
        return 0.0;
    }
    const Vec y = Forward(sequence);

    std::fill(m_gwx.begin(), m_gwx.end(), 0.0);
    std::fill(m_gwh.begin(), m_gwh.end(), 0.0);
    std::fill(m_gbh.begin(), m_gbh.end(), 0.0);
    std::fill(m_gwy.begin(), m_gwy.end(), 0.0);
    std::fill(m_gby.begin(), m_gby.end(), 0.0);

    double loss = 0.0;
    Vec dh(m_hidden, 0.0);
    for (uint32_t o = 0; o < m_out; ++o)
    {
        const double err = y[o] - target[o];
        loss += 0.5 * err * err;
        m_gby[o] += err;
        double* row = &m_gwy[(size_t)o * m_hidden];
        const double* w = &m_wy[(size_t)o * m_hidden];
        for (uint32_t h = 0; h < m_hidden; ++h)
        {
            row[h] += err * m_hs[T - 1][h];
            dh[h] += err * w[h];
        }
    }

    Vec dc(m_hidden, 0.0);
    for (size_t t = T; t-- > 0;)
    {
        Vec dhPrev(m_hidden, 0.0);
        Vec dcPrev(m_hidden, 0.0);
        const Vec zero(m_hidden, 0.0);
        const Vec& cPrevStorage = (t > 0) ? m_cs[t - 1] : zero;
        const Vec& hPrevStorage = (t > 0) ? m_hs[t - 1] : zero;

        for (uint32_t h = 0; h < m_hidden; ++h)
        {
            const double tanhC = std::tanh(m_cs[t][h]);
            const double dO = dh[h] * tanhC;
            const double dCt = dc[h] + dh[h] * m_os[t][h] * (1.0 - tanhC * tanhC);

            const double dI = dCt * m_gs[t][h];
            const double dF = dCt * cPrevStorage[h];
            const double dG = dCt * m_is[t][h];

            const double gi = dI * m_is[t][h] * (1.0 - m_is[t][h]);
            const double gf = dF * m_fs[t][h] * (1.0 - m_fs[t][h]);
            const double gg = dG * (1.0 - m_gs[t][h] * m_gs[t][h]);
            const double go = dO * m_os[t][h] * (1.0 - m_os[t][h]);
            const double gates[4] = {gi, gf, gg, go};

            dcPrev[h] += dCt * m_fs[t][h];

            for (uint32_t k = 0; k < 4; ++k)
            {
                const uint32_t row = k * m_hidden + h;
                m_gbh[row] += gates[k];
                double* gwx = &m_gwx[(size_t)row * m_in];
                for (uint32_t i = 0; i < m_in; ++i)
                {
                    gwx[i] += gates[k] * m_xs[t][i];
                }
                double* gwh = &m_gwh[(size_t)row * m_hidden];
                const double* wh = &m_wh[(size_t)row * m_hidden];
                for (uint32_t i = 0; i < m_hidden; ++i)
                {
                    gwh[i] += gates[k] * hPrevStorage[i];
                    dhPrev[i] += gates[k] * wh[i];
                }
            }
        }
        dh = dhPrev;
        dc = dcPrev;
    }

    m_t++;
    AdamUpdate(m_wx, m_gwx, m_mwx, m_vwx, lr, m_t, 1);
    AdamUpdate(m_wh, m_gwh, m_mwh, m_vwh, lr, m_t, 1);
    AdamUpdate(m_bh, m_gbh, m_mbh, m_vbh, lr, m_t, 1);
    AdamUpdate(m_wy, m_gwy, m_mwy, m_vwy, lr, m_t, 1);
    AdamUpdate(m_by, m_gby, m_mby, m_vby, lr, m_t, 1);

    return loss;
}

} // namespace arEaurp
} // namespace ns3
