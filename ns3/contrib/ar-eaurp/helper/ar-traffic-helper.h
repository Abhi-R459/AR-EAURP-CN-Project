/*
 * Installs the variable-size acknowledged CBR application.
 */

#ifndef AR_TRAFFIC_HELPER_H
#define AR_TRAFFIC_HELPER_H

#include "ns3/application-container.h"
#include "ns3/attribute.h"
#include "ns3/node-container.h"
#include "ns3/object-factory.h"

namespace ns3
{

class ArTrafficHelper
{
  public:
    ArTrafficHelper();

    void SetAttribute(std::string name, const AttributeValue& value);

    ApplicationContainer Install(Ptr<Node> node) const;
    ApplicationContainer Install(NodeContainer c) const;

    /// Fix the streams used by the applications' random variables.
    static int64_t AssignStreams(ApplicationContainer c, int64_t stream);

  private:
    ObjectFactory m_factory;
};

} // namespace ns3

#endif /* AR_TRAFFIC_HELPER_H */
