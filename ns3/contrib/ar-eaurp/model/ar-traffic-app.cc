#include "ar-traffic-app.h"

#include "ar-eaurp-oracle.h"
#include "ar-eaurp-routing-protocol.h"

#include "ns3/boolean.h"
#include "ns3/inet-socket-address.h"
#include "ns3/ipv4.h"
#include "ns3/log.h"
#include "ns3/node.h"
#include "ns3/packet.h"
#include "ns3/simulator.h"
#include "ns3/socket-factory.h"
#include "ns3/socket.h"
#include "ns3/udp-socket-factory.h"
#include "ns3/uinteger.h"

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("ArTrafficApp");

namespace arEaurp
{

NS_OBJECT_ENSURE_REGISTERED(ArTrafficHeader);

ArTrafficHeader::ArTrafficHeader()
    : m_seq(0),
      m_sendTimeNs(0),
      m_kind(0),
      m_hops(0)
{
}

TypeId
ArTrafficHeader::GetTypeId()
{
    static TypeId tid = TypeId("ns3::arEaurp::ArTrafficHeader")
                            .SetParent<Header>()
                            .SetGroupName("ArEaurp")
                            .AddConstructor<ArTrafficHeader>();
    return tid;
}

TypeId
ArTrafficHeader::GetInstanceTypeId() const
{
    return GetTypeId();
}

uint32_t
ArTrafficHeader::GetSerializedSize() const
{
    return 18;
}

void
ArTrafficHeader::Serialize(Buffer::Iterator i) const
{
    i.WriteHtonU64(m_seq);
    i.WriteHtonU64(m_sendTimeNs);
    i.WriteU8(m_kind);
    i.WriteU8(m_hops);
}

uint32_t
ArTrafficHeader::Deserialize(Buffer::Iterator start)
{
    Buffer::Iterator i = start;
    m_seq = i.ReadNtohU64();
    m_sendTimeNs = i.ReadNtohU64();
    m_kind = i.ReadU8();
    m_hops = i.ReadU8();
    return i.GetDistanceFrom(start);
}

void
ArTrafficHeader::Print(std::ostream& os) const
{
    os << (IsAck() ? "ACK" : "DATA") << " seq " << m_seq << " hops " << (uint32_t)m_hops;
}

// ---------------------------------------------------------------------------

NS_OBJECT_ENSURE_REGISTERED(ArTrafficApp);

TypeId
ArTrafficApp::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::arEaurp::ArTrafficApp")
            .SetParent<Application>()
            .SetGroupName("ArEaurp")
            .AddConstructor<ArTrafficApp>()
            .AddAttribute("Remote",
                          "Destination address; unset means receive only.",
                          Ipv4AddressValue(Ipv4Address::GetZero()),
                          MakeIpv4AddressAccessor(&ArTrafficApp::m_remote),
                          MakeIpv4AddressChecker())
            .AddAttribute("Port",
                          "UDP port used by the flow.",
                          UintegerValue(9),
                          MakeUintegerAccessor(&ArTrafficApp::m_port),
                          MakeUintegerChecker<uint16_t>())
            .AddAttribute("Interval",
                          "Time between two data packets.",
                          TimeValue(Seconds(1.0)),
                          MakeTimeAccessor(&ArTrafficApp::m_interval),
                          MakeTimeChecker())
            .AddAttribute("MinSize",
                          "Smallest payload, in bytes.",
                          UintegerValue(512),
                          MakeUintegerAccessor(&ArTrafficApp::m_minSize),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("MaxSize",
                          "Largest payload, in bytes.",
                          UintegerValue(1024),
                          MakeUintegerAccessor(&ArTrafficApp::m_maxSize),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("AckTimeout",
                          "How long the source waits for an acknowledgement.",
                          TimeValue(Seconds(2.0)),
                          MakeTimeAccessor(&ArTrafficApp::m_ackTimeout),
                          MakeTimeChecker())
            .AddAttribute("EnableAck",
                          "Whether the destination acknowledges each packet.",
                          BooleanValue(true),
                          MakeBooleanAccessor(&ArTrafficApp::m_enableAck),
                          MakeBooleanChecker());
    return tid;
}

ArTrafficApp::ArTrafficApp()
    : m_socket(nullptr),
      m_remote(Ipv4Address::GetZero()),
      m_port(9),
      m_interval(Seconds(1.0)),
      m_minSize(512),
      m_maxSize(1024),
      m_ackTimeout(Seconds(2.0)),
      m_enableAck(true),
      m_seq(0),
      m_sent(0),
      m_received(0)
{
    m_sizeRng = CreateObject<UniformRandomVariable>();
    m_jitterRng = CreateObject<UniformRandomVariable>();
}

ArTrafficApp::~ArTrafficApp()
{
}

int64_t
ArTrafficApp::AssignStreams(int64_t stream)
{
    m_sizeRng->SetStream(stream);
    m_jitterRng->SetStream(stream + 1);
    return 2;
}

void
ArTrafficApp::StartApplication()
{
    if (!m_socket)
    {
        m_socket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
        m_socket->Bind(InetSocketAddress(Ipv4Address::GetAny(), m_port));
        m_socket->SetRecvCallback(MakeCallback(&ArTrafficApp::HandleRead, this));
        m_socket->SetIpRecvTtl(true);
        m_socket->SetAllowBroadcast(false);
    }
    if (m_remote != Ipv4Address::GetZero())
    {
        // Stagger the flows so a hundred sources do not all fire together.
        m_sendEvent = Simulator::Schedule(MilliSeconds(m_jitterRng->GetInteger(0, 1000)),
                                          &ArTrafficApp::Send,
                                          this);
    }
}

void
ArTrafficApp::StopApplication()
{
    m_sendEvent.Cancel();
    for (auto& t : m_ackTimers)
    {
        t.second.Cancel();
    }
    m_ackTimers.clear();
    if (m_socket)
    {
        m_socket->Close();
        m_socket->SetRecvCallback(MakeNullCallback<void, Ptr<Socket>>());
    }
}

void
ArTrafficApp::Send()
{
    const uint32_t payload = m_sizeRng->GetInteger(m_minSize, m_maxSize);
    ArTrafficHeader header;
    header.SetSeq(++m_seq);
    header.SetSendTime(Simulator::Now());
    header.SetAck(false);

    Ptr<Packet> packet = Create<Packet>(payload - header.GetSerializedSize());
    packet->AddHeader(header);

    m_socket->SendTo(Protect(packet, m_seq), 0, InetSocketAddress(m_remote, m_port));
    m_sent++;
    if (auto routing = DynamicCast<RoutingProtocol>(GetNode()->GetObject<Ipv4>()->GetRoutingProtocol()))
        routing->RecordEndpoint(true);
    Oracle::Get().CountAppTx(payload);

    if (m_enableAck)
    {
        // Loopback route discovery is queued before this ScheduleNow event.
        // Store the selected action with this sequence before any ACK arrives.
        Simulator::ScheduleNow(&ArTrafficApp::RecordDecision, this, m_seq);
        m_ackTimers[m_seq] =
            Simulator::Schedule(m_ackTimeout, &ArTrafficApp::AckTimeout, this, m_seq);
    }

    m_sendEvent = Simulator::Schedule(m_interval, &ArTrafficApp::Send, this);
}

void
ArTrafficApp::HandleRead(Ptr<Socket> socket)
{
    Ptr<Packet> packet;
    Address from;
    while ((packet = socket->RecvFrom(from)))
    {
        if (packet->GetSize() == 0)
        {
            break;
        }
        SocketIpTtlTag ttlTag;
        uint32_t hops = 1;
        if (packet->RemovePacketTag(ttlTag))
        {
            hops = (uint32_t)(64 - ttlTag.GetTtl()) + 1;
        }

        ArTrafficHeader header;
        if (m_cipher)
        {
            std::vector<uint8_t> wire(packet->GetSize()), clear;
            packet->CopyData(wire.data(), wire.size());
            if (!m_cipher->Open(wire, clear))
            {
                Oracle::Get().CountCryptoFailure();
                continue;
            }
            packet = Create<Packet>(clear.data(), clear.size());
        }
        if (packet->GetSize() < header.GetSerializedSize()) continue;
        packet->RemoveHeader(header);
        const Ipv4Address peer = InetSocketAddress::ConvertFrom(from).GetIpv4();

        if (header.IsAck())
        {
            auto t = m_ackTimers.find(header.GetSeq());
            if (t != m_ackTimers.end())
            {
                t->second.Cancel();
                m_ackTimers.erase(t);
                ReportDelivery(true, header.GetHops(), header.GetSeq(), header.GetSendTime());
            }
            continue;
        }

        m_received++;
        if (auto routing = DynamicCast<RoutingProtocol>(GetNode()->GetObject<Ipv4>()->GetRoutingProtocol()))
            routing->RecordEndpoint(false);
        Oracle::Get().CountAppRx(packet->GetSize() + header.GetSerializedSize(),
                                 Simulator::Now() - header.GetSendTime(),
                                 hops);

        if (m_enableAck)
        {
            ArTrafficHeader ack;
            ack.SetSeq(header.GetSeq());
            ack.SetSendTime(header.GetSendTime());
            ack.SetAck(true);
            ack.SetHops((uint8_t)std::min<uint32_t>(255, hops));
            Ptr<Packet> reply = Create<Packet>(14); // 32-byte acknowledgement
            reply->AddHeader(ack);
            socket->SendTo(Protect(reply, ack.GetSeq()), 0, InetSocketAddress(peer, m_port));
        }
    }
}

void
ArTrafficApp::AckTimeout(uint64_t seq)
{
    m_ackTimers.erase(seq);
    ReportDelivery(false, 0, seq, Simulator::Now() - m_ackTimeout);
}

Ptr<Packet> ArTrafficApp::Protect(Ptr<Packet> packet, uint64_t sequence)
{
    if (!m_cipher) return packet;
    std::vector<uint8_t> clear(packet->GetSize());
    packet->CopyData(clear.data(), clear.size());
    auto wire = m_cipher->Seal(clear, sequence);
    Oracle::Get().CountCryptoTx(wire.size() - clear.size());
    return Create<Packet>(wire.data(), wire.size());
}

void
ArTrafficApp::RecordDecision(uint64_t sequence)
{
    auto routing = DynamicCast<RoutingProtocol>(GetNode()->GetObject<Ipv4>()->GetRoutingProtocol());
    if (routing) m_decisionIds[sequence] = routing->DecisionId(m_remote);
}

void
ArTrafficApp::ReportDelivery(bool delivered, uint32_t hops, uint64_t sequence, Time sent)
{
    Oracle::Get().CountAppFeedback(delivered, sent);
    Ptr<Ipv4> ipv4 = GetNode()->GetObject<Ipv4>();
    if (!ipv4)
    {
        return;
    }
    Ptr<RoutingProtocol> routing = DynamicCast<RoutingProtocol>(ipv4->GetRoutingProtocol());
    if (routing)
    {
        auto decision = m_decisionIds.find(sequence);
        routing->NotifyDelivery(m_remote, delivered, hops == 0 ? 3 : hops,
                                decision == m_decisionIds.end() ? 0 : decision->second);
    }
    m_decisionIds.erase(sequence);
}

} // namespace arEaurp
} // namespace ns3
