#include "ar-eaurp-results.h"
#include "ns3/gnuplot.h"
#include <iostream>
#include <openssl/evp.h>
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>

namespace ns3::arEaurp
{
namespace
{
std::string Hex(const unsigned char* bytes, unsigned size)
{
    std::ostringstream out;
    for (unsigned i = 0; i < size; ++i)
        out << std::hex << std::setw(2) << std::setfill('0') << unsigned(bytes[i]);
    return out.str();
}
std::string FileDigest(const fs::path& file)
{
    std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> ctx(EVP_MD_CTX_new(), EVP_MD_CTX_free);
    if (!ctx || EVP_DigestInit_ex(ctx.get(), EVP_sha256(), nullptr) != 1)
        throw std::runtime_error("Cannot initialise SHA-256");
    std::ifstream input(file, std::ios::binary);
    if (!input) throw std::runtime_error("Cannot read " + file.string());
    char buffer[65536];
    while (input.read(buffer, sizeof buffer) || input.gcount())
        if (EVP_DigestUpdate(ctx.get(), buffer, input.gcount()) != 1)
            throw std::runtime_error("Cannot hash " + file.string());
    if (!input.eof()) throw std::runtime_error("Cannot read " + file.string());
    unsigned char bytes[EVP_MAX_MD_SIZE]; unsigned size;
    if (EVP_DigestFinal_ex(ctx.get(), bytes, &size) != 1) throw std::runtime_error("SHA-256 failed");
    return Hex(bytes, size);
}
double Value(const ExperimentRow& row, const std::string& key)
{
    return row.values.at(key);
}
std::string Html(const std::string& value)
{
    std::string out;
    for (char c : value)
        switch (c) { case '&': out += "&amp;"; break; case '<': out += "&lt;"; break;
                     case '>': out += "&gt;"; break; case '"': out += "&quot;"; break; default: out += c; }
    return out;
}
std::string Number(double n)
{
    std::ostringstream out; out << std::setprecision(5) << n; return out.str();
}
std::string TickLabel(const std::string& label)
{
    std::string out;
    for (char c : label)
    {
        if (c == '%' ) out += '%'; // gnuplot treats tic labels as format strings
        if (c == '\'' || c == '\\') out += '\\';
        out += c;
    }
    return out;
}
}

std::string Digest(const std::string& value)
{
    unsigned char bytes[EVP_MAX_MD_SIZE]; unsigned size;
    if (EVP_Digest(value.data(), value.size(), bytes, &size, EVP_sha256(), nullptr) != 1)
        throw std::runtime_error("SHA-256 failed");
    return Hex(bytes, size);
}
std::string ReadFile(const fs::path& file)
{
    std::ifstream input(file, std::ios::binary);
    if (!input) throw std::runtime_error("Cannot read " + file.string());
    std::ostringstream out; out << input.rdbuf();
    if (input.bad()) throw std::runtime_error("Cannot read " + file.string());
    return out.str();
}
void WriteAtomic(const fs::path& file, const std::string& value)
{
    if (!file.parent_path().empty()) fs::create_directories(file.parent_path());
    const fs::path temporary = file.string() + ".tmp";
    { std::ofstream out(temporary, std::ios::binary); out << value;
      if (!out) throw std::runtime_error("Cannot write " + temporary.string()); }
    fs::rename(temporary, file);
}
std::string CsvQuote(const std::string& value)
{
    std::string out = "\"";
    for (char c : value) { if (c == '"') out += '"'; out += c; }
    return out + '"';
}
std::string JsonQuote(const std::string& value)
{
    std::ostringstream out; out << '"';
    for (unsigned char c : value)
        switch (c) { case '"': out << "\\\""; break; case '\\': out << "\\\\"; break;
                     case '\n': out << "\\n"; break; case '\r': out << "\\r"; break;
                     case '\t': out << "\\t"; break;
                     default: if (c < 32) out << "\\u00" << std::hex << std::setw(2) << std::setfill('0') << unsigned(c) << std::dec;
                              else out << c; }
    out << '"'; return out.str();
}
std::string ShellQuote(const std::string& value)
{
    std::string out = "'";
    for (char c : value) out += c == '\'' ? "'\\''" : std::string(1, c);
    return out + '\'';
}
std::string BuildIdentity(const fs::path& project, const fs::path& home)
{
    auto version = ReadFile(home / "VERSION");
    version.erase(version.find_last_not_of(" \t\r\n") + 1);
    if (version != "3.45") throw std::runtime_error("Requires ns-3.45");
    std::map<std::string, fs::path> files;
    for (const auto& entry : fs::recursive_directory_iterator(project / "ns3"))
    {
        const auto ext = entry.path().extension();
        if (entry.is_regular_file() && (ext == ".cc" || ext == ".h" || ext == ".txt" || ext == ".sh"))
            files["source/" + entry.path().lexically_relative(project).generic_string()] = entry.path();
    }
    unsigned libraries = 0, binaries = 0;
    for (const auto& entry : fs::directory_iterator(home / "build/lib"))
        if (entry.is_regular_file() && entry.path().filename().string().find("ns3.45-") != std::string::npos &&
            entry.path().filename().string().find("-test-") == std::string::npos)
        { files["library/" + entry.path().filename().string()] = entry.path(); ++libraries; }
    for (const auto& entry : fs::directory_iterator(home / "build/scratch"))
        if (entry.is_regular_file() && (entry.path().filename().string().find("ns3.45-ar-eaurp-sim-") == 0 ||
                                        entry.path().filename().string().find("ns3.45-ar-eaurp-experiments-") == 0))
        { files["binary/" + entry.path().filename().string()] = entry.path(); ++binaries; }
    if (!libraries || binaries < 2) throw std::runtime_error("Build both native executables with setup.sh");
    std::string material;
    for (const auto& [name, path] : files) material += name + "\n" + FileDigest(path) + "\n";
    return Digest(material);
}
bool ValidMeasurements(const Measurements& values)
{
    for (const auto& [key, value] : values) if (key.empty() || !std::isfinite(value)) return false;
    for (const auto* key : {"app_tx", "app_rx", "pdr", "mean_delay_s", "mean_hops", "measurement_seconds",
                           "throughput_bps", "loss_packets", "control_packets", "wall_clock_seconds", "crypto_packets",
                           "crypto_overhead_bytes", "crypto_auth_failures", "gan_trained", "gan_train_windows",
                           "lstm_trained", "lstm_validation_sequences", "lstm_mae_w", "lstm_persistence_mae_w",
                           "lstm_window_mean_mae_w", "residual_energy_j", "harvested_j", "first_death_observed",
                           "first_death_s", "eighty_pct_death_observed", "eighty_pct_dead_s", "lifetime_horizon_s",
                           "cmdp_lambda", "cmdp_lambda_peak", "cmdp_violations", "cmdp_decisions", "detector_windows",
                           "detect_tpr", "detect_fpr", "revoke_tpr", "revoke_fpr", "cfg_seed", "cfg_run", "cfg_nodes"})
        if (!values.count(key)) return false;
    return values.at("app_tx") >= 0 && values.at("app_rx") >= 0 && values.at("app_rx") <= values.at("app_tx") &&
           values.at("pdr") >= 0 && values.at("pdr") <= 1 && values.at("measurement_seconds") > 0;
}
Measurements Aggregate(const std::vector<Measurements>& runs)
{
    if (runs.empty()) throw std::runtime_error("No runs to aggregate");
    Measurements result;
    for (const auto& [key, initial] : runs.front())
    {
        (void)initial;
        double mean = 0, squared = 0; unsigned n = 0;
        for (const auto& run : runs)
        {
            if (run.size() != runs.front().size()) throw std::runtime_error("Inconsistent native result schema");
            const double value = run.at(key);
            if (!std::isfinite(value)) throw std::runtime_error("Non-finite native result");
            const double delta = value - mean;
            mean += delta / ++n; squared += delta * (value - mean);
        }
        result[key] = mean;
        result[key + "_std"] = runs.size() > 1 ? std::sqrt(std::max(0.0, squared / (runs.size() - 1))) : 0;
    }
    result["runs"] = runs.size(); return result;
}
bool ReadCheckpoint(const fs::path& path, const std::string& signature, Measurements& values)
{
    if (!fs::is_regular_file(path)) return false;
    try
    {
        std::istringstream input(ReadFile(path)); std::string magic, saved, checksum;
        std::getline(input, magic); std::getline(input, saved); std::getline(input, checksum);
        std::ostringstream payload; payload << input.rdbuf();
        if (magic != "AR-EAURP native checkpoint 1" || saved != signature || Digest(payload.str()) != checksum) return false;
        Measurements candidate; std::istringstream metrics(payload.str()); std::string line;
        while (std::getline(metrics, line))
        {
            const auto separator = line.find(',');
            if (separator == std::string::npos) return false;
            std::size_t consumed; const auto text = line.substr(separator + 1);
            const double value = std::stod(text, &consumed);
            if (consumed != text.size() || !candidate.emplace(line.substr(0, separator), value).second) return false;
        }
        if (!ValidMeasurements(candidate)) return false;
        values = std::move(candidate); return true;
    }
    catch (const std::exception&) { return false; }
}
void SaveCheckpoint(const fs::path& path, const std::string& signature, const Measurements& values)
{
    if (!ValidMeasurements(values)) throw std::runtime_error("Invalid native measurements");
    std::ostringstream payload; payload << std::setprecision(17);
    for (const auto& [key, value] : values) payload << key << ',' << value << '\n';
    WriteAtomic(path, "AR-EAURP native checkpoint 1\n" + signature + "\n" + Digest(payload.str()) + "\n" + payload.str());
}
void WriteCsv(const fs::path& path, const std::vector<ExperimentRow>& rows,
              const std::string& identity, const std::string& profile)
{
    if (rows.empty()) return;
    std::set<std::string> metadata;
    for (const auto& row : rows) for (const auto& [key, value] : row.metadata) { (void)value; metadata.insert(key); }
    std::ostringstream out; out << std::setprecision(17);
    out << "label,policy_label,protocol,attack,engine,ns3_version,source_sha256,profile";
    for (const auto& key : metadata) out << ',' << key;
    for (const auto& [key, value] : rows.front().values) { (void)value; out << ',' << key; }
    out << '\n';
    for (const auto& row : rows)
    {
        if (row.values.size() != rows.front().values.size()) throw std::runtime_error("Inconsistent result schema");
        out << CsvQuote(row.label) << ',' << CsvQuote(row.policy) << ',' << row.protocol << ',' << row.attack
            << ",ns-3,3.45," << identity << ',' << profile;
        for (const auto& key : metadata)
        { const auto found = row.metadata.find(key); out << ',' << CsvQuote(found == row.metadata.end() ? "" : found->second); }
        for (const auto& [key, value] : rows.front().values) { (void)value; out << ',' << row.values.at(key); }
        out << '\n';
    }
    WriteAtomic(path, out.str());
}

void WriteReports(const fs::path& root, const ExperimentResults& results,
                  const std::string& identity, const std::string& profile, bool render)
{
    const std::vector<std::string> caveats{
        "Every experiment, commissioning run, network event, learning update, checkpoint and aggregation runs in compiled ns-3 C++. Plots use ns-3's Gnuplot helper and the gnuplot renderer.",
        "A/B adapt paper policies to local distributed routing. A uses watchdog trust; B advertises its own send/receive-counter trust and never revokes nodes. Diversification avoids the previous next hop, not every node on the previous route.",
        "The adversarial AODV baseline shares the custom substrate. Upstream ns3-aodv supports clean runs only.",
        "PDR counts sends in the measurement window and their arrivals through cooldown. Lost ACKs can penalise delivered data. Delay is seconds, energy joules, forecasts watts, throughput bits/s.",
        "GAN/LSTM train only during clean commissioning. An untrained flag means its zero error is a placeholder. LSTM holdouts are disjoint chronological intervals per node; persistence and window mean are baselines.",
        "Lifetime flags identify observed deaths. Unobserved events are censored at the horizon; mixed censored/observed seed means are not lifetime estimates.",
        "The solar/kinetic source is a model with compressed days and an ideal reservoir without a capacity ceiling. First depletion permanently disables the PHY. A ns-3.45 radio callback guard prevents premature model shutdown while the PHY remains active.",
        "X25519/HKDF/AES-GCM adds 28 bytes per protected message. Keys are deterministic simulation fixtures, provisioned before the run. Key-exchange traffic and crypto CPU latency are not injected into simulated time.",
        "Control counters are generated message attempts, including attempts after PHY shutdown, rather than successful radio transmissions. Layer drop counters are not additive end-to-end loss categories.",
        "CMDP multipliers, actions and violations include warmup/cooldown policy activity. An unmet PDR target does not prove mathematical infeasibility. Wall time includes commissioning and is host runtime.",
        "Detection scores nodes flagged by honest witnesses: contested flags require two witnesses; revocations require one. The AUC placeholder is 0.5. A smoke run is an execution check, not evidence of comparative performance."};
    std::ostringstream md, html;
    md << "# AR-EAURP — entirely native ns-3 evaluation\n\nProfile: **" << profile << "**; engine: ns-3.45 C++.\n\nBuild identity: `" << identity << "`.\n\n";
    html << "<!doctype html><meta charset=\"utf-8\"><title>AR-EAURP native evaluation</title><style>body{font:15px system-ui;margin:32px;max-width:1400px}table{border-collapse:collapse;width:100%;margin:16px 0}td,th{padding:8px;border:1px solid #ccc;text-align:left}img{max-width:100%}.table{overflow:auto}code{overflow-wrap:anywhere}</style><h1>AR-EAURP — native ns-3 evaluation</h1><p>Profile: " << profile << "; ns-3.45 C++</p><p>Build: <code>" << identity << "</code></p>";
    if (profile == "smoke")
    { md << "These short single-seed runs validate execution only.\n\n";
      html << "<p><strong>These short single-seed runs validate execution only.</strong></p>"; }
    std::vector<std::string> figures;
    auto plot = [&](const std::string& name, const std::vector<ExperimentRow>& rows, const std::string& metric,
                    const std::string& ylabel, const std::string& xkey = "") {
        if (rows.empty()) return;
        const std::string basename = name + "_" + metric;
        Gnuplot chart(basename + ".svg", name + " — " + ylabel);
        chart.SetTerminal("svg size 1100,650 noenhanced");
        chart.SetLegend(xkey.empty() ? "Configuration" : xkey == "speed_value" ? "Maximum speed (m/s)" :
                        xkey == "malicious_pct" ? "Malicious nodes (%)" : "Node count", ylabel);
        chart.AppendExtra("set grid; set key outside right; set bmargin 14");
        chart.AppendExtra(metric == "pdr" || metric == "detect_tpr" || metric == "detect_fpr" ?
                          "set yrange [0:1]" : "set yrange [0:*]");
        std::map<std::string, Gnuplot2dDataset> series;
        std::ostringstream ticks; ticks << "set xtics rotate by -45 ("; unsigned index = 0, points = 0;
        for (const auto& row : rows)
        {
            ++index;
            if (index > 1) ticks << ',';
            ticks << '\'' << TickLabel(row.label) << "' " << index;
            if (metric == "first_death_s" && Value(row, "first_death_observed") != 1) continue;
            if (metric.find("mae_w") != std::string::npos && Value(row, "lstm_trained") != 1) continue;
            const auto group = xkey.empty() ? metric : row.policy;
            auto [entry, inserted] = series.emplace(group, Gnuplot2dDataset(group));
            if (inserted) { entry->second.SetStyle(Gnuplot2dDataset::LINES_POINTS); entry->second.SetErrorBars(Gnuplot2dDataset::Y); }
            const double x = xkey.empty() ? index : std::stod(row.metadata.at(xkey));
            const auto measured = (metric == "detect_tpr" || metric == "detect_fpr") && row.protocol != "ar-eaurp" ?
                std::string("revoke_") + metric.substr(7) : metric;
            entry->second.Add(x, Value(row, measured), Value(row, measured + "_std")); ++points;
        }
        if (!points) return;
        ticks << ')'; if (xkey.empty()) chart.AppendExtra(ticks.str());
        for (const auto& [name, data] : series) { (void)name; chart.AddDataset(data); }
        fs::create_directories(root / "figures");
        std::ofstream output(root / "figures" / (basename + ".gp")); chart.GenerateOutput(output); output.close();
        if (!output) throw std::runtime_error("Cannot write plot script");
        if (render)
        {
            const std::string command = "cd " + ShellQuote(fs::absolute(root / "figures").string()) + " && gnuplot " + ShellQuote(basename + ".gp");
            if (std::system(command.c_str()) != 0) throw std::runtime_error("gnuplot failed; install gnuplot or use --render=0 to export scripts only");
            figures.push_back(basename);
        }
    };
    auto table = [&](const std::vector<ExperimentRow>& rows, const std::vector<std::pair<std::string, std::string>>& columns) {
        md << "| Configuration"; html << "<div class=\"table\"><table><tr><th>Configuration</th>";
        for (const auto& [key, title] : columns) { (void)key; md << " | " << title; html << "<th>" << Html(title) << "</th>"; }
        md << " |\n|---"; html << "</tr>";
        for (std::size_t i = 0; i < columns.size(); ++i) md << "|---:";
        md << "|\n";
        for (const auto& row : rows)
        {
            std::string label = row.label; std::replace(label.begin(), label.end(), '|', '/');
            md << "| " << label; html << "<tr><td>" << Html(row.label) << "</td>";
            for (const auto& [key, title] : columns)
            {
                (void)title; std::string number = Number(Value(row, key));
                if (key == "first_death_s" || key == "eighty_pct_dead_s")
                {
                    const auto flag = Value(row, key == "first_death_s" ? "first_death_observed" : "eighty_pct_death_observed");
                    if (flag != 1) number = flag == 0 ? "censored" : "mixed observed/censored";
                }
                md << " | " << number; html << "<td>" << number << "</td>";
            }
            md << " |\n"; html << "</tr>";
        }
        md << '\n'; html << "</table></div>";
    };
    for (const auto& [name, rows] : results)
    {
        md << "## " << name << "\n\n"; html << "<h2>" << name << "</h2>";
        table(rows, {{"runs", "Runs"}, {"pdr", "PDR"}, {"pdr_std", "PDR seed SD"}, {"mean_delay_s", "Delay (s)"},
                     {"throughput_bps", "Throughput (bit/s)"}, {"gan_trained", "GAN trained"}, {"lstm_trained", "LSTM trained"}});
        const auto xkey = name == "e1_speed" ? "speed_value" : name == "e2_density" ? "node_count" : "";
        if (name != "e3_attack") plot(name, rows, "pdr", "PDR", xkey);
        if (!std::string(xkey).empty())
            for (const auto& [metric, title] : std::vector<std::pair<std::string, std::string>>{{"mean_delay_s", "Delay (s)"}, {"loss_packets", "Application losses"}, {"throughput_bps", "Throughput (bit/s)"}})
                plot(name, rows, metric, title, xkey);
        if (name == "e3_attack")
        {
            table(rows, {{"detect_tpr", "GAN window TPR"}, {"detect_fpr", "GAN window FPR"}, {"detector_auc", "GAN score AUC"}, {"contested_tpr", "Two-witness contested TPR"}, {"contested_fpr", "Two-witness contested FPR"}, {"revoke_tpr", "Revocation TPR"}, {"revoke_fpr", "Revocation FPR"}, {"detector_windows", "Detector windows"}});
            for (const auto* attack : {"blackhole", "grayhole", "trust_poisoning"})
            {
                std::vector<ExperimentRow> subset;
                for (const auto& row : rows) if (row.attack == attack) subset.push_back(row);
                plot(std::string("e3_") + attack, subset, "pdr", "PDR", "malicious_pct");
                plot(std::string("e3_") + attack, subset, "detect_tpr", "GAN window TPR", "malicious_pct");
                plot(std::string("e3_") + attack, subset, "detect_fpr", "GAN window FPR", "malicious_pct");
                plot(std::string("e3_") + attack + "_consensus", subset, "contested_tpr", "Two-witness contested TPR", "malicious_pct");
            }
        }
        if (name == "e4_energy")
        {
            table(rows, {{"residual_energy_j", "Residual (J)"}, {"harvested_j", "Harvested (J)"}, {"lstm_mae_w", "LSTM MAE (W)"}, {"lstm_persistence_mae_w", "Persistence MAE (W)"}, {"lstm_window_mean_mae_w", "Window mean MAE (W)"}, {"lstm_validation_sequences", "Holdout sequences"}});
            plot(name, rows, "residual_energy_j", "Residual energy (J)"); plot(name, rows, "harvested_j", "Harvested energy (J)");
            plot(name, rows, "lstm_mae_w", "Trained LSTM holdout MAE (W)");
        }
        if (name == "e4b_lifetime")
        { table(rows, {{"first_death_s", "First depletion (s)"}, {"eighty_pct_dead_s", "80% depletion (s)"}, {"lifetime_horizon_s", "Horizon (s)"}}); plot(name, rows, "first_death_s", "Observed first depletion (s)"); }
        if (name == "e5_ablation" || name == "e5b_cmdp_floor")
        {
            table(rows, {{"cfg_pdr_floor", "PDR target"}, {"cmdp_lambda", "Final multiplier"}, {"cmdp_lambda_peak", "Peak multiplier"}, {"cmdp_violations", "Violations"}, {"cmdp_decisions", "Decisions"}, {"cmdp_action_trust", "Trust actions"}, {"cmdp_action_energy_surplus", "Energy actions"}, {"cmdp_action_balanced", "Balanced actions"}, {"cmdp_action_diversified", "Diversified actions"}});
            plot(name, rows, "cmdp_lambda", "Final constraint multiplier");
        }
        if (name == "e6_overhead")
        {
            table(rows, {{"control_packets", "Generated control messages"}, {"wall_clock_seconds", "Wall time (s)"}, {"crypto_packets", "Protected messages"}, {"crypto_overhead_bytes", "Crypto overhead (bytes)"}, {"crypto_auth_failures", "Authentication failures"}});
            plot(name, rows, "control_packets", "Generated control messages"); plot(name, rows, "wall_clock_seconds", "Wall time incl. commissioning (s)"); plot(name, rows, "crypto_overhead_bytes", "Crypto overhead (bytes)");
        }
    }
    md << "## Measurement and modelling limits\n\n"; html << "<h2>Measurement and modelling limits</h2><ul>";
    for (const auto& caveat : caveats) { md << "- " << caveat << '\n'; html << "<li>" << Html(caveat) << "</li>"; }
    md << '\n'; html << "</ul>";
    for (const auto& name : figures)
    { md << "![" << name << "](<" << fs::absolute(root / "figures" / (name + ".svg")).string() << ">)\n\n";
      html << "<p><img alt=\"" << name << "\" src=\"figures/" << name << ".svg\"></p>"; }
    if (!render) { md << "Gnuplot scripts were exported; figures have not been rendered.\n"; html << "<p>Gnuplot scripts exported; figures have not been rendered.</p>"; }
    auto markdown = md.str();
    while (markdown.size() > 1 && markdown.substr(markdown.size() - 2) == "\n\n") markdown.pop_back();
    WriteAtomic(root / "report.md", markdown); WriteAtomic(root / "report.html", html.str());
}

void ExportNotebooks(const fs::path& project)
{
    // Use ordinary tar/base64 tools to package source. Execution and report
    // generation stay in C++; notebook cells only build/launch native binaries.
    const std::string command = "cd " + ShellQuote(project.string()) +
        " && tar --exclude=__pycache__ --exclude='*.o' -czf - ns3 README.md | base64";
    const std::string checked = "bash -o pipefail -c " + ShellQuote(command);
    FILE* pipe = popen(checked.c_str(), "r");
    if (!pipe) throw std::runtime_error("Cannot package notebook source");
    std::string encoded; char buffer[8192];
    while (fgets(buffer, sizeof buffer, pipe)) encoded += buffer;
    if (pclose(pipe) != 0 || encoded.empty()) throw std::runtime_error("Cannot package notebook source");
    std::vector<std::string> markdown{
        "# AR-EAURP — entirely native ns-3.45\n\nExperiment selection, repeated runs, checkpointing, seed aggregation, learning, reporting and plot-script generation execute in C++. Cells run Bash only. A CPU runtime and internet are required. `smoke` verifies execution; `quick` and `full` have larger research budgets. SVGs are rendered by gnuplot. The upstream ns-3 build keeps its own standard dependencies.",
        "A private repository can use the embedded-source notebook without GitHub credentials. Upload REVIEW2_AR_EAURP.ipynb to Colab. Native raw checkpoints can be preserved by choosing an output directory on an already mounted Drive. Smoke results do not justify performance claims."};
    auto notebook = [&](bool embedded) {
        std::vector<std::pair<std::string, std::string>> cells{{"markdown", markdown[0]}};
        std::string restore = "%%bash\nset -euo pipefail\n";
        if (embedded)
            restore += "mkdir -p /content/AR-EAURP-CN-Project\nbase64 -d <<'AR_EAURP_SOURCE' | tar -xzf - -C /content/AR-EAURP-CN-Project\n" + encoded + "AR_EAURP_SOURCE\n";
        else
            restore += "if [[ ! -d /content/AR-EAURP-CN-Project/.git ]]; then\n  git clone --depth=1 https://github.com/Abhi-R459/AR-EAURP-CN-Project.git /content/AR-EAURP-CN-Project || { echo 'For a private repository, upload the embedded-source notebook.' >&2; exit 2; }\nfi\n";
        cells.push_back({"code", restore});
        cells.push_back({"code", "%%bash\nset -euo pipefail\napt-get update -qq\napt-get install -y -qq build-essential cmake pkg-config libssl-dev curl gnuplot-nox\ncd /content/AR-EAURP-CN-Project\nbash ns3/scripts/setup.sh --home /content/ns-3.45 --download\n"});
        cells.push_back({"code", "%%bash\nset -euo pipefail\nexport NS3_HOME=/content/ns-3.45\ncd /content/AR-EAURP-CN-Project\n\"$NS3_HOME/build/utils/ns3.45-test-runner-optimized\" --suite=ar-eaurp --verbose\nbash ns3/scripts/run.sh --verify=1\n"});
        cells.push_back({"code", "%%bash\nset -euo pipefail\nexport NS3_HOME=/content/ns-3.45\ncd /content/AR-EAURP-CN-Project\nPROFILE=smoke # smoke / quick / full\n# Set OUT_DIR to an already mounted Drive folder for persistence.\nOUT_DIR=\"results/ns3-native-$PROFILE\"\nbash ns3/scripts/run.sh --profile=\"$PROFILE\" --out=\"$OUT_DIR\"\n# Rerun this cell to resume; --fresh=1 recomputes matching checkpoints.\n"});
        cells.push_back({"markdown", "Open the generated report.html and figures/ SVGs in Colab's Files panel, or download the result folder. CSVs and raw per-seed checkpoints are also saved. No project Python code runs in these cells. An actual Colab run has not been verified by notebook generation."});
        cells.push_back({"markdown", markdown[1]});
        std::ostringstream out;
        out << "{\"nbformat\":4,\"nbformat_minor\":5,\"metadata\":{\"kernelspec\":{\"display_name\":\"Python 3\",\"language\":\"python\",\"name\":\"python3\"}},\"cells\":[";
        unsigned i = 0;
        for (const auto& [type, source] : cells)
        {
            if (i) out << ',';
            out << "{\"id\":\"native-" << i++ << "\",\"cell_type\":" << JsonQuote(type) << ",\"metadata\":{},\"source\":" << JsonQuote(source);
            if (type == "code") out << ",\"execution_count\":null,\"outputs\":[]";
            out << '}';
        }
        out << "]}\n"; return out.str();
    };
    WriteAtomic(project / "colab/REVIEW2_AR_EAURP.ipynb", notebook(true));
    WriteAtomic(project / "colab/REVIEW2_FROM_GITHUB.ipynb", notebook(false));
    std::cout << "Generated shell-only embedded-source and GitHub Colab notebooks\n";
}
}
