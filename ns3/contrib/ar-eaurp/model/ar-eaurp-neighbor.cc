#include "ar-eaurp-neighbor.h"

#include "ns3/log.h"

#include <algorithm>
#include <cmath>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("ArEaurpNeighbor");

namespace arEaurp
{

NeighborTrust::NeighborTrust()
    : m_neighbourLifetime(Seconds(30)),
      m_watchdogTimeout(MilliSeconds(400)),
      m_smoothing(0.7),
      m_trustThreshold(0.6),
      m_minObservations(5),
      m_largePacketThreshold(700)
{
}

void
NeighborTrust::SetParameters(Time neighbourLifetime,
                             Time watchdogTimeout,
                             double smoothing,
                             double trustThreshold,
                             uint32_t minObservations,
                             uint32_t largePacketThreshold)
{
    m_neighbourLifetime = neighbourLifetime;
    m_watchdogTimeout = watchdogTimeout;
    m_smoothing = smoothing;
    m_trustThreshold = trustThreshold;
    m_minObservations = minObservations;
    m_largePacketThreshold = largePacketThreshold;
}

void
NeighborTrust::Refresh(Ipv4Address addr, Mac48Address mac, double energyFraction, double surplus)
{
    auto& e = m_table[addr];
    e.addr = addr;
    if (mac != Mac48Address())
    {
        e.mac = mac;
        m_macToIp[mac] = addr;
    }
    e.expire = Simulator::Now() + m_neighbourLifetime;
    e.energyFraction = energyFraction;
    e.surplus = surplus;
}

void
NeighborTrust::NoteBeacon(Ipv4Address addr, bool heardMe, Time symmetryLifetime)
{
    auto& e = m_table[addr];
    e.addr = addr;
    e.beaconsThisWindow++;
    if (heardMe)
    {
        e.heardMeUntil = Simulator::Now() + symmetryLifetime;
    }
}

void
NeighborTrust::NoteAdvertisedNeighbours(Ipv4Address addr, const std::vector<Ipv4Address>& links)
{
    auto& e = m_table[addr];
    e.addr = addr;
    e.advertised = links;
}

uint32_t
NeighborTrust::AdditionalCoverage(Ipv4Address previousHop, double qualityThreshold) const
{
    auto prev = m_table.find(previousHop);
    if (prev == m_table.end() || prev->second.advertised.empty())
    {
        return (uint32_t)m_table.size(); // nothing known about its reach: forward
    }
    const std::set<Ipv4Address> covered(prev->second.advertised.begin(),
                                        prev->second.advertised.end());
    uint32_t extra = 0;
    for (const auto& kv : m_table)
    {
        if (kv.first == previousHop)
        {
            continue;
        }
        if (!IsUsableLink(kv.first, qualityThreshold))
        {
            continue;
        }
        if (!covered.count(kv.first))
        {
            extra++;
        }
    }
    return extra;
}

void
NeighborTrust::TickLinkQuality(double weight, double initialQuality, double high, double low)
{
    for (auto& kv : m_table)
    {
        NeighborEntry& e = kv.second;
        const bool heard = (e.beaconsThisWindow > 0);
        if (e.quality <= 0.0 && heard)
        {
            // First beacon from a new neighbour: start optimistic enough to be
            // usable, low enough that one lucky frame does not make a route.
            e.quality = initialQuality;
        }
        else
        {
            e.quality = (1.0 - weight) * e.quality + weight * (heard ? 1.0 : 0.0);
        }
        e.beaconsThisWindow = 0;
        e.usable = e.usable ? (e.quality >= low) : (e.quality >= high);
    }
}

bool
NeighborTrust::IsUsableLink(Ipv4Address addr, double qualityThreshold) const
{
    auto i = m_table.find(addr);
    if (i == m_table.end())
    {
        return false;
    }
    const NeighborEntry& e = i->second;
    (void)qualityThreshold;
    return (e.expire > Simulator::Now()) && e.usable && (e.heardMeUntil > Simulator::Now());
}

double
NeighborTrust::GetQuality(Ipv4Address addr) const
{
    auto i = m_table.find(addr);
    return (i == m_table.end()) ? 0.0 : i->second.quality;
}

bool
NeighborTrust::IsNeighbor(Ipv4Address addr)
{
    auto i = m_table.find(addr);
    return (i != m_table.end() && i->second.expire > Simulator::Now());
}

void
NeighborTrust::Purge()
{
    // Entries are kept (trust is long-lived state) but a stale neighbour is no
    // longer treated as adjacent; only the MAC binding is dropped, so that a
    // recycled address cannot inherit somebody else's reputation.
    for (auto& kv : m_table)
    {
        if (kv.second.expire <= Simulator::Now() && kv.second.mac != Mac48Address())
        {
            m_macToIp.erase(kv.second.mac);
            kv.second.mac = Mac48Address();
        }
    }
}

void
NeighborTrust::BindMac(Mac48Address mac, Ipv4Address addr)
{
    m_macToIp[mac] = addr;
    auto& e = m_table[addr];
    e.addr = addr;
    e.mac = mac;
}

bool
NeighborTrust::LookupMac(Mac48Address mac, Ipv4Address& addr) const
{
    auto i = m_macToIp.find(mac);
    if (i == m_macToIp.end())
    {
        return false;
    }
    addr = i->second;
    return true;
}

void
NeighborTrust::ArmWatchdog(Ipv4Address nextHop, uint64_t digest, uint32_t payloadSize)
{
    PendingWatch w;
    w.nextHop = nextHop;
    w.digest = digest;
    w.size = payloadSize;
    w.armed = Simulator::Now();
    w.deadline = Simulator::Now() + m_watchdogTimeout;
    m_pending.push_back(w);

    auto& e = m_table[nextHop];
    e.addr = nextHop;
    e.requested += 1.0;
    if (payloadSize >= m_largePacketThreshold)
    {
        e.requestedLarge += 1.0;
    }
    else
    {
        e.requestedSmall += 1.0;
    }
}

bool
NeighborTrust::ConfirmWatchdog(Mac48Address from, uint64_t digest)
{
    Ipv4Address addr;
    if (!LookupMac(from, addr))
    {
        watchUnknownMac++;
        return false;
    }
    bool sawPending = false;
    for (auto i = m_pending.begin(); i != m_pending.end(); ++i)
    {
        if (i->nextHop == addr)
        {
            sawPending = true;
        }
        if (i->digest == digest && i->nextHop == addr)
        {
            auto& e = m_table[addr];
            const double latency = (Simulator::Now() - i->armed).GetSeconds();
            e.observed += 1.0;
            if (i->size >= m_largePacketThreshold)
            {
                e.observedLarge += 1.0;
            }
            else
            {
                e.observedSmall += 1.0;
            }
            e.latencySum += latency;
            e.latencySumSq += latency * latency;
            e.latencyCount += 1.0;
            m_pending.erase(i);
            return true;
        }
    }
    if (sawPending)
    {
        watchDigestMiss++;
    }
    else
    {
        watchNoPending++;
    }
    return false;
}

bool
NeighborTrust::CancelWatchdog(Ipv4Address nextHop, uint64_t digest)
{
    for (auto i = m_pending.begin(); i != m_pending.end(); ++i)
    {
        if (i->digest == digest && i->nextHop == nextHop)
        {
            auto e = m_table.find(nextHop);
            if (e != m_table.end())
            {
                e->second.requested = std::max(0.0, e->second.requested - 1.0);
                if (i->size >= m_largePacketThreshold)
                {
                    e->second.requestedLarge = std::max(0.0, e->second.requestedLarge - 1.0);
                }
                else
                {
                    e->second.requestedSmall = std::max(0.0, e->second.requestedSmall - 1.0);
                }
            }
            m_pending.erase(i);
            return true;
        }
    }
    return false;
}

void
NeighborTrust::ExpireWatchdogs()
{
    const Time now = Simulator::Now();
    // An entry that times out is simply left counted as "requested but not
    // observed", which is what drives PFR down.
    m_pending.erase(std::remove_if(m_pending.begin(),
                                   m_pending.end(),
                                   [now](const PendingWatch& w) { return w.deadline <= now; }),
                    m_pending.end());
}

void
NeighborTrust::RefreshTrust()
{
    for (auto& kv : m_table)
    {
        NeighborEntry& e = kv.second;
        if (e.requested <= 0.0)
        {
            continue;
        }
        const double pfr = e.WindowPfr();
        e.trust = m_smoothing * e.trust + (1.0 - m_smoothing) * pfr;
        e.trust = std::min(1.0, std::max(0.0, e.trust));
    }
}

double
NeighborTrust::GetTrust(Ipv4Address addr) const
{
    auto i = m_table.find(addr);
    return (i == m_table.end()) ? 1.0 : i->second.trust;
}

double
NeighborTrust::GetEnergyFraction(Ipv4Address addr) const
{
    auto i = m_table.find(addr);
    return (i == m_table.end()) ? 1.0 : i->second.energyFraction;
}

double
NeighborTrust::GetSurplus(Ipv4Address addr) const
{
    auto i = m_table.find(addr);
    return (i == m_table.end()) ? 0.0 : i->second.surplus;
}

bool
NeighborTrust::IsContested(Ipv4Address addr) const
{
    auto i = m_table.find(addr);
    return (i != m_table.end() && i->second.contested);
}

void
NeighborTrust::SetContested(Ipv4Address addr, Time until, double score)
{
    auto& e = m_table[addr];
    e.addr = addr;
    e.contested = true;
    e.contestedUntil = until;
    e.anomalyScore = score;
}

void
NeighborTrust::ExpireContested()
{
    for (auto& kv : m_table)
    {
        if (kv.second.contested && kv.second.contestedUntil <= Simulator::Now())
        {
            kv.second.contested = false;
        }
    }
}

std::vector<std::pair<Ipv4Address, double>>
NeighborTrust::BuildOpinions() const
{
    std::vector<std::pair<Ipv4Address, double>> out;
    for (const auto& kv : m_table)
    {
        if (kv.second.requested >= (double)m_minObservations)
        {
            out.emplace_back(kv.first, kv.second.trust);
        }
    }
    return out;
}

void
NeighborTrust::AddOpinion(Ipv4Address observer, Ipv4Address subject, double trust)
{
    Opinion o;
    o.trust = trust;
    o.received = Simulator::Now();
    m_opinions[subject][observer] = o;
}

void
NeighborTrust::PurgeOpinions(Time maxAge)
{
    const Time cutoff = Simulator::Now() - maxAge;
    for (auto s = m_opinions.begin(); s != m_opinions.end();)
    {
        for (auto o = s->second.begin(); o != s->second.end();)
        {
            if (o->second.received < cutoff)
            {
                o = s->second.erase(o);
            }
            else
            {
                ++o;
            }
        }
        if (s->second.empty())
        {
            s = m_opinions.erase(s);
        }
        else
        {
            ++s;
        }
    }
}

std::vector<Ipv4Address>
NeighborTrust::Consensus(double fraction,
                         uint32_t minAccusers,
                         bool energyExcuse,
                         double energyThresholdFraction) const
{
    std::vector<Ipv4Address> condemned;
    for (const auto& s : m_opinions)
    {
        const Ipv4Address subject = s.first;
        if (m_revoked.count(subject))
        {
            continue;
        }
        uint32_t observers = 0;
        uint32_t accusers = 0;
        for (const auto& o : s.second)
        {
            observers++;
            if (o.second.trust < m_trustThreshold)
            {
                accusers++;
            }
        }
        if (observers < minAccusers)
        {
            continue;
        }
        const uint32_t needed =
            std::max<uint32_t>(minAccusers, (uint32_t)std::ceil(fraction * (double)observers));
        if (accusers < needed)
        {
            continue;
        }
        if (energyExcuse)
        {
            // base.pdf 3.7: "before labeling it malicious, the energy level
            // will be checked" -- a node too flat to relay is not malicious.
            auto n = m_table.find(subject);
            if (n != m_table.end() && n->second.energyFraction <= energyThresholdFraction)
            {
                continue;
            }
        }
        condemned.push_back(subject);
    }
    return condemned;
}

void
NeighborTrust::Revoke(Ipv4Address addr)
{
    m_revoked.insert(addr);
}

bool
NeighborTrust::IsRevoked(Ipv4Address addr) const
{
    return m_revoked.count(addr) > 0;
}

double
NeighborTrust::Disagreement(Ipv4Address subject) const
{
    auto s = m_opinions.find(subject);
    if (s == m_opinions.end() || s->second.size() < 2)
    {
        return 0.0;
    }
    std::vector<double> values;
    values.reserve(s->second.size());
    for (const auto& o : s->second)
    {
        values.push_back(o.second.trust);
    }
    std::sort(values.begin(), values.end());
    const size_t n = values.size();
    const double median =
        (n % 2 == 1) ? values[n / 2] : 0.5 * (values[n / 2 - 1] + values[n / 2]);

    // Spread of published opinions around their median. A node whose watchers
    // disagree sharply about it is either being slandered or is behaving
    // differently towards different neighbours -- both are worth flagging.
    double spread = 0.0;
    for (double v : values)
    {
        spread += std::fabs(v - median);
    }
    return spread / (double)n;
}

void
NeighborTrust::ExtractFeatures(std::vector<Ipv4Address>& subjects,
                               std::vector<std::vector<double>>& features,
                               bool updateSnapshot,
                               uint32_t minWindow)
{
    subjects.clear();
    features.clear();

    for (auto& kv : m_table)
    {
        NeighborEntry& e = kv.second;
        const double dRequested = e.requested - e.prevRequested;
        if (e.requested < (double)m_minObservations || dRequested < (double)minWindow)
        {
            continue;
        }

        const double dObserved = e.observed - e.prevObserved;
        const double dReqLarge = e.requestedLarge - e.prevRequestedLarge;
        const double dObsLarge = e.observedLarge - e.prevObservedLarge;
        const double dReqSmall = e.requestedSmall - e.prevRequestedSmall;
        const double dObsSmall = e.observedSmall - e.prevObservedSmall;

        const double pfrShort = dObserved / dRequested;
        const double pfrLong = e.Pfr();
        const double dropLarge = (dReqLarge > 0.0) ? (1.0 - dObsLarge / dReqLarge) : 0.0;
        const double dropSmall = (dReqSmall > 0.0) ? (1.0 - dObsSmall / dReqSmall) : 0.0;

        double latMean = 0.0;
        double latStd = 0.0;
        if (e.latencyCount > 0.0)
        {
            latMean = e.latencySum / e.latencyCount;
            const double second = e.latencySumSq / e.latencyCount;
            latStd = std::sqrt(std::max(0.0, second - latMean * latMean));
        }

        std::vector<double> f(kFeatureDim, 0.0);
        f[0] = pfrShort;
        f[1] = pfrLong;
        f[2] = pfrShort - pfrLong;
        f[3] = dropLarge;
        f[4] = dropSmall;
        // Watchdog latencies are on the order of a few milliseconds; scaling by
        // 100 ms puts them on the same footing as the ratio features so no
        // single input dominates the discriminator purely by magnitude.
        f[5] = std::min(2.0, latMean / 0.1);
        f[6] = std::min(2.0, latStd / 0.1);
        f[7] = Disagreement(kv.first);
        // The differential itself. A selective-forwarding gray-hole is defined
        // by this one number being large while every individual ratio stays
        // defensible; giving it to the detector directly, rather than asking it
        // to infer the difference of two noisy columns, is what makes the
        // attack separable from a handful of observations.
        f[8] = dropLarge - dropSmall;

        for (auto& v : f)
        {
            if (!std::isfinite(v))
            {
                v = 0.0;
            }
            v = std::max(-1.0, std::min(2.0, v));
        }

        subjects.push_back(kv.first);
        features.push_back(f);
    }

    if (updateSnapshot)
    {
        for (auto& kv : m_table)
        {
            NeighborEntry& e = kv.second;
            e.prevRequested = e.requested;
            e.prevObserved = e.observed;
            e.prevRequestedLarge = e.requestedLarge;
            e.prevObservedLarge = e.observedLarge;
            e.prevRequestedSmall = e.requestedSmall;
            e.prevObservedSmall = e.observedSmall;
        }
    }
}

} // namespace arEaurp
} // namespace ns3
