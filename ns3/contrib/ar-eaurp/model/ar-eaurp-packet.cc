#include "ar-eaurp-packet.h"

#include "ns3/address-utils.h"
#include "ns3/packet.h"

#include <algorithm>
#include <cmath>

namespace ns3
{
namespace arEaurp
{

namespace
{
/// Quantise a [0,1] value into one byte; the wire cost of a trust report is
/// one byte per neighbour, which is what makes PT_NID cheap enough to beacon.
uint8_t
Quantise(double v)
{
    if (v < 0.0)
    {
        v = 0.0;
    }
    if (v > 1.0)
    {
        v = 1.0;
    }
    return static_cast<uint8_t>(std::lround(v * 255.0));
}

double
Dequantise(uint8_t v)
{
    return static_cast<double>(v) / 255.0;
}
} // namespace

// ---------------------------------------------------------------- TypeHeader

NS_OBJECT_ENSURE_REGISTERED(TypeHeader);

TypeHeader::TypeHeader(MessageType t)
    : m_type(t),
      m_valid(true)
{
}

TypeId
TypeHeader::GetTypeId()
{
    static TypeId tid = TypeId("ns3::arEaurp::TypeHeader")
                            .SetParent<Header>()
                            .SetGroupName("ArEaurp")
                            .AddConstructor<TypeHeader>();
    return tid;
}

TypeId
TypeHeader::GetInstanceTypeId() const
{
    return GetTypeId();
}

uint32_t
TypeHeader::GetSerializedSize() const
{
    return 1;
}

void
TypeHeader::Serialize(Buffer::Iterator i) const
{
    i.WriteU8((uint8_t)m_type);
}

uint32_t
TypeHeader::Deserialize(Buffer::Iterator start)
{
    Buffer::Iterator i = start;
    uint8_t type = i.ReadU8();
    m_valid = true;
    switch (type)
    {
    case AREAURP_RREQ:
    case AREAURP_RREP:
    case AREAURP_RERR:
    case AREAURP_RREP_ACK:
    case AREAURP_NID:
    case AREAURP_GID:
    case AREAURP_CREV:
        m_type = (MessageType)type;
        break;
    default:
        m_valid = false;
    }
    return i.GetDistanceFrom(start);
}

void
TypeHeader::Print(std::ostream& os) const
{
    switch (m_type)
    {
    case AREAURP_RREQ:
        os << "RREQ";
        break;
    case AREAURP_RREP:
        os << "RREP";
        break;
    case AREAURP_RERR:
        os << "RERR";
        break;
    case AREAURP_RREP_ACK:
        os << "RREP_ACK";
        break;
    case AREAURP_NID:
        os << "PT_NID";
        break;
    case AREAURP_GID:
        os << "PT_GID";
        break;
    case AREAURP_CREV:
        os << "PT_CREV";
        break;
    default:
        os << "UNKNOWN";
    }
}

bool
TypeHeader::operator==(const TypeHeader& o) const
{
    return (m_type == o.m_type && m_valid == o.m_valid);
}

std::ostream&
operator<<(std::ostream& os, const TypeHeader& h)
{
    h.Print(os);
    return os;
}

// ---------------------------------------------------------------- RreqHeader

NS_OBJECT_ENSURE_REGISTERED(RreqHeader);

RreqHeader::RreqHeader(uint8_t flags,
                       uint8_t hopCount,
                       uint32_t requestID,
                       Ipv4Address dst,
                       uint32_t dstSeqNo,
                       Ipv4Address origin,
                       uint32_t originSeqNo,
                       uint32_t pathCost)
    : m_flags(flags),
      m_hopCount(hopCount),
      m_requestID(requestID),
      m_dst(dst),
      m_dstSeqNo(dstSeqNo),
      m_origin(origin),
      m_originSeqNo(originSeqNo),
      m_pathCost(pathCost),
      m_ttl(10)
{
}

TypeId
RreqHeader::GetTypeId()
{
    static TypeId tid = TypeId("ns3::arEaurp::RreqHeader")
                            .SetParent<Header>()
                            .SetGroupName("ArEaurp")
                            .AddConstructor<RreqHeader>();
    return tid;
}

TypeId
RreqHeader::GetInstanceTypeId() const
{
    return GetTypeId();
}

uint32_t
RreqHeader::GetSerializedSize() const
{
    return 27;
}

void
RreqHeader::Serialize(Buffer::Iterator i) const
{
    i.WriteU8(m_flags);
    i.WriteU8(m_hopCount);
    i.WriteHtonU32(m_requestID);
    WriteTo(i, m_dst);
    i.WriteHtonU32(m_dstSeqNo);
    WriteTo(i, m_origin);
    i.WriteHtonU32(m_originSeqNo);
    i.WriteHtonU32(m_pathCost);
    i.WriteU8(m_ttl);
}

uint32_t
RreqHeader::Deserialize(Buffer::Iterator start)
{
    Buffer::Iterator i = start;
    m_flags = i.ReadU8();
    m_hopCount = i.ReadU8();
    m_requestID = i.ReadNtohU32();
    ReadFrom(i, m_dst);
    m_dstSeqNo = i.ReadNtohU32();
    ReadFrom(i, m_origin);
    m_originSeqNo = i.ReadNtohU32();
    m_pathCost = i.ReadNtohU32();
    m_ttl = i.ReadU8();
    return i.GetDistanceFrom(start);
}

void
RreqHeader::Print(std::ostream& os) const
{
    os << "RREQ id " << m_requestID << " dst " << m_dst << " src " << m_origin << " hops "
       << (uint32_t)m_hopCount << " cost " << m_pathCost;
}

void
RreqHeader::SetPolicy(uint8_t p)
{
    m_flags = (m_flags & ~0x03) | (p & 0x03);
}

uint8_t
RreqHeader::GetPolicy() const
{
    return m_flags & 0x03;
}

void
RreqHeader::SetUnknownSeqno(bool f)
{
    m_flags = f ? (m_flags | (1 << 3)) : (m_flags & ~(1 << 3));
}

bool
RreqHeader::GetUnknownSeqno() const
{
    return (m_flags & (1 << 3));
}

void
RreqHeader::SetDestinationOnly(bool f)
{
    m_flags = f ? (m_flags | (1 << 4)) : (m_flags & ~(1 << 4));
}

bool
RreqHeader::GetDestinationOnly() const
{
    return (m_flags & (1 << 4));
}

void
RreqHeader::SetGratuitousRrep(bool f)
{
    m_flags = f ? (m_flags | (1 << 5)) : (m_flags & ~(1 << 5));
}

bool
RreqHeader::GetGratuitousRrep() const
{
    return (m_flags & (1 << 5));
}

bool
RreqHeader::operator==(const RreqHeader& o) const
{
    return (m_flags == o.m_flags && m_hopCount == o.m_hopCount && m_requestID == o.m_requestID &&
            m_dst == o.m_dst && m_dstSeqNo == o.m_dstSeqNo && m_origin == o.m_origin &&
            m_originSeqNo == o.m_originSeqNo && m_pathCost == o.m_pathCost &&
            m_ttl == o.m_ttl);
}

std::ostream&
operator<<(std::ostream& os, const RreqHeader& h)
{
    h.Print(os);
    return os;
}

// ---------------------------------------------------------------- RrepHeader

NS_OBJECT_ENSURE_REGISTERED(RrepHeader);

RrepHeader::RrepHeader(uint8_t prefixSize,
                       uint8_t hopCount,
                       Ipv4Address dst,
                       uint32_t dstSeqNo,
                       Ipv4Address origin,
                       Time lifetime,
                       uint32_t pathCost)
    : m_flags(0),
      m_prefixSize(prefixSize),
      m_hopCount(hopCount),
      m_dst(dst),
      m_dstSeqNo(dstSeqNo),
      m_origin(origin),
      m_pathCost(pathCost)
{
    m_lifeTime = (uint32_t)lifetime.GetMilliSeconds();
}

TypeId
RrepHeader::GetTypeId()
{
    static TypeId tid = TypeId("ns3::arEaurp::RrepHeader")
                            .SetParent<Header>()
                            .SetGroupName("ArEaurp")
                            .AddConstructor<RrepHeader>();
    return tid;
}

TypeId
RrepHeader::GetInstanceTypeId() const
{
    return GetTypeId();
}

uint32_t
RrepHeader::GetSerializedSize() const
{
    return 23;
}

void
RrepHeader::Serialize(Buffer::Iterator i) const
{
    i.WriteU8(m_flags);
    i.WriteU8(m_prefixSize);
    i.WriteU8(m_hopCount);
    WriteTo(i, m_dst);
    i.WriteHtonU32(m_dstSeqNo);
    WriteTo(i, m_origin);
    i.WriteHtonU32(m_lifeTime);
    i.WriteHtonU32(m_pathCost);
}

uint32_t
RrepHeader::Deserialize(Buffer::Iterator start)
{
    Buffer::Iterator i = start;
    m_flags = i.ReadU8();
    m_prefixSize = i.ReadU8();
    m_hopCount = i.ReadU8();
    ReadFrom(i, m_dst);
    m_dstSeqNo = i.ReadNtohU32();
    ReadFrom(i, m_origin);
    m_lifeTime = i.ReadNtohU32();
    m_pathCost = i.ReadNtohU32();
    return i.GetDistanceFrom(start);
}

void
RrepHeader::Print(std::ostream& os) const
{
    os << "RREP dst " << m_dst << " src " << m_origin << " hops " << (uint32_t)m_hopCount
       << " cost " << m_pathCost << " lifetime " << m_lifeTime << "ms";
}

void
RrepHeader::SetLifeTime(Time t)
{
    m_lifeTime = (uint32_t)t.GetMilliSeconds();
}

Time
RrepHeader::GetLifeTime() const
{
    return MilliSeconds(m_lifeTime);
}

void
RrepHeader::SetPolicy(uint8_t p)
{
    m_flags = (m_flags & ~0x03) | (p & 0x03);
}

uint8_t
RrepHeader::GetPolicy() const
{
    return m_flags & 0x03;
}

void
RrepHeader::SetAckRequired(bool f)
{
    m_flags = f ? (m_flags | (1 << 6)) : (m_flags & ~(1 << 6));
}

bool
RrepHeader::GetAckRequired() const
{
    return (m_flags & (1 << 6));
}

void
RrepHeader::SetPrefixSize(uint8_t sz)
{
    m_prefixSize = sz;
}

uint8_t
RrepHeader::GetPrefixSize() const
{
    return m_prefixSize;
}

void
RrepHeader::SetHello(Ipv4Address src, uint32_t srcSeqNo, Time lifetime)
{
    m_flags = 0;
    m_prefixSize = 0;
    m_hopCount = 0;
    m_dst = src;
    m_dstSeqNo = srcSeqNo;
    m_origin = src;
    m_lifeTime = (uint32_t)lifetime.GetMilliSeconds();
    m_pathCost = 0;
}

bool
RrepHeader::operator==(const RrepHeader& o) const
{
    return (m_flags == o.m_flags && m_prefixSize == o.m_prefixSize && m_hopCount == o.m_hopCount &&
            m_dst == o.m_dst && m_dstSeqNo == o.m_dstSeqNo && m_origin == o.m_origin &&
            m_lifeTime == o.m_lifeTime && m_pathCost == o.m_pathCost);
}

std::ostream&
operator<<(std::ostream& os, const RrepHeader& h)
{
    h.Print(os);
    return os;
}

// ---------------------------------------------------------------- RerrHeader

NS_OBJECT_ENSURE_REGISTERED(RerrHeader);

RerrHeader::RerrHeader()
    : m_flag(0),
      m_reserved(0)
{
}

TypeId
RerrHeader::GetTypeId()
{
    static TypeId tid = TypeId("ns3::arEaurp::RerrHeader")
                            .SetParent<Header>()
                            .SetGroupName("ArEaurp")
                            .AddConstructor<RerrHeader>();
    return tid;
}

TypeId
RerrHeader::GetInstanceTypeId() const
{
    return GetTypeId();
}

uint32_t
RerrHeader::GetSerializedSize() const
{
    return (3 + 8 * GetDestCount());
}

void
RerrHeader::Serialize(Buffer::Iterator i) const
{
    i.WriteU8(m_flag);
    i.WriteU8(m_reserved);
    i.WriteU8(GetDestCount());
    for (auto j = m_unreachableDstSeqNo.begin(); j != m_unreachableDstSeqNo.end(); ++j)
    {
        WriteTo(i, j->first);
        i.WriteHtonU32(j->second);
    }
}

uint32_t
RerrHeader::Deserialize(Buffer::Iterator start)
{
    Buffer::Iterator i = start;
    m_flag = i.ReadU8();
    m_reserved = i.ReadU8();
    uint8_t dest = i.ReadU8();
    m_unreachableDstSeqNo.clear();
    for (uint8_t k = 0; k < dest; ++k)
    {
        Ipv4Address address;
        ReadFrom(i, address);
        uint32_t seqNo = i.ReadNtohU32();
        m_unreachableDstSeqNo.insert(std::make_pair(address, seqNo));
    }
    return i.GetDistanceFrom(start);
}

void
RerrHeader::Print(std::ostream& os) const
{
    os << "RERR unreachable:";
    for (auto j = m_unreachableDstSeqNo.begin(); j != m_unreachableDstSeqNo.end(); ++j)
    {
        os << " " << j->first;
    }
}

void
RerrHeader::SetNoDelete(bool f)
{
    m_flag = f ? (m_flag | (1 << 0)) : (m_flag & ~(1 << 0));
}

bool
RerrHeader::GetNoDelete() const
{
    return (m_flag & (1 << 0));
}

bool
RerrHeader::AddUnDestination(Ipv4Address dst, uint32_t seqNo)
{
    if (m_unreachableDstSeqNo.find(dst) != m_unreachableDstSeqNo.end())
    {
        return true;
    }
    if (GetDestCount() >= 25)
    {
        return false; // one RERR must still fit comfortably in one frame
    }
    m_unreachableDstSeqNo.insert(std::make_pair(dst, seqNo));
    return true;
}

bool
RerrHeader::RemoveUnDestination(std::pair<Ipv4Address, uint32_t>& un)
{
    if (m_unreachableDstSeqNo.empty())
    {
        return false;
    }
    auto i = m_unreachableDstSeqNo.begin();
    un = *i;
    m_unreachableDstSeqNo.erase(i);
    return true;
}

void
RerrHeader::Clear()
{
    m_unreachableDstSeqNo.clear();
    m_flag = 0;
    m_reserved = 0;
}

bool
RerrHeader::operator==(const RerrHeader& o) const
{
    return (m_flag == o.m_flag && m_reserved == o.m_reserved &&
            m_unreachableDstSeqNo == o.m_unreachableDstSeqNo);
}

std::ostream&
operator<<(std::ostream& os, const RerrHeader& h)
{
    h.Print(os);
    return os;
}

// ----------------------------------------------------------------- NidHeader

NS_OBJECT_ENSURE_REGISTERED(NidHeader);

NidHeader::NidHeader()
    : m_origin(Ipv4Address()),
      m_energy(255),
      m_surplus(0)
{
}

TypeId
NidHeader::GetTypeId()
{
    static TypeId tid = TypeId("ns3::arEaurp::NidHeader")
                            .SetParent<Header>()
                            .SetGroupName("ArEaurp")
                            .AddConstructor<NidHeader>();
    return tid;
}

TypeId
NidHeader::GetInstanceTypeId() const
{
    return GetTypeId();
}

uint32_t
NidHeader::GetSerializedSize() const
{
    return 8 + 5 * (uint32_t)m_ratios.size() + 4 * (uint32_t)m_links.size();
}

void
NidHeader::Serialize(Buffer::Iterator i) const
{
    WriteTo(i, m_origin);
    i.WriteU8(m_energy);
    i.WriteU8(m_surplus);
    i.WriteU8((uint8_t)m_ratios.size());
    for (const auto& r : m_ratios)
    {
        WriteTo(i, r.first);
        i.WriteU8(Quantise(r.second));
    }
    i.WriteU8((uint8_t)m_links.size());
    for (const auto& l : m_links)
    {
        WriteTo(i, l);
    }
}

uint32_t
NidHeader::Deserialize(Buffer::Iterator start)
{
    Buffer::Iterator i = start;
    ReadFrom(i, m_origin);
    m_energy = i.ReadU8();
    m_surplus = i.ReadU8();
    uint8_t count = i.ReadU8();
    m_ratios.clear();
    for (uint8_t k = 0; k < count; ++k)
    {
        Ipv4Address a;
        ReadFrom(i, a);
        uint8_t pfr = i.ReadU8();
        m_ratios.emplace_back(a, Dequantise(pfr));
    }
    uint8_t links = i.ReadU8();
    m_links.clear();
    for (uint8_t k = 0; k < links; ++k)
    {
        Ipv4Address a;
        ReadFrom(i, a);
        m_links.push_back(a);
    }
    return i.GetDistanceFrom(start);
}

void
NidHeader::Print(std::ostream& os) const
{
    os << "PT_NID from " << m_origin << " energy " << Dequantise(m_energy) << " surplus "
       << Dequantise(m_surplus) << " reports " << m_ratios.size();
}

void
NidHeader::SetEnergyFraction(double f)
{
    m_energy = Quantise(f);
}

double
NidHeader::GetEnergyFraction() const
{
    return Dequantise(m_energy);
}

void
NidHeader::SetSurplus(double f)
{
    m_surplus = Quantise(f);
}

double
NidHeader::GetSurplus() const
{
    return Dequantise(m_surplus);
}

void
NidHeader::AddRatio(Ipv4Address neighbour, double pfr)
{
    if (m_ratios.size() >= 40)
    {
        return; // keep PT_NID inside a single frame
    }
    m_ratios.emplace_back(neighbour, pfr);
}

void
NidHeader::AddLink(Ipv4Address neighbour)
{
    if (m_links.size() >= 40)
    {
        return;
    }
    m_links.push_back(neighbour);
}

std::ostream&
operator<<(std::ostream& os, const NidHeader& h)
{
    h.Print(os);
    return os;
}

// ----------------------------------------------------------------- GidHeader

NS_OBJECT_ENSURE_REGISTERED(GidHeader);

GidHeader::GidHeader()
    : m_origin(Ipv4Address()),
      m_seq(0),
      m_ttl(2)
{
}

TypeId
GidHeader::GetTypeId()
{
    static TypeId tid = TypeId("ns3::arEaurp::GidHeader")
                            .SetParent<Header>()
                            .SetGroupName("ArEaurp")
                            .AddConstructor<GidHeader>();
    return tid;
}

TypeId
GidHeader::GetInstanceTypeId() const
{
    return GetTypeId();
}

uint32_t
GidHeader::GetSerializedSize() const
{
    return 10 + 5 * (uint32_t)m_opinions.size();
}

void
GidHeader::Serialize(Buffer::Iterator i) const
{
    WriteTo(i, m_origin);
    i.WriteHtonU32(m_seq);
    i.WriteU8(m_ttl);
    i.WriteU8((uint8_t)m_opinions.size());
    for (const auto& o : m_opinions)
    {
        WriteTo(i, o.first);
        i.WriteU8(Quantise(o.second));
    }
}

uint32_t
GidHeader::Deserialize(Buffer::Iterator start)
{
    Buffer::Iterator i = start;
    ReadFrom(i, m_origin);
    m_seq = i.ReadNtohU32();
    m_ttl = i.ReadU8();
    uint8_t count = i.ReadU8();
    m_opinions.clear();
    for (uint8_t k = 0; k < count; ++k)
    {
        Ipv4Address a;
        ReadFrom(i, a);
        uint8_t t = i.ReadU8();
        m_opinions.emplace_back(a, Dequantise(t));
    }
    return i.GetDistanceFrom(start);
}

void
GidHeader::Print(std::ostream& os) const
{
    os << "PT_GID from " << m_origin << " seq " << m_seq << " ttl " << (uint32_t)m_ttl
       << " opinions " << m_opinions.size();
}

void
GidHeader::AddOpinion(Ipv4Address subject, double trust)
{
    if (m_opinions.size() >= 40)
    {
        return;
    }
    m_opinions.emplace_back(subject, trust);
}

std::ostream&
operator<<(std::ostream& os, const GidHeader& h)
{
    h.Print(os);
    return os;
}

// ---------------------------------------------------------------- CrevHeader

NS_OBJECT_ENSURE_REGISTERED(CrevHeader);

CrevHeader::CrevHeader()
    : m_origin(Ipv4Address()),
      m_revoked(Ipv4Address()),
      m_seq(0),
      m_ttl(16),
      m_evidence(0)
{
}

TypeId
CrevHeader::GetTypeId()
{
    static TypeId tid = TypeId("ns3::arEaurp::CrevHeader")
                            .SetParent<Header>()
                            .SetGroupName("ArEaurp")
                            .AddConstructor<CrevHeader>();
    return tid;
}

TypeId
CrevHeader::GetInstanceTypeId() const
{
    return GetTypeId();
}

uint32_t
CrevHeader::GetSerializedSize() const
{
    return 14;
}

void
CrevHeader::Serialize(Buffer::Iterator i) const
{
    WriteTo(i, m_origin);
    WriteTo(i, m_revoked);
    i.WriteHtonU32(m_seq);
    i.WriteU8(m_ttl);
    i.WriteU8(m_evidence);
}

uint32_t
CrevHeader::Deserialize(Buffer::Iterator start)
{
    Buffer::Iterator i = start;
    ReadFrom(i, m_origin);
    ReadFrom(i, m_revoked);
    m_seq = i.ReadNtohU32();
    m_ttl = i.ReadU8();
    m_evidence = i.ReadU8();
    return i.GetDistanceFrom(start);
}

void
CrevHeader::Print(std::ostream& os) const
{
    os << "PT_CREV from " << m_origin << " revokes " << m_revoked << " evidence "
       << (uint32_t)m_evidence << " ttl " << (uint32_t)m_ttl;
}

std::ostream&
operator<<(std::ostream& os, const CrevHeader& h)
{
    h.Print(os);
    return os;
}

} // namespace arEaurp
} // namespace ns3
