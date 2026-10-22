/*
 * Variable-size CBR traffic with end-to-end acknowledgement.
 *
 * Two reasons this is not just OnOffApplication:
 *
 * 1. PACKET SIZES VARY. The papers draw payloads uniformly from 512 to 1024
 *    bytes, and the whole selective-forwarding attack is defined on that
 *    spread -- a gray-hole that drops only the large packets is invisible to a
 *    protocol watching a single forwarding ratio. A fixed-size generator would
 *    make the attack impossible to express.
 *
 * 2. THE SOURCE HAS TO LEARN WHETHER DELIVERY HAPPENED. The CMDP agent is
 *    rewarded on delivery, so something has to tell the source. UDP alone does
 *    not, so the destination returns a small acknowledgement -- as an
 *    application using confirmable messaging would. The ack carries the hop
 *    count the packet actually travelled, taken from the IP TTL, which is also
 *    what the energy term in the reward is computed from.
 *
 * Acks are enabled for every protocol variant, so the traffic each variant
 * sees is identical and the comparison stays fair.
 */

#ifndef AR_TRAFFIC_APP_H
#define AR_TRAFFIC_APP_H
#include "ar-eaurp-crypto.h"

#include "ns3/application.h"
#include "ns3/event-id.h"
#include "ns3/header.h"
#include "ns3/ipv4-address.h"
#include "ns3/random-variable-stream.h"
#include "ns3/socket.h"

#include <map>
#include <memory>

namespace ns3
{
namespace arEaurp
{

/// Eighteen bytes of application header: sequence, send time, kind, hops.
class ArTrafficHeader : public Header
{
  public:
    ArTrafficHeader();

    static TypeId GetTypeId();
    TypeId GetInstanceTypeId() const override;
    uint32_t GetSerializedSize() const override;
    void Serialize(Buffer::Iterator start) const override;
    uint32_t Deserialize(Buffer::Iterator start) override;
    void Print(std::ostream& os) const override;

    void SetSeq(uint64_t s)
    {
        m_seq = s;
    }

    uint64_t GetSeq() const
    {
        return m_seq;
    }

    void SetSendTime(Time t)
    {
        m_sendTimeNs = (uint64_t)t.GetNanoSeconds();
    }

    Time GetSendTime() const
    {
        return NanoSeconds(m_sendTimeNs);
    }

    void SetAck(bool a)
    {
        m_kind = a ? 1 : 0;
    }

    bool IsAck() const
    {
        return m_kind == 1;
    }

    void SetHops(uint8_t h)
    {
        m_hops = h;
    }

    uint8_t GetHops() const
    {
        return m_hops;
    }

  private:
    uint64_t m_seq;
    uint64_t m_sendTimeNs;
    uint8_t m_kind;
    uint8_t m_hops;
};

class ArTrafficApp : public Application
{
  public:
    static TypeId GetTypeId();
    ArTrafficApp();
    ~ArTrafficApp() override;

    int64_t AssignStreams(int64_t stream) override;
    void SetCipher(const CryptoBox::Key& key, uint32_t prefix)
    { m_cipher = std::make_unique<CryptoBox>(key, prefix); }
    void StopSending() { m_sendEvent.Cancel(); }

    uint64_t Sent() const
    {
        return m_sent;
    }

    uint64_t Received() const
    {
        return m_received;
    }

  private:
    void StartApplication() override;
    void StopApplication() override;

    void Send();
    void HandleRead(Ptr<Socket> socket);
    void AckTimeout(uint64_t seq);
    void ReportDelivery(bool delivered, uint32_t hops, uint64_t sequence, Time sent);
    void RecordDecision(uint64_t sequence);
    Ptr<Packet> Protect(Ptr<Packet> packet, uint64_t sequence);

    Ptr<Socket> m_socket;
    std::unique_ptr<CryptoBox> m_cipher;
    Ipv4Address m_remote;
    uint16_t m_port;
    Time m_interval;
    uint32_t m_minSize;
    uint32_t m_maxSize;
    Time m_ackTimeout;
    bool m_enableAck;
    Time m_startJitter;

    EventId m_sendEvent;
    std::map<uint64_t, EventId> m_ackTimers;
    std::map<uint64_t, uint64_t> m_decisionIds;
    uint64_t m_seq;
    uint64_t m_sent;
    uint64_t m_received;

    Ptr<UniformRandomVariable> m_sizeRng;
    Ptr<UniformRandomVariable> m_jitterRng;
};

} // namespace arEaurp
} // namespace ns3

#endif /* AR_TRAFFIC_APP_H */
