#include "ar-eaurp-rtable.h"

#include "ns3/log.h"
#include "ns3/simulator.h"

#include <algorithm>
#include <iomanip>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("ArEaurpRoutingTable");

namespace arEaurp
{

RoutingTableEntry::RoutingTableEntry(Ptr<NetDevice> dev,
                                     Ipv4Address dst,
                                     bool vSeqNo,
                                     uint32_t seqNo,
                                     Ipv4InterfaceAddress iface,
                                     uint16_t hops,
                                     Ipv4Address nextHop,
                                     Time lifetime,
                                     uint32_t pathCost)
    : m_seqNo(seqNo),
      m_hops(hops),
      m_lifeTime(lifetime + Simulator::Now()),
      m_iface(iface),
      m_flag(VALID),
      m_pathCost(pathCost),
      m_reqCount(0),
      m_blackListState(false),
      m_blackListTimeout(Simulator::Now()),
      m_validSeqNo(vSeqNo)
{
    m_ipv4Route = Create<Ipv4Route>();
    m_ipv4Route->SetDestination(dst);
    m_ipv4Route->SetGateway(nextHop);
    m_ipv4Route->SetSource(m_iface.GetLocal());
    m_ipv4Route->SetOutputDevice(dev);
}

RoutingTableEntry::~RoutingTableEntry()
{
}

bool
RoutingTableEntry::InsertPrecursor(Ipv4Address id)
{
    if (!LookupPrecursor(id))
    {
        m_precursorList.push_back(id);
        return true;
    }
    return false;
}

bool
RoutingTableEntry::LookupPrecursor(Ipv4Address id)
{
    return std::find(m_precursorList.begin(), m_precursorList.end(), id) != m_precursorList.end();
}

bool
RoutingTableEntry::DeletePrecursor(Ipv4Address id)
{
    auto i = std::remove(m_precursorList.begin(), m_precursorList.end(), id);
    if (i == m_precursorList.end())
    {
        return false;
    }
    m_precursorList.erase(i, m_precursorList.end());
    return true;
}

void
RoutingTableEntry::DeleteAllPrecursors()
{
    m_precursorList.clear();
}

bool
RoutingTableEntry::IsPrecursorListEmpty() const
{
    return m_precursorList.empty();
}

void
RoutingTableEntry::GetPrecursors(std::vector<Ipv4Address>& prec) const
{
    if (IsPrecursorListEmpty())
    {
        return;
    }
    for (auto i = m_precursorList.begin(); i != m_precursorList.end(); ++i)
    {
        if (std::find(prec.begin(), prec.end(), *i) == prec.end())
        {
            prec.push_back(*i);
        }
    }
}

void
RoutingTableEntry::Invalidate(Time badLinkLifetime)
{
    if (m_flag == INVALID)
    {
        return;
    }
    m_flag = INVALID;
    m_reqCount = 0;
    m_lifeTime = badLinkLifetime + Simulator::Now();
}

void
RoutingTableEntry::Print(Ptr<OutputStreamWrapper> stream) const
{
    std::ostream* os = stream->GetStream();
    *os << std::setiosflags(std::ios::fixed) << m_ipv4Route->GetDestination() << "\t\t"
        << m_ipv4Route->GetGateway() << "\t\t" << m_iface.GetLocal() << "\t\t";
    switch (m_flag)
    {
    case VALID:
        *os << "UP";
        break;
    case INVALID:
        *os << "DOWN";
        break;
    case IN_SEARCH:
        *os << "IN_SEARCH";
        break;
    }
    *os << "\t\t" << std::setprecision(3) << (m_lifeTime - Simulator::Now()).As(Time::S) << "\t\t"
        << m_hops << "\t\t" << m_pathCost << "\n";
}

// ---------------------------------------------------------------------------

RoutingTable::RoutingTable(Time t)
    : m_badLinkLifetime(t)
{
}

bool
RoutingTable::LookupRoute(Ipv4Address id, RoutingTableEntry& rt)
{
    Purge();
    if (m_ipv4AddressEntry.empty())
    {
        return false;
    }
    auto i = m_ipv4AddressEntry.find(id);
    if (i == m_ipv4AddressEntry.end())
    {
        return false;
    }
    rt = i->second;
    return true;
}

bool
RoutingTable::LookupValidRoute(Ipv4Address id, RoutingTableEntry& rt)
{
    if (!LookupRoute(id, rt))
    {
        return false;
    }
    return (rt.GetFlag() == VALID);
}

bool
RoutingTable::DeleteRoute(Ipv4Address dst)
{
    Purge();
    return m_ipv4AddressEntry.erase(dst) != 0;
}

bool
RoutingTable::AddRoute(RoutingTableEntry& rt)
{
    Purge();
    if (rt.GetFlag() != IN_SEARCH)
    {
        rt.SetRreqCnt(0);
    }
    auto result = m_ipv4AddressEntry.insert(std::make_pair(rt.GetDestination(), rt));
    return result.second;
}

bool
RoutingTable::Update(RoutingTableEntry& rt)
{
    auto i = m_ipv4AddressEntry.find(rt.GetDestination());
    if (i == m_ipv4AddressEntry.end())
    {
        return false;
    }
    i->second = rt;
    if (i->second.GetFlag() != IN_SEARCH)
    {
        i->second.SetRreqCnt(0);
    }
    return true;
}

bool
RoutingTable::SetEntryState(Ipv4Address id, RouteFlags state)
{
    auto i = m_ipv4AddressEntry.find(id);
    if (i == m_ipv4AddressEntry.end())
    {
        return false;
    }
    i->second.SetFlag(state);
    i->second.SetRreqCnt(0);
    return true;
}

void
RoutingTable::GetListOfDestinationWithNextHop(Ipv4Address nextHop,
                                              std::map<Ipv4Address, uint32_t>& unreachable)
{
    Purge();
    unreachable.clear();
    for (auto i = m_ipv4AddressEntry.begin(); i != m_ipv4AddressEntry.end(); ++i)
    {
        if (i->second.GetNextHop() == nextHop)
        {
            unreachable.insert(std::make_pair(i->first, i->second.GetSeqNo()));
        }
    }
}

void
RoutingTable::InvalidateRoutesWithDst(const std::map<Ipv4Address, uint32_t>& unreachable)
{
    Purge();
    for (auto i = m_ipv4AddressEntry.begin(); i != m_ipv4AddressEntry.end(); ++i)
    {
        for (auto j = unreachable.begin(); j != unreachable.end(); ++j)
        {
            if ((i->first == j->first) && (i->second.GetFlag() == VALID))
            {
                i->second.Invalidate(m_badLinkLifetime);
                i->second.SetSeqNo(j->second);
            }
        }
    }
}

void
RoutingTable::InvalidateRoutesWithNextHop(Ipv4Address nextHop, Time badLinkLifetime)
{
    for (auto i = m_ipv4AddressEntry.begin(); i != m_ipv4AddressEntry.end(); ++i)
    {
        if (i->second.GetNextHop() == nextHop && i->second.GetFlag() == VALID)
        {
            i->second.Invalidate(badLinkLifetime);
        }
    }
}

void
RoutingTable::DeleteAllRoutesFromInterface(Ipv4InterfaceAddress iface)
{
    if (m_ipv4AddressEntry.empty())
    {
        return;
    }
    for (auto i = m_ipv4AddressEntry.begin(); i != m_ipv4AddressEntry.end();)
    {
        if (i->second.GetInterface() == iface)
        {
            auto tmp = i;
            ++i;
            m_ipv4AddressEntry.erase(tmp);
        }
        else
        {
            ++i;
        }
    }
}

void
RoutingTable::Purge()
{
    if (m_ipv4AddressEntry.empty())
    {
        return;
    }
    for (auto i = m_ipv4AddressEntry.begin(); i != m_ipv4AddressEntry.end();)
    {
        if (i->second.GetLifeTime() < Seconds(0))
        {
            if (i->second.GetFlag() == INVALID)
            {
                auto tmp = i;
                ++i;
                m_ipv4AddressEntry.erase(tmp);
            }
            else if (i->second.GetFlag() == VALID)
            {
                i->second.Invalidate(m_badLinkLifetime);
                ++i;
            }
            else
            {
                ++i;
            }
        }
        else
        {
            ++i;
        }
    }
}

bool
RoutingTable::MarkLinkAsUnidirectional(Ipv4Address neighbour, Time blacklistTimeout)
{
    auto i = m_ipv4AddressEntry.find(neighbour);
    if (i == m_ipv4AddressEntry.end())
    {
        return false;
    }
    i->second.Invalidate(blacklistTimeout);
    return true;
}

void
RoutingTable::Print(Ptr<OutputStreamWrapper> stream) const
{
    std::map<Ipv4Address, RoutingTableEntry> table = m_ipv4AddressEntry;
    Purge(table);
    std::ostream* os = stream->GetStream();
    *os << "\nAR-EAURP Routing table\n"
        << "Destination\tGateway\t\tInterface\tFlag\tExpire\t\tHops\tCost\n";
    for (auto i = table.begin(); i != table.end(); ++i)
    {
        i->second.Print(stream);
    }
    *os << "\n";
}

void
RoutingTable::Purge(std::map<Ipv4Address, RoutingTableEntry>& table) const
{
    for (auto i = table.begin(); i != table.end();)
    {
        if (i->second.GetLifeTime() < Seconds(0))
        {
            if (i->second.GetFlag() == INVALID)
            {
                auto tmp = i;
                ++i;
                table.erase(tmp);
            }
            else if (i->second.GetFlag() == VALID)
            {
                i->second.Invalidate(m_badLinkLifetime);
                ++i;
            }
            else
            {
                ++i;
            }
        }
        else
        {
            ++i;
        }
    }
}

} // namespace arEaurp
} // namespace ns3
