/*
 * AR-EAURP control packet formats.
 *
 * Route discovery uses the AODV control set (RREQ/RREP/RERR) extended with an
 * accumulated route cost, so that base.pdf's R_Score = a*T + b*E can be carried
 * hop by hop instead of being computed by an omniscient observer.
 *
 * The three trust-plane packets are the ones base.pdf 3.6 specifies verbatim:
 *
 *   PT_NID  0x81  Node Identification  -- who I am, how much battery I have,
 *                                        and the forwarding ratio I measured
 *                                        for each of my neighbours
 *   PT_GID  0x82  Group Identification -- the trust values I publish about the
 *                                        nodes I watch (the consensus input)
 *   PT_CREV 0x83  Controlled Revocation - node X has been voted malicious
 *
 * Every field is serialised in network byte order and every header reports a
 * real wire size, so the control overhead measured by the simulation is the
 * overhead this protocol would actually put on the air.
 */

#ifndef AR_EAURP_PACKET_H
#define AR_EAURP_PACKET_H

#include "ns3/header.h"
#include "ns3/ipv4-address.h"
#include "ns3/nstime.h"

#include <iostream>
#include <map>
#include <vector>

namespace ns3
{
namespace arEaurp
{

/// Message type codes. The 0x8x block is taken from base.pdf 3.6.
enum MessageType
{
    AREAURP_RREQ = 1,     //!< Route Request
    AREAURP_RREP = 2,     //!< Route Reply
    AREAURP_RERR = 3,     //!< Route Error
    AREAURP_RREP_ACK = 4, //!< Route Reply Acknowledgment
    AREAURP_NID = 0x81,   //!< PT_NID  -- node identification / trust report
    AREAURP_GID = 0x82,   //!< PT_GID  -- group identification / consensus vote
    AREAURP_CREV = 0x83,  //!< PT_CREV -- controlled revocation
};

/**
 * \brief One byte on the wire telling the receiver which header follows.
 */
class TypeHeader : public Header
{
  public:
    TypeHeader(MessageType t = AREAURP_RREQ);

    static TypeId GetTypeId();
    TypeId GetInstanceTypeId() const override;
    uint32_t GetSerializedSize() const override;
    void Serialize(Buffer::Iterator start) const override;
    uint32_t Deserialize(Buffer::Iterator start) override;
    void Print(std::ostream& os) const override;

    MessageType Get() const
    {
        return m_type;
    }

    bool IsValid() const
    {
        return m_valid;
    }

    bool operator==(const TypeHeader& o) const;

  private:
    MessageType m_type;
    bool m_valid;
};

std::ostream& operator<<(std::ostream& os, const TypeHeader& h);

/**
 * \brief Route Request carrying the accumulated EAURP route cost.
 *
 * m_pathCost is the sum over the hops already traversed of
 * (1 - R_Score(prev hop)) + hopPenalty, in milli-units. Each forwarder adds the
 * cost of the neighbour it heard the RREQ from, using its own locally measured
 * trust for that neighbour and the energy the neighbour advertised in PT_NID.
 * A node therefore never scores itself, which is what stops a malicious node
 * from simply declaring itself trustworthy.
 */
class RreqHeader : public Header
{
  public:
    RreqHeader(uint8_t flags = 0,
               uint8_t hopCount = 0,
               uint32_t requestID = 0,
               Ipv4Address dst = Ipv4Address(),
               uint32_t dstSeqNo = 0,
               Ipv4Address origin = Ipv4Address(),
               uint32_t originSeqNo = 0,
               uint32_t pathCost = 0);

    static TypeId GetTypeId();
    TypeId GetInstanceTypeId() const override;
    uint32_t GetSerializedSize() const override;
    void Serialize(Buffer::Iterator start) const override;
    uint32_t Deserialize(Buffer::Iterator start) override;
    void Print(std::ostream& os) const override;

    void SetHopCount(uint8_t count)
    {
        m_hopCount = count;
    }

    uint8_t GetHopCount() const
    {
        return m_hopCount;
    }

    void SetId(uint32_t id)
    {
        m_requestID = id;
    }

    uint32_t GetId() const
    {
        return m_requestID;
    }

    void SetDst(Ipv4Address a)
    {
        m_dst = a;
    }

    Ipv4Address GetDst() const
    {
        return m_dst;
    }

    void SetDstSeqno(uint32_t s)
    {
        m_dstSeqNo = s;
    }

    uint32_t GetDstSeqno() const
    {
        return m_dstSeqNo;
    }

    void SetOrigin(Ipv4Address a)
    {
        m_origin = a;
    }

    Ipv4Address GetOrigin() const
    {
        return m_origin;
    }

    void SetOriginSeqno(uint32_t s)
    {
        m_originSeqNo = s;
    }

    uint32_t GetOriginSeqno() const
    {
        return m_originSeqNo;
    }

    void SetPathCost(uint32_t c)
    {
        m_pathCost = c;
    }

    uint32_t GetPathCost() const
    {
        return m_pathCost;
    }

    /// Hop budget for this attempt -- the ring of the expanding ring search.
    void SetTtl(uint8_t t)
    {
        m_ttl = t;
    }

    uint8_t GetTtl() const
    {
        return m_ttl;
    }

    /**
     * \brief Which scoring policy the originator asked the network to use.
     *
     * Carried in the low two bits of the flags byte so that every forwarder
     * scores the path the same way the originator's agent intended; otherwise
     * each hop would weigh trust against energy differently and the
     * accumulated cost would mean nothing.
     */
    void SetPolicy(uint8_t p);
    uint8_t GetPolicy() const;

    void SetUnknownSeqno(bool f);
    bool GetUnknownSeqno() const;
    void SetDestinationOnly(bool f);
    bool GetDestinationOnly() const;
    void SetGratuitousRrep(bool f);
    bool GetGratuitousRrep() const;

    bool operator==(const RreqHeader& o) const;

  private:
    uint8_t m_flags;
    uint8_t m_hopCount;
    uint32_t m_requestID;
    Ipv4Address m_dst;
    uint32_t m_dstSeqNo;
    Ipv4Address m_origin;
    uint32_t m_originSeqNo;
    uint32_t m_pathCost; //!< accumulated EAURP cost, milli-units
    uint8_t m_ttl;       //!< hop budget for this ring of the search
};

std::ostream& operator<<(std::ostream& os, const RreqHeader& h);

/**
 * \brief Route Reply. Carries the cost of the path it has travelled so far,
 * so the originator can compare competing replies on route quality rather
 * than on arrival order alone.
 */
class RrepHeader : public Header
{
  public:
    RrepHeader(uint8_t prefixSize = 0,
               uint8_t hopCount = 0,
               Ipv4Address dst = Ipv4Address(),
               uint32_t dstSeqNo = 0,
               Ipv4Address origin = Ipv4Address(),
               Time lifetime = MilliSeconds(0),
               uint32_t pathCost = 0);

    static TypeId GetTypeId();
    TypeId GetInstanceTypeId() const override;
    uint32_t GetSerializedSize() const override;
    void Serialize(Buffer::Iterator start) const override;
    uint32_t Deserialize(Buffer::Iterator start) override;
    void Print(std::ostream& os) const override;

    void SetHopCount(uint8_t count)
    {
        m_hopCount = count;
    }

    uint8_t GetHopCount() const
    {
        return m_hopCount;
    }

    void SetDst(Ipv4Address a)
    {
        m_dst = a;
    }

    Ipv4Address GetDst() const
    {
        return m_dst;
    }

    void SetDstSeqno(uint32_t s)
    {
        m_dstSeqNo = s;
    }

    uint32_t GetDstSeqno() const
    {
        return m_dstSeqNo;
    }

    void SetOrigin(Ipv4Address a)
    {
        m_origin = a;
    }

    Ipv4Address GetOrigin() const
    {
        return m_origin;
    }

    void SetLifeTime(Time t);
    Time GetLifeTime() const;

    void SetPathCost(uint32_t c)
    {
        m_pathCost = c;
    }

    uint32_t GetPathCost() const
    {
        return m_pathCost;
    }

    /// The scoring policy this reply is being accumulated under.
    void SetPolicy(uint8_t p);
    uint8_t GetPolicy() const;

    void SetAckRequired(bool f);
    bool GetAckRequired() const;
    void SetPrefixSize(uint8_t sz);
    uint8_t GetPrefixSize() const;

    /// Build the reply a destination sends for a request it just received.
    void SetHello(Ipv4Address src, uint32_t srcSeqNo, Time lifetime);

    bool operator==(const RrepHeader& o) const;

  private:
    uint8_t m_flags;
    uint8_t m_prefixSize;
    uint8_t m_hopCount;
    Ipv4Address m_dst;
    uint32_t m_dstSeqNo;
    Ipv4Address m_origin;
    uint32_t m_lifeTime; //!< milliseconds
    uint32_t m_pathCost; //!< accumulated EAURP cost, milli-units
};

std::ostream& operator<<(std::ostream& os, const RrepHeader& h);

/**
 * \brief Route Error: the listed destinations are no longer reachable through
 * the sender. base.pdf 3.8 requires one of these whenever a revocation breaks
 * an active route.
 */
class RerrHeader : public Header
{
  public:
    RerrHeader();

    static TypeId GetTypeId();
    TypeId GetInstanceTypeId() const override;
    uint32_t GetSerializedSize() const override;
    void Serialize(Buffer::Iterator start) const override;
    uint32_t Deserialize(Buffer::Iterator start) override;
    void Print(std::ostream& os) const override;

    void SetNoDelete(bool f);
    bool GetNoDelete() const;

    bool AddUnDestination(Ipv4Address dst, uint32_t seqNo);
    bool RemoveUnDestination(std::pair<Ipv4Address, uint32_t>& un);
    void Clear();

    uint8_t GetDestCount() const
    {
        return (uint8_t)m_unreachableDstSeqNo.size();
    }

    bool operator==(const RerrHeader& o) const;

  private:
    uint8_t m_flag;
    uint8_t m_reserved;
    std::map<Ipv4Address, uint32_t> m_unreachableDstSeqNo;
};

std::ostream& operator<<(std::ostream& os, const RerrHeader& h);

/**
 * \brief PT_NID (0x81) -- base.pdf 3.6.
 *
 * Doubles as the neighbour beacon and as the watchdog report: the sender
 * publishes its residual energy, its forecast harvest surplus, and the packet
 * forwarding ratio it has measured for each neighbour it has watched.
 */
class NidHeader : public Header
{
  public:
    NidHeader();

    static TypeId GetTypeId();
    TypeId GetInstanceTypeId() const override;
    uint32_t GetSerializedSize() const override;
    void Serialize(Buffer::Iterator start) const override;
    uint32_t Deserialize(Buffer::Iterator start) override;
    void Print(std::ostream& os) const override;

    void SetOrigin(Ipv4Address a)
    {
        m_origin = a;
    }

    Ipv4Address GetOrigin() const
    {
        return m_origin;
    }

    /// Residual energy as a fraction of the node's initial energy.
    void SetEnergyFraction(double f);
    double GetEnergyFraction() const;

    /// Forecast harvest surplus over the next horizon, normalised to [0, 1].
    void SetSurplus(double f);
    double GetSurplus() const;

    void AddRatio(Ipv4Address neighbour, double pfr);

    const std::vector<std::pair<Ipv4Address, double>>& GetRatios() const
    {
        return m_ratios;
    }

    /**
     * \brief Neighbours whose beacons the sender is currently hearing.
     *
     * A node that finds itself in this list knows the link is bidirectional.
     * Without that check a route can be built over a link that carries the
     * sender's broadcasts but not the receiver's replies, and every data packet
     * sent along it dies at the MAC after exhausting its retries.
     */
    void AddLink(Ipv4Address neighbour);

    const std::vector<Ipv4Address>& GetLinks() const
    {
        return m_links;
    }

  private:
    Ipv4Address m_origin;
    uint8_t m_energy;
    uint8_t m_surplus;
    std::vector<std::pair<Ipv4Address, double>> m_ratios;
    std::vector<Ipv4Address> m_links;
};

std::ostream& operator<<(std::ostream& os, const NidHeader& h);

/**
 * \brief PT_GID (0x82) -- base.pdf 3.6/3.7.
 *
 * The trust values a node publishes about the nodes it watches. An honest node
 * publishes what its watchdog measured; a slanderer publishes whatever serves
 * its colluders, which is precisely the input the majority vote consumes.
 * Scoped flood (TTL) so the vote reaches the accused node's whole neighbourhood,
 * not just the accuser's own one-hop range.
 */
class GidHeader : public Header
{
  public:
    GidHeader();

    static TypeId GetTypeId();
    TypeId GetInstanceTypeId() const override;
    uint32_t GetSerializedSize() const override;
    void Serialize(Buffer::Iterator start) const override;
    uint32_t Deserialize(Buffer::Iterator start) override;
    void Print(std::ostream& os) const override;

    void SetOrigin(Ipv4Address a)
    {
        m_origin = a;
    }

    Ipv4Address GetOrigin() const
    {
        return m_origin;
    }

    void SetSeq(uint32_t s)
    {
        m_seq = s;
    }

    uint32_t GetSeq() const
    {
        return m_seq;
    }

    void SetTtl(uint8_t t)
    {
        m_ttl = t;
    }

    uint8_t GetTtl() const
    {
        return m_ttl;
    }

    void AddOpinion(Ipv4Address subject, double trust);

    const std::vector<std::pair<Ipv4Address, double>>& GetOpinions() const
    {
        return m_opinions;
    }

  private:
    Ipv4Address m_origin;
    uint32_t m_seq;
    uint8_t m_ttl;
    std::vector<std::pair<Ipv4Address, double>> m_opinions;
};

std::ostream& operator<<(std::ostream& os, const GidHeader& h);

/**
 * \brief PT_CREV (0x83) -- base.pdf 3.6/3.8: node X is revoked, network wide.
 */
class CrevHeader : public Header
{
  public:
    CrevHeader();

    static TypeId GetTypeId();
    TypeId GetInstanceTypeId() const override;
    uint32_t GetSerializedSize() const override;
    void Serialize(Buffer::Iterator start) const override;
    uint32_t Deserialize(Buffer::Iterator start) override;
    void Print(std::ostream& os) const override;

    void SetOrigin(Ipv4Address a)
    {
        m_origin = a;
    }

    Ipv4Address GetOrigin() const
    {
        return m_origin;
    }

    void SetRevoked(Ipv4Address a)
    {
        m_revoked = a;
    }

    Ipv4Address GetRevoked() const
    {
        return m_revoked;
    }

    void SetSeq(uint32_t s)
    {
        m_seq = s;
    }

    uint32_t GetSeq() const
    {
        return m_seq;
    }

    void SetTtl(uint8_t t)
    {
        m_ttl = t;
    }

    uint8_t GetTtl() const
    {
        return m_ttl;
    }

    void SetEvidence(uint8_t e)
    {
        m_evidence = e;
    }

    uint8_t GetEvidence() const
    {
        return m_evidence;
    }

  private:
    Ipv4Address m_origin;
    Ipv4Address m_revoked;
    uint32_t m_seq;
    uint8_t m_ttl;
    uint8_t m_evidence;
};

std::ostream& operator<<(std::ostream& os, const CrevHeader& h);

} // namespace arEaurp
} // namespace ns3

#endif /* AR_EAURP_PACKET_H */
