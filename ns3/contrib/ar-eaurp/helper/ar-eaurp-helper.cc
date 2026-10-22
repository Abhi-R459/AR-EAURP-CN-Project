#include "ar-eaurp-helper.h"

#include "ns3/ar-eaurp-routing-protocol.h"
#include "ns3/ipv4-list-routing.h"
#include "ns3/node-list.h"
#include "ns3/ptr.h"

namespace ns3
{

ArEaurpHelper::ArEaurpHelper()
{
    m_agentFactory.SetTypeId("ns3::arEaurp::RoutingProtocol");
}

ArEaurpHelper*
ArEaurpHelper::Copy() const
{
    return new ArEaurpHelper(*this);
}

Ptr<Ipv4RoutingProtocol>
ArEaurpHelper::Create(Ptr<Node> node) const
{
    Ptr<arEaurp::RoutingProtocol> agent = m_agentFactory.Create<arEaurp::RoutingProtocol>();
    node->AggregateObject(agent);
    return agent;
}

void
ArEaurpHelper::Set(std::string name, const AttributeValue& value)
{
    m_agentFactory.Set(name, value);
}

int64_t
ArEaurpHelper::AssignStreams(NodeContainer c, int64_t stream)
{
    int64_t currentStream = stream;
    for (auto i = c.Begin(); i != c.End(); ++i)
    {
        Ptr<Node> node = *i;
        Ptr<Ipv4> ipv4 = node->GetObject<Ipv4>();
        NS_ASSERT_MSG(ipv4, "Ipv4 not installed on node");
        Ptr<Ipv4RoutingProtocol> proto = ipv4->GetRoutingProtocol();
        NS_ASSERT_MSG(proto, "Ipv4 routing not installed on node");
        Ptr<arEaurp::RoutingProtocol> ar = DynamicCast<arEaurp::RoutingProtocol>(proto);
        if (ar)
        {
            currentStream += ar->AssignStreams(currentStream);
            continue;
        }
        Ptr<Ipv4ListRouting> list = DynamicCast<Ipv4ListRouting>(proto);
        if (list)
        {
            int16_t priority;
            Ptr<Ipv4RoutingProtocol> listProto;
            Ptr<arEaurp::RoutingProtocol> listAr;
            for (uint32_t i2 = 0; i2 < list->GetNRoutingProtocols(); i2++)
            {
                listProto = list->GetRoutingProtocol(i2, priority);
                listAr = DynamicCast<arEaurp::RoutingProtocol>(listProto);
                if (listAr)
                {
                    currentStream += listAr->AssignStreams(currentStream);
                    break;
                }
            }
        }
    }
    return (currentStream - stream);
}

} // namespace ns3
