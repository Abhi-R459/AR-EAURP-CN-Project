#include "ar-eaurp-experiments.h"
#include "ar-eaurp-results.h"
#include "ns3/core-module.h"
#include "ns3/basic-energy-source.h"
#include "ns3/random-waypoint-mobility-model.h"
#include "ns3/wifi-radio-energy-model.h"
#include "ns3/aodv-routing-protocol.h"
#include <dlfcn.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>

namespace ns3::arEaurp
{
namespace
{
using Parameters = std::map<std::string, std::string>;
struct Profile
{
    std::string name;
    unsigned duration, warmup, commission, runs, ganEpochs, lstmEpochs, lifetime;
};
const std::vector<std::pair<std::string, std::string>> kPolicies{
    {"AODV (reference baseline)", "aodv"}, {"EAURP (base substrate)", "eaurp"},
    {"A: DRL-EAURP (paper)", "drl-paper"}, {"B: DRL-EAURP (senior)", "drl-senior"},
    {"C: AR-EAURP (advancement)", "ar-eaurp"}};
Profile GetProfile(const std::string& name)
{
    if (name == "smoke") return {name, 12, 2, 100, 1, 2, 1, 40};
    if (name == "quick") return {name, 120, 20, 120, 2, 60, 10, 900};
    if (name == "full") return {name, 400, 30, 240, 5, 120, 30, 1500};
    throw std::runtime_error("Unknown profile; use smoke, quick or full");
}
Parameters Defaults(const Profile& profile)
{
    Parameters args{{"time", std::to_string(profile.duration)}, {"warmup", std::to_string(profile.warmup)},
                    {"commission", std::to_string(profile.commission)}, {"ganEpochs", std::to_string(profile.ganEpochs)},
                    {"lstmEpochs", std::to_string(profile.lstmEpochs)}, {"seed", "20260909"}, {"run", "1"},
                    {"protocol", "ar-eaurp"}, {"attack", "none"}, {"malicious", "0"}};
    if (profile.name == "smoke")
        args.insert({{"nodes", "16"}, {"flows", "6"}, {"area", "200"}, {"maxSpeed", "5"}});
    return args;
}
ExperimentRow Row(const std::string& label, const std::string& policy, Parameters args, Parameters meta = {})
{
    return {label, policy, args.at("protocol"), args.at("attack"), std::move(args), std::move(meta), {}};
}
ExperimentResults Configurations(const Profile& p, const std::set<std::string>& selected)
{
    ExperimentResults all;
    auto add = [&](const std::string& name, const std::string& policy, const std::string& protocol,
                   const std::string& label, Parameters flags, Parameters meta) {
        auto args = Defaults(p); args["protocol"] = protocol;
        for (const auto& [key, value] : flags) args[key] = value;
        all[name].push_back(Row(label, policy, std::move(args), std::move(meta)));
    };
    for (const auto& [label, protocol] : kPolicies)
    {
        if (selected.count("e1"))
            for (unsigned speed : p.name == "smoke" ? std::vector<unsigned>{1, 5} : std::vector<unsigned>{1, 5, 10, 15, 20})
                add("e1_speed", label, protocol, label + " @ " + std::to_string(speed) + " m/s",
                    {{"maxSpeed", std::to_string(speed)}}, {{"speed_value", std::to_string(speed)}});
        if (selected.count("e2"))
            for (unsigned nodes : p.name == "smoke" ? std::vector<unsigned>{12, 24} : std::vector<unsigned>{60, 80, 100, 120, 150, 200})
                add("e2_density", label, protocol, label + " @ N=" + std::to_string(nodes),
                    {{"nodes", std::to_string(nodes)}}, {{"node_count", std::to_string(nodes)}});
        if (selected.count("e3"))
            for (const auto* attack : {"blackhole", "grayhole", "trust_poisoning"})
                for (unsigned percent : p.name == "smoke" ? std::vector<unsigned>{0, 30} : std::vector<unsigned>{0, 10, 20, 30, 40, 50})
                    add("e3_attack", label, protocol, label + " | " + attack + " @ " + std::to_string(percent) + "%",
                        {{"attack", attack}, {"malicious", std::to_string(percent / 100.0)}},
                        {{"attack_type", attack}, {"malicious_pct", std::to_string(percent)}});
        if (selected.count("e4"))
            for (const auto* mode : {"battery", "solar"})
            {
                const Parameters flags{{"harvest", std::string(mode) == "solar" ? "1" : "0"}};
                add("e4_energy", label, protocol, label + " | " + mode, flags, {{"energy_mode", mode}});
                auto lifetime = flags;
                lifetime["time"] = std::to_string(p.lifetime);
                lifetime["energy"] = p.name == "smoke" ? "20" : "350";
                add("e4b_lifetime", label, protocol, label + " | " + mode, lifetime, {{"energy_mode", mode}});
            }
        if (selected.count("e6"))
            add("e6_overhead", label, protocol, label, {{"attack", "grayhole"}, {"malicious", "0.3"}}, {});
    }
    if (selected.count("e5"))
    {
        const std::vector<std::pair<std::string, Parameters>> variants{
            {"C full", {}}, {"C without GAN", {{"gan", "0"}}}, {"C without LSTM", {{"lstm", "0"}}},
            {"C without CMDP", {{"cmdp", "0"}}}, {"C bare", {{"gan", "0"}, {"lstm", "0"}, {"cmdp", "0"}}},
            {"C without energy excuse", {{"energyExcuse", "0"}}}};
        for (const auto& [label, variant] : variants)
        {
            auto flags = variant; flags["attack"] = "grayhole"; flags["malicious"] = "0.3";
            add("e5_ablation", label, "ar-eaurp", label, flags, {});
        }
        for (const auto* floor : {"0.70", "0.80", "0.90", "0.95"})
            add("e5b_cmdp_floor", kPolicies.back().first, "ar-eaurp", std::string("C floor=") + floor,
                {{"attack", "grayhole"}, {"malicious", "0.3"}, {"pdrFloor", floor}}, {{"pdr_floor", floor}});
    }
    if (selected.count("e6"))
        add("e6_overhead", "C without ECC", "ar-eaurp", "C without ECC",
            {{"attack", "grayhole"}, {"malicious", "0.3"}, {"ecc", "0"}}, {});
    return all;
}
Measurements Run(const Parameters& parameters, bool verbose = false)
{
    std::vector<std::string> arguments{"ar-eaurp-sim"};
    for (const auto& [key, value] : parameters) arguments.push_back("--" + key + "=" + value);
    std::vector<char*> argv; for (auto& arg : arguments) argv.push_back(arg.data());
    Measurements result; std::ostringstream log;
    auto* previous = std::cout.rdbuf(); if (!verbose) std::cout.rdbuf(log.rdbuf());
    int status;
    try { status = RunScenarioCommand(argv.size(), argv.data(), &result); }
    catch (...) { std::cout.rdbuf(previous); throw; }
    std::cout.rdbuf(previous);
    if (status != 0) throw std::runtime_error("Scenario failed (" + std::to_string(status) + "): " + log.str());
    if (!ValidMeasurements(result)) throw std::runtime_error("Scenario produced invalid measurements");
    return result;
}
std::string Signature(const std::string& identity, const Parameters& args)
{
    std::string material = "ns-3.45 native batch v1\n" + identity + '\n';
    for (const auto& [key, value] : args) material += key + "=" + value + '\n';
    return Digest(material);
}
Measurements CachedRun(const Parameters& args, const fs::path& root, const std::string& identity,
                       bool fresh, unsigned& executed, unsigned& reused)
{
    const auto signature = Signature(identity, args);
    const auto file = root / "raw" / (signature + ".csv"); Measurements result;
    if (!fresh && ReadCheckpoint(file, signature, result)) { ++reused; return result; }
    result = Run(args); SaveCheckpoint(file, signature, result); ++executed; return result;
}
void Require(bool condition, const std::string& description)
{
    if (!condition) throw std::runtime_error("Verification failed: " + description);
    std::cout << "PASS " << description << '\n';
}
void Verify(const std::string& identity)
{
    auto args = Defaults(GetProfile("smoke"));
    for (const auto& [key, value] : Parameters{{"nodes", "6"}, {"area", "30"}, {"flows", "2"},
                                             {"time", "5"}, {"warmup", "1"}, {"harvest", "0"}, {"train", "0"}}) args[key] = value;
    args["protocol"] = "aodv";
    const auto first = Run(args), second = Run(args);
    auto a = first, b = second; a.erase("wall_clock_seconds"); b.erase("wall_clock_seconds");
    if (a != b) for (const auto& [key, value] : a)
        if (b.at(key) != value) std::cerr << "repeat mismatch " << key << ": " << value << " vs " << b.at(key) << '\n';
    Require(a == b, "repeated native runs reproduce every simulated metric");
    Require(first.at("app_rx") > 0 && first.at("crypto_overhead_bytes") > 0 && first.at("crypto_auth_failures") == 0, "protected UDP delivers without authentication failures");
    for (const auto* protocol : {"eaurp", "drl-paper", "drl-senior", "ar-eaurp", "ns3-aodv"})
    {
        args["protocol"] = protocol; const auto result = Run(args);
        Require(result.at("app_rx") > 0, std::string("delivery: ") + protocol);
        if (std::string(protocol).find("drl-") == 0) Require(result.at("q_updates") > 0, std::string("Q-learning: ") + protocol);
    }
    args["protocol"] = "drl-paper"; args["nodes"] = "2"; args["flows"] = "1"; args["area"] = "1000000";
    const auto isolated = Run(args);
    Require(isolated.at("app_tx") == isolated.at("app_feedback_success") + isolated.at("app_feedback_timeout") &&
            isolated.at("q_updates") == isolated.at("app_tx"), "cooldown completes disconnected route feedback");
    args["protocol"] = "aodv"; args["area"] = "30";
    for (const auto* energy : {"0.01", "0.1", "0.3", "2"})
    {
        args["energy"] = energy; const auto result = Run(args);
        Require(result.at("dead_nodes") == 2 && result.at("radio_off_nodes") == 2 &&
                result.at("radio_current_a") == 0 && result.at("first_death_s") > 0 &&
                result.at("first_death_s") <= std::stod(energy) / .819 + .005, std::string("physical depletion: ") + energy + " J");
    }
    args["harvest"] = "1"; args["panelFraction"] = "1"; args["dayLength"] = "40"; args["time"] = "80";
    const auto recharged = Run(args);
    Require(recharged.at("dead_nodes") == 2 && recharged.at("residual_energy_j") > 0 &&
            recharged.at("radio_off_nodes") == 2 && recharged.at("radio_current_a") == 0, "depleted PHYs remain off after reservoir recharge");
    args = Defaults(GetProfile("smoke")); args["protocol"] = "aodv";
    for (const auto& [key, value] : Parameters{{"nodes", "30"}, {"flows", "30"}, {"area", "300"}, {"time", "25"},
                                             {"attack", "grayhole"}, {"malicious", "1"}, {"train", "0"}}) args[key] = value;
    for (const auto* size : {"680", "900"})
    {
        args["minSize"] = args["maxSize"] = size;
        const auto result = Run(args);
        Require((result.at("adversary_drops") > 0) == (std::string(size) == "900"), std::string("grayhole plaintext-size selection: ") + size);
    }
    args = Defaults(GetProfile("smoke"));
    for (const auto& [key, value] : Parameters{{"nodes", "40"}, {"flows", "30"}, {"area", "350"}, {"maxSpeed", "20"},
                                             {"time", "60"}, {"warmup", "10"}, {"commission", "120"}, {"ganEpochs", "5"}, {"lstmEpochs", "1"},
                                             {"attack", "grayhole"}, {"malicious", "0.3"}}) args[key] = value;
    const auto learned = Run(args);
    Require(learned.at("gan_trained") == 1 && learned.at("detector_windows") > 0 && learned.at("lstm_trained") == 1 &&
            learned.at("lstm_validation_sequences") > 0 && learned.at("adversary_drops") > 0 && learned.at("cmdp_decisions") > 0,
            "trained GAN/LSTM/CMDP execute under a real grayhole attack");
    const auto stats = Aggregate({{{"pdr", .5}}, {{"pdr", 1}}});
    Require(stats.at("pdr") == .75 && std::abs(stats.at("pdr_std") - std::sqrt(.125)) < 1e-12, "sample seed standard deviation");
    for (const auto& invalid : std::vector<Parameters>{{{"protocol", "typo"}}, {{"nodes", "1"}},
                                                       {{"minSpeed", "0"}}, {{"malicious", "-0.1"}}, {{"time", "1"}}})
    {
        auto invalidArgs = Defaults(GetProfile("smoke"));
        for (const auto& [key, value] : invalid) invalidArgs[key] = value;
        bool rejected = false;
        try { Run(invalidArgs); } catch (const std::runtime_error&) { rejected = true; }
        Require(rejected, "invalid scenario rejected: " + invalid.begin()->first);
    }
    const auto temp = fs::temp_directory_path() / ("ar-eaurp-native-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    fs::create_directories(temp);
    try
    {
        unsigned executed = 0, reused = 0;
        args = Defaults(GetProfile("smoke")); args["protocol"] = "aodv"; args["train"] = "0";
        const auto one = CachedRun(args, temp, identity, false, executed, reused);
        const auto checkpoint = temp / "raw" / (Signature(identity, args) + ".csv"); const auto time = fs::last_write_time(checkpoint);
        const auto two = CachedRun(args, temp, identity, false, executed, reused);
        Require(one == two && executed == 1 && reused == 1 && fs::last_write_time(checkpoint) == time, "resume preserves matching checkpoints");
        WriteAtomic(checkpoint, "truncated checkpoint\n");
        CachedRun(args, temp, identity, false, executed, reused);
        Require(executed == 2, "corrupt checkpoint is recomputed");
        Measurements wrong; Require(!ReadCheckpoint(checkpoint, Digest(identity), wrong), "changed build/config signature cannot resume");
        Require(CsvQuote("comma, \"quote\"\nline") == "\"comma, \"\"quote\"\"\nline\"", "CSV labels preserve commas, quotes and newlines");
        const auto file = temp / "hash-input"; WriteAtomic(file, "before"); const auto before = Digest(ReadFile(file)); WriteAtomic(file, "after");
        Require(before != Digest(ReadFile(file)), "content identity detects changes");
    }
    catch (...) { fs::remove_all(temp); throw; }
    fs::remove_all(temp);
    const auto configured = Configurations(GetProfile("smoke"), {"e1", "e2", "e3", "e4", "e5", "e6"});
    unsigned count = 0;
    for (const auto& [name, rows] : configured) { (void)name; count += rows.size(); }
    Require(configured.size() == 8 && count == 86, "all eight E1–E6 tables and 86 smoke configurations are configured");
}
bool SetString(std::string* destination, const std::string& value) { *destination = value; return true; }
void CheckLoadedInstallation(const fs::path& home, const char* argument)
{
    fs::path executable;
#ifdef __APPLE__
    uint32_t size = 0; _NSGetExecutablePath(nullptr, &size);
    std::vector<char> buffer(size);
    if (_NSGetExecutablePath(buffer.data(), &size) != 0) throw std::runtime_error("Cannot locate running executable");
    executable = fs::canonical(buffer.data());
#elif defined(__linux__)
    executable = fs::canonical("/proc/self/exe");
#else
    executable = fs::canonical(argument);
#endif
    (void)argument;
    if (executable.parent_path() != fs::canonical(home / "build/scratch"))
        throw std::runtime_error("--ns3-home does not match the running native executable");
    const auto directory = fs::canonical(home / "build/lib");
    for (const auto* symbol : {reinterpret_cast<const void*>(&RunExperimentsCommand),
                              reinterpret_cast<const void*>(&RngSeedManager::GetSeed),
                              reinterpret_cast<const void*>(&energy::BasicEnergySource::GetTypeId),
                              reinterpret_cast<const void*>(&RandomWaypointMobilityModel::GetTypeId),
                              reinterpret_cast<const void*>(&WifiRadioEnergyModel::GetTypeId),
                              reinterpret_cast<const void*>(&aodv::RoutingProtocol::GetTypeId)})
    {
        Dl_info info{};
        if (!dladdr(symbol, &info) || !info.dli_fname || fs::canonical(info.dli_fname).parent_path() != directory)
            throw std::runtime_error("Loaded ns-3 libraries do not match --ns3-home");
    }
}
}

int RunExperimentsCommand(int argc, char* argv[])
{
    try
    {
        std::string project = std::getenv("AR_EAURP_PROJECT") ? std::getenv("AR_EAURP_PROJECT") : fs::current_path().string();
        std::string home = std::getenv("NS3_HOME") ? std::getenv("NS3_HOME") : std::string(std::getenv("HOME") ? std::getenv("HOME") : ".") + "/.cache/ar-eaurp/ns-3.45";
        std::string profile = "quick", out, only = "e1,e2,e3,e4,e5,e6", report;
        bool stamp = false, verify = false, fresh = false, render = true, notebooks = false;
        CommandLine cmd(__FILE__);
        cmd.AddValue("project", "Project source root", MakeBoundCallback(&SetString, &project));
        cmd.AddValue("ns3-home", "ns-3.45 installation", MakeBoundCallback(&SetString, &home));
        cmd.AddValue("profile", "smoke / quick / full", MakeBoundCallback(&SetString, &profile));
        cmd.AddValue("out", "Output directory; defaults to results/ns3-native-PROFILE", MakeBoundCallback(&SetString, &out));
        cmd.AddValue("only", "Comma-separated experiments, e1 through e6", MakeBoundCallback(&SetString, &only));
        cmd.AddValue("report", "Optional copy of generated Markdown report", MakeBoundCallback(&SetString, &report));
        cmd.AddValue("fresh", "Recompute matching checkpoints", fresh);
        cmd.AddValue("render", "Render SVGs with gnuplot; 0 exports scripts only", render);
        cmd.AddValue("stamp", "Record successful native build identity", stamp);
        cmd.AddValue("verify", "Run real-network native integration checks", verify);
        cmd.AddValue("notebooks", "Generate shell-only Colab notebooks", notebooks);
        cmd.Parse(argc, argv);
        const auto root = fs::absolute(project), installation = fs::absolute(home);
        CheckLoadedInstallation(installation, argv[0]);
        if (notebooks) { ExportNotebooks(root); return 0; }
        const auto identity = BuildIdentity(root, installation);
        const auto stampFile = installation / ".ar-eaurp-native-build.sha256";
        if (stamp) { WriteAtomic(stampFile, identity + '\n'); std::cout << "Stamped native build " << identity << '\n'; return 0; }
        if (!fs::is_regular_file(stampFile) || ReadFile(stampFile) != identity + '\n')
            throw std::runtime_error("Native build is stale or unrecorded; rerun ns3/scripts/setup.sh");
        if (verify) { Verify(identity); return 0; }
        const auto budget = GetProfile(profile);
        std::set<std::string> selected; std::istringstream names(only); std::string name;
        while (std::getline(names, name, ','))
        { if (!std::set<std::string>{"e1", "e2", "e3", "e4", "e5", "e6"}.count(name)) throw std::runtime_error("Unknown experiment: " + name); selected.insert(name); }
        if (selected.empty()) throw std::runtime_error("Select at least one experiment");
        const fs::path destination = out.empty() ? root / "results" / ("ns3-native-" + profile) : fs::absolute(out);
        // Reports contain only results selected and completed by this invocation.
        auto results = Configurations(budget, selected);
        fs::create_directories(destination);
        WriteAtomic(destination / "manifest.json", "{\n\"engine\":\"ns-3\",\"ns3_version\":\"3.45\",\"workflow\":\"C++\",\"source_sha256\":" + JsonQuote(identity) + ",\"profile\":" + JsonQuote(profile) + ",\"runs\":" + std::to_string(budget.runs) + ",\"selection\":" + JsonQuote(only) + "\n}\n");
        unsigned configurations = 0, executed = 0, reused = 0;
        for (auto& [experiment, rows] : results)
        {
            std::cout << experiment << ": " << rows.size() << " configurations\n";
            std::vector<ExperimentRow> completed;
            for (auto& row : rows)
            {
                if (BuildIdentity(root, installation) != identity) throw std::runtime_error("Source or linked library changed during the batch; rebuild before continuing");
                std::vector<Measurements> seeds;
                for (unsigned run = 1; run <= budget.runs; ++run)
                {
                    auto args = row.parameters; args["run"] = std::to_string(run);
                    seeds.push_back(CachedRun(args, destination, identity, fresh, executed, reused));
                }
                row.values = Aggregate(seeds); completed.push_back(row); ++configurations;
                WriteCsv(destination / "csv" / (experiment + ".csv"), completed, identity, profile);
                std::cout << "  " << row.label << ": PDR=" << row.values.at("pdr") << '\n';
            }
        }
        WriteReports(destination, results, identity, profile, render);
        if (!report.empty()) WriteAtomic(fs::absolute(report), ReadFile(destination / "report.md"));
        std::cout << "Completed " << configurations << " configurations; " << executed << " native runs, " << reused
                  << " resumed runs. Report: " << destination / "report.html" << '\n';
        return 0;
    }
    catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 2; }
}
}
