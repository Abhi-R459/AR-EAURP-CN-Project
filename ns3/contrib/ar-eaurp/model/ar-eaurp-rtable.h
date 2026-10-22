/*
 * AR-EAURP routing table.
 *
 * A reactive (AODV-family) table: one entry per destination, holding the next
 * hop, the hop count, the destination sequence number and -- the EAURP
 * addition -- the accumulated route cost the reply arrived with. The cost is
 * what lets a node prefer a longer but more trustworthy and better-powered
 * path over a short one through a suspect relay.
 */

#ifndef AR_EAURP_RTABLE_H
#define AR_EAURP_RTABLE_H

#include "ns3/ipv4-route.h"
#include "ns3/ipv4.h"
#include "ns3/net-device.h"
#include "ns3/nstime.h"
#include "ns3/output-stream-wrapper.h"
#include "ns3/timer.h"

#include <cassert>
#include <map>
#include <sys/types.h>
#include <vector>

namespace ns3
{
namespace arEaurp
{

/// Route state, as in RFC 3561.
enum RouteFlags
{
    VALID = 0,
    INVALID = 1,
    IN_SEARCH = 2,
};

/**
 * \brief One routing table entry.
 */
class RoutingTableEntry
{
  public:
    RoutingTableEntry(Ptr<NetDevice> dev = nullptr,
                      Ipv4Address dst = Ipv4Address(),
                      bool vSeqNo = false,
                      uint32_t seqNo = 0,
                      Ipv4InterfaceAddress iface = Ipv4InterfaceAddress(),
                      uint16_t hops = 0,
                      Ipv4Address nextHop = Ipv4Address(),
                      Time lifetime = Simulator::Now(),
                      uint32_t pathCost = 0);

    ~RoutingTableEntry();

    bool InsertPrecursor(Ipv4Address id);
    bool LookupPrecursor(Ipv4Address id);
    bool DeletePrecursor(Ipv4Address id);
    void DeleteAllPrecursors();
    bool IsPrecursorListEmpty() const;
    void GetPrecursors(std::vector<Ipv4Address>& prec) const;

    void Invalidate(Time badLinkLifetime);

    void SetDestination(Ipv4Address dst)
    {
        m_ipv4Route->SetDestination(dst);
    }

    Ipv4Address GetDestination() const
    {
        return m_ipv4Route->GetDestination();
    }

    Ptr<Ipv4Route> GetRoute() const
    {
        return m_ipv4Route;
    }

    void SetRoute(Ptr<Ipv4Route> r)
    {
        m_ipv4Route = r;
    }

    void SetNextHop(Ipv4Address nextHop)
    {
        m_ipv4Route->SetGateway(nextHop);
    }

    Ipv4Address GetNextHop() const
    {
        return m_ipv4Route->GetGateway();
    }

    void SetOutputDevice(Ptr<NetDevice> dev)
    {
        m_ipv4Route->SetOutputDevice(dev);
    }

    Ptr<NetDevice> GetOutputDevice() const
    {
        return m_ipv4Route->GetOutputDevice();
    }

    Ipv4InterfaceAddress GetInterface() const
    {
        return m_iface;
    }

    void SetInterface(Ipv4InterfaceAddress iface)
    {
        m_iface = iface;
    }

    void SetValidSeqNo(bool s)
    {
        m_validSeqNo = s;
    }

    bool GetValidSeqNo() const
    {
        return m_validSeqNo;
    }

    void SetSeqNo(uint32_t sn)
    {
        m_seqNo = sn;
    }

    uint32_t GetSeqNo() const
    {
        return m_seqNo;
    }

    void SetHop(uint16_t hop)
    {
        m_hops = hop;
    }

    uint16_t GetHop() const
    {
        return m_hops;
    }

    void SetLifeTime(Time lt)
    {
        m_lifeTime = lt + Simulator::Now();
    }

    Time GetLifeTime() const
    {
        return m_lifeTime - Simulator::Now();
    }

    void SetFlag(RouteFlags flag)
    {
        m_flag = flag;
    }

    RouteFlags GetFlag() const
    {
        return m_flag;
    }

    void SetPathCost(uint32_t c)
    {
        m_pathCost = c;
    }

    uint32_t GetPathCost() const
    {
        return m_pathCost;
    }

    void IncrementRreqCnt()
    {
        m_reqCount++;
    }

    void SetRreqCnt(uint8_t n)
    {
        m_reqCount = n;
    }

    uint8_t GetRreqCnt() const
    {
        return m_reqCount;
    }

    bool operator==(const Ipv4Address dst) const
    {
        return (m_ipv4Route->GetDestination() == dst);
    }

    void Print(Ptr<OutputStreamWrapper> stream) const;

  private:
    uint32_t m_seqNo;
    uint16_t m_hops;
    Time m_lifeTime;
    Ptr<Ipv4Route> m_ipv4Route;
    Ipv4InterfaceAddress m_iface;
    RouteFlags m_flag;
    uint32_t m_pathCost; //!< accumulated EAURP route cost, milli-units
    std::vector<Ipv4Address> m_precursorList;
    uint8_t m_reqCount;
    bool m_blackListState;
    Time m_blackListTimeout;
    bool m_validSeqNo;
};

/**
 * \brief The table itself, plus purge/invalidate helpers.
 */
class RoutingTable
{
  public:
    RoutingTable(Time t);

    bool LookupRoute(Ipv4Address dst, RoutingTableEntry& rt);
    bool LookupValidRoute(Ipv4Address dst, RoutingTableEntry& rt);
    bool DeleteRoute(Ipv4Address dst);
    bool AddRoute(RoutingTableEntry& r);
    bool Update(RoutingTableEntry& rt);
    bool SetEntryState(Ipv4Address dst, RouteFlags state);

    /// Every destination currently reached through nextHop, with its seqno.
    void GetListOfDestinationWithNextHop(Ipv4Address nextHop,
                                         std::map<Ipv4Address, uint32_t>& unreachable);

    void InvalidateRoutesWithDst(const std::map<Ipv4Address, uint32_t>& unreachable);

    /// Kill every route whose next hop is this node (used by PT_CREV).
    void DeleteAllRoutesFromInterface(Ipv4InterfaceAddress iface);

    /// Invalidate every route that goes through a revoked neighbour.
    void InvalidateRoutesWithNextHop(Ipv4Address nextHop, Time badLinkLifetime);

    void Clear()
    {
        m_ipv4AddressEntry.clear();
    }

    void Purge();
    bool MarkLinkAsUnidirectional(Ipv4Address neighbour, Time blacklistTimeout);

    void SetBadLinkLifetime(Time t)
    {
        m_badLinkLifetime = t;
    }

    Time GetBadLinkLifetime() const
    {
        return m_badLinkLifetime;
    }

    void Print(Ptr<OutputStreamWrapper> stream) const;

  private:
    std::map<Ipv4Address, RoutingTableEntry> m_ipv4AddressEntry;
    Time m_badLinkLifetime;

    void Purge(std::map<Ipv4Address, RoutingTableEntry>& table) const;
};

} // namespace arEaurp
} // namespace ns3

#endif /* AR_EAURP_RTABLE_H */
