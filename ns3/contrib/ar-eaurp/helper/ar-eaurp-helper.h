/*
 * Installs the AR-EAURP routing protocol on a node, the way AodvHelper does.
 */

#ifndef AR_EAURP_HELPER_H
#define AR_EAURP_HELPER_H

#include "ns3/ipv4-routing-helper.h"
#include "ns3/node-container.h"
#include "ns3/object-factory.h"

namespace ns3
{

class ArEaurpHelper : public Ipv4RoutingHelper
{
  public:
    ArEaurpHelper();

    ArEaurpHelper* Copy() const override;
    Ptr<Ipv4RoutingProtocol> Create(Ptr<Node> node) const override;

    void Set(std::string name, const AttributeValue& value);

    /// Fix the streams used by the protocol's random variables.
    int64_t AssignStreams(NodeContainer c, int64_t stream);

  private:
    ObjectFactory m_agentFactory;
};

} // namespace ns3

#endif /* AR_EAURP_HELPER_H */
