#ifndef AR_EAURP_SCENARIO_H
#define AR_EAURP_SCENARIO_H

#include <map>
#include <string>

namespace ns3::arEaurp
{
using Measurements = std::map<std::string, double>;
// Run a complete commissioning/evaluation pair and destroy its simulator.
// Arguments follow the individual scenario CLI; output is optional.
int RunScenarioCommand(int argc, char* argv[], Measurements* output = nullptr);
}
#endif
