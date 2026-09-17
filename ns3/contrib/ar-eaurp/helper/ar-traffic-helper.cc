#include "ar-traffic-helper.h"

#include "ns3/ar-traffic-app.h"

namespace ns3
{

ArTrafficHelper::ArTrafficHelper()
{
    m_factory.SetTypeId("ns3::arEaurp::ArTrafficApp");
}

void
ArTrafficHelper::SetAttribute(std::string name, const AttributeValue& value)
{
    m_factory.Set(name, value);
}

ApplicationContainer
ArTrafficHelper::Install(Ptr<Node> node) const
{
    Ptr<arEaurp::ArTrafficApp> app = m_factory.Create<arEaurp::ArTrafficApp>();
    node->AddApplication(app);
    return ApplicationContainer(app);
}

ApplicationContainer
ArTrafficHelper::Install(NodeContainer c) const
{
    ApplicationContainer apps;
    for (auto i = c.Begin(); i != c.End(); ++i)
    {
        apps.Add(Install(*i));
    }
    return apps;
}

int64_t
ArTrafficHelper::AssignStreams(ApplicationContainer c, int64_t stream)
{
    int64_t current = stream;
    for (uint32_t i = 0; i < c.GetN(); ++i)
    {
        Ptr<arEaurp::ArTrafficApp> app = DynamicCast<arEaurp::ArTrafficApp>(c.Get(i));
        if (app)
        {
            current += app->AssignStreams(current);
        }
    }
    return current - stream;
}

} // namespace ns3
