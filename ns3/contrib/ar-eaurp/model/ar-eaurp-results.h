#ifndef AR_EAURP_RESULTS_H
#define AR_EAURP_RESULTS_H
#include "ar-eaurp-scenario.h"
#include <filesystem>
#include <vector>

namespace ns3::arEaurp
{
namespace fs = std::filesystem;
struct ExperimentRow
{
    std::string label, policy, protocol, attack;
    std::map<std::string, std::string> parameters, metadata;
    Measurements values;
};
using ExperimentResults = std::map<std::string, std::vector<ExperimentRow>>;
std::string Digest(const std::string& value);
std::string BuildIdentity(const fs::path& project, const fs::path& home);
std::string ReadFile(const fs::path& file);
void WriteAtomic(const fs::path& file, const std::string& value);
std::string CsvQuote(const std::string& value);
std::string JsonQuote(const std::string& value);
std::string ShellQuote(const std::string& value);
bool ValidMeasurements(const Measurements& values);
Measurements Aggregate(const std::vector<Measurements>& runs);
bool ReadCheckpoint(const fs::path& path, const std::string& signature, Measurements& values);
void SaveCheckpoint(const fs::path& path, const std::string& signature, const Measurements& values);
void WriteCsv(const fs::path& path, const std::vector<ExperimentRow>& rows,
              const std::string& identity, const std::string& profile);
void WriteReports(const fs::path& root, const ExperimentResults& results,
                  const std::string& identity, const std::string& profile, bool render);
void ExportNotebooks(const fs::path& project);
}
#endif
