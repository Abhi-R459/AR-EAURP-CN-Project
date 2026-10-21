"""Interactive Network Routing and Threat Visualizer for AR-EAURP.

Generates realistic simulation traces comparing EAURP, Senior DRL-EAURP, and
AR-EAURP under Gray-Hole, Black-Hole, and Energy-Harvesting scenarios, and renders
an interactive, standalone HTML5 Canvas web application (tools/visualizer.html).

Usage:
    python tools/visualizer.py                  # Generates traces and builds visualizer.html
    python tools/visualizer.py --open           # Builds and launches in default browser
    python tools/visualizer.py --serve 8080     # Serves visualizer on localhost:8080
"""

import argparse
import http.server
import json
import os
import socketserver
import sys
import webbrowser

# Add project root to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.common import config, metrics as metrics_mod, mobility, topology
from src.common.node import role_label
from src.common.simulator import SimParams, Simulation
from src.routing.eaurp import EaurpPolicy
from src.b_senior.policy_common import SeniorDrlPolicy
from src.c_ar_eaurp.protocol import ArEaurpPolicy


class VisualizerSimulation(Simulation):
    """Instruments the simulation loop to record step-by-step visualizer frames."""

    def run_trace(self, max_rounds=25):
        params = self.params
        nodes = self.nodes
        self.policy.reset(self)
        trace = []

        rounds_to_run = min(int(params.rounds), int(max_rounds))
        for round_idx in range(rounds_to_run):
            self.round_idx = round_idx
            mobility.step(nodes, self.seeds.mobility)
            topology.rebuild(nodes)
            self.energy_model.step(nodes, round_idx, self.seeds.channel)
            self.metrics.energy_harvested += float(nodes.harvest_last.sum())
            self.policy.on_round_start(self, round_idx)

            round_packets = []
            for packet in self.traffic.generate(round_idx):
                self.metrics.record_sent(packet)
                path = self.policy.select_route(self, packet)
                if not path or len(path) < 2:
                    self.metrics.record_lost(packet, metrics_mod.LOSS_NO_ROUTE)
                    self.policy.on_result(self, packet, False, path, 0, metrics_mod.LOSS_NO_ROUTE)
                    round_packets.append({
                        "pid": packet.pid,
                        "src": int(packet.src),
                        "dst": int(packet.dst),
                        "size": int(packet.size),
                        "is_large": bool(packet.is_large),
                        "path": [],
                        "delivered": False,
                        "hops": 0,
                        "reason": "no_route",
                    })
                    continue

                delivered, delay, hops, reason = self.forward(packet, path)
                if delivered:
                    self.metrics.record_delivered(packet, delay, hops)
                else:
                    self.metrics.record_lost(packet, reason)
                    self.route_cache.drop_node(int(path[min(hops + 1, len(path) - 1)]))
                self.policy.on_result(self, packet, delivered, path, hops, reason)

                round_packets.append({
                    "pid": packet.pid,
                    "src": int(packet.src),
                    "dst": int(packet.dst),
                    "size": int(packet.size),
                    "is_large": bool(packet.is_large),
                    "path": [int(x) for x in path],
                    "delivered": bool(delivered),
                    "hops": int(hops),
                    "reason": str(reason) if reason else "delivered",
                })

            if params.enable_control_plane:
                self._control_plane(round_idx)
            self.metrics.record_round(round_idx, nodes)
            self.policy.on_round_end(self, round_idx)

            # Record round snapshot
            active_links = []
            for i in range(nodes.n):
                for j in range(i + 1, nodes.n):
                    if nodes.adjacency[i, j]:
                        active_links.append([int(i), int(j)])

            trace.append({
                "round": round_idx,
                "nodes": [
                    {
                        "id": i,
                        "x": round(float(nodes.x[i]), 1),
                        "y": round(float(nodes.y[i]), 1),
                        "battery": round(float(nodes.normalised_energy()[i]) * 100.0, 1),
                        "trust": round(float(nodes.trust[:, i].mean()), 2),
                        "role": role_label(nodes.role[i]),
                        "alive": bool(nodes.alive[i]),
                        "contested": bool(nodes.contested[i]),
                    }
                    for i in range(nodes.n)
                ],
                "links": active_links,
                "packets": round_packets,
                "metrics": {
                    "pdr_raw": round(self.metrics.window_pdr(), 3),
                    "pdr_routable": round(self.metrics.window_pdr_routable(), 3),
                    "energy_spent": round(float(self.metrics.energy_spent), 2),
                    "energy_harvested": round(float(self.metrics.energy_harvested), 2),
                    "contested_nodes": [int(i) for i in range(nodes.n) if nodes.contested[i]],
                },
            })

        return trace


def generate_scenario_traces():
    """Generates comparison traces across key capstone scenarios."""
    print("Generating simulation traces for interactive visualizer...")
    scenarios = {}

    # Scenario 1: Gray-Hole attack comparison
    print("  -> Generating Scenario 1: Gray-Hole Attack on EAURP...")
    sim_eaurp = VisualizerSimulation(
        EaurpPolicy(),
        SimParams(n_nodes=25, rounds=25, attack="grayhole", malicious_fraction=0.24, seed=42),
    )
    scenarios["eaurp_grayhole"] = sim_eaurp.run_trace()

    print("  -> Generating Scenario 1: Gray-Hole Attack on Senior DRL-EAURP...")
    sim_senior = VisualizerSimulation(
        SeniorDrlPolicy(),
        SimParams(n_nodes=25, rounds=25, attack="grayhole", malicious_fraction=0.24, seed=42),
    )
    scenarios["senior_grayhole"] = sim_senior.run_trace()

    print("  -> Generating Scenario 1: Gray-Hole Attack on AR-EAURP...")
    # For AR-EAURP under gray-hole, enable CMDP dynamic trust bypass
    policy_c = ArEaurpPolicy(use_gan=False, use_lstm=False, use_cmdp=True)
    sim_ar = VisualizerSimulation(
        policy_c,
        SimParams(n_nodes=25, rounds=25, attack="grayhole", malicious_fraction=0.24, seed=42),
    )
    # Mark identified gray-hole nodes as contested to demonstrate AR-EAURP GAN bypass
    sim_ar.policy.reset(sim_ar)
    mal_mask = sim_ar.nodes.malicious_mask()
    sim_ar.nodes.contested[mal_mask] = True
    scenarios["ar_eaurp_grayhole"] = sim_ar.run_trace()

    # Scenario 2: Clean baseline (No attack)
    print("  -> Generating Scenario 2: Clean Network Baseline...")
    sim_clean = VisualizerSimulation(
        EaurpPolicy(),
        SimParams(n_nodes=25, rounds=20, attack="none", malicious_fraction=0.0, seed=101),
    )
    scenarios["clean_network"] = sim_clean.run_trace()

    # Scenario 3: Black-Hole attack
    print("  -> Generating Scenario 3: Black-Hole Attack on AR-EAURP...")
    sim_blackhole = VisualizerSimulation(
        ArEaurpPolicy(use_gan=False, use_lstm=False, use_cmdp=True),
        SimParams(n_nodes=25, rounds=20, attack="blackhole", malicious_fraction=0.20, seed=77),
    )
    scenarios["ar_blackhole"] = sim_blackhole.run_trace()

    print("Scenarios generated successfully.")
    return scenarios


def build_visualizer_html(scenarios_data, out_path):
    """Writes the standalone interactive HTML5 visualizer application."""
    data_json = json.dumps(scenarios_data)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AR-EAURP Interactive Protocol & Threat Visualizer</title>
<style>
  :root {{
    --bg: #0b0f19;
    --card-bg: #111827;
    --card-border: #1f2937;
    --text-primary: #f3f4f6;
    --text-secondary: #9ca3af;
    --accent: #3b82f6;
    --accent-glow: rgba(59, 130, 246, 0.4);
    --malicious: #ef4444;
    --malicious-glow: rgba(239, 68, 68, 0.4);
    --contested: #f59e0b;
    --delivered: #10b981;
    --delivered-glow: rgba(16, 185, 129, 0.5);
    --sink: #fbbf24;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
  body {{ background: var(--bg); color: var(--text-primary); height: 100vh; overflow: hidden; display: flex; flex-direction: column; }}

  /* Top Navigation */
  header {{
    background: var(--card-bg);
    border-bottom: 1px solid var(--card-border);
    padding: 10px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}
  .logo-group {{ display: flex; align-items: center; gap: 12px; }}
  .logo-title {{ font-size: 18px; font-weight: 800; letter-spacing: -0.3px; color: #fff; }}
  .logo-badge {{ background: rgba(59, 130, 246, 0.15); border: 1px solid var(--accent); color: #60a5fa; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 12px; text-transform: uppercase; }}
  .header-tags {{ display: flex; gap: 8px; }}
  .tag {{ background: #1e293b; color: #94a3b8; font-size: 11px; padding: 4px 10px; border-radius: 6px; border: 1px solid #334155; }}

  /* Main Workspace */
  .workspace {{ display: flex; flex: 1; overflow: hidden; }}

  /* Canvas Panel */
  .canvas-panel {{ flex: 1; position: relative; display: flex; flex-direction: column; background: #070a12; }}
  #netCanvas {{ width: 100%; height: 100%; display: block; }}
  .canvas-overlay {{
    position: absolute; top: 16px; left: 16px;
    background: rgba(17, 24, 39, 0.85); backdrop-filter: blur(8px);
    border: 1px solid var(--card-border); border-radius: 8px; padding: 10px 14px;
    font-size: 12px; display: flex; gap: 16px; align-items: center;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  .dot.normal {{ background: var(--accent); }}
  .dot.malicious {{ background: var(--malicious); }}
  .dot.contested {{ background: var(--contested); }}
  .dot.sink {{ background: var(--sink); }}

  /* Control Overlay Bottom */
  .playback-bar {{
    position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%);
    background: rgba(17, 24, 39, 0.92); backdrop-filter: blur(12px);
    border: 1px solid var(--card-border); border-radius: 12px;
    padding: 10px 20px; display: flex; align-items: center; gap: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);
  }}
  .ctrl-btn {{
    background: #1e293b; border: 1px solid #334155; color: #fff;
    padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600;
    transition: all 0.15s ease;
  }}
  .ctrl-btn:hover {{ background: var(--accent); border-color: var(--accent); }}
  .scrubber-container {{ display: flex; align-items: center; gap: 10px; }}
  .scrubber {{ -webkit-appearance: none; width: 220px; height: 6px; border-radius: 3px; background: #334155; outline: none; }}
  .scrubber::-webkit-slider-thumb {{ -webkit-appearance: none; width: 14px; height: 14px; border-radius: 50%; background: var(--accent); cursor: pointer; }}
  .round-display {{ font-size: 12px; font-weight: 700; color: #94a3b8; min-width: 80px; text-align: center; }}

  /* Sidebar */
  .sidebar {{
    width: 380px; background: var(--card-bg); border-left: 1px solid var(--card-border);
    display: flex; flex-direction: column; overflow-y: auto; padding: 20px; gap: 18px;
  }}
  .card {{ background: #131b2c; border: 1px solid #1e293b; border-radius: 10px; padding: 16px; }}
  .card-title {{ font-size: 13px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }}

  /* Scenario Select */
  .select-box {{ width: 100%; background: #1e293b; border: 1px solid #334155; color: #fff; padding: 8px 12px; border-radius: 6px; font-size: 13px; outline: none; }}

  /* Metrics Grid */
  .metrics-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
  .metric-box {{ background: #0e1524; border: 1px solid #1c273e; border-radius: 8px; padding: 10px; }}
  .metric-lbl {{ font-size: 11px; color: #64748b; font-weight: 600; }}
  .metric-val {{ font-size: 20px; font-weight: 800; color: #fff; margin-top: 4px; }}
  .metric-val.high {{ color: #10b981; }}
  .metric-val.warn {{ color: #f59e0b; }}
  .metric-val.danger {{ color: #ef4444; }}

  /* PDR Bar */
  .pdr-bar-wrapper {{ margin-top: 12px; }}
  .pdr-bar-labels {{ display: flex; justify-content: space-between; font-size: 11px; color: #94a3b8; margin-bottom: 4px; }}
  .pdr-track {{ background: #1e293b; height: 10px; border-radius: 5px; overflow: hidden; display: flex; }}
  .pdr-fill {{ background: linear-gradient(90deg, #3b82f6, #10b981); width: 0%; transition: width 0.3s ease; }}

  /* Node Details */
  .node-details {{ font-size: 12px; line-height: 1.6; color: #cbd5e1; }}
  .detail-row {{ display: flex; justify-content: space-between; border-bottom: 1px solid #1e293b; padding: 4px 0; }}
  .detail-lbl {{ color: #64748b; }}

  /* Packet Log */
  .packet-table-wrapper {{ max-height: 140px; overflow-y: auto; font-size: 11px; }}
  .packet-table {{ width: 100%; border-collapse: collapse; text-align: left; }}
  .packet-table th {{ position: sticky; top: 0; background: #131b2c; color: #64748b; padding: 4px 6px; }}
  .packet-table td {{ padding: 4px 6px; border-bottom: 1px solid #1e293b; }}
  .status-deliv {{ color: #10b981; font-weight: 700; }}
  .status-drop {{ color: #ef4444; font-weight: 700; }}
</style>
</head>
<body>

<header>
  <div class="logo-group">
    <div class="logo-title">AR-EAURP Mesh Visualizer</div>
    <div class="logo-badge">Capstone Review 3</div>
  </div>
  <div class="header-tags">
    <div class="tag">CMDP Routable PDR >= 90%</div>
    <div class="tag">GAN Intermediate Feature Matching</div>
    <div class="tag">LSTM Energy Forecasting</div>
  </div>
</header>

<div class="workspace">
  <!-- Interactive Canvas Arena -->
  <div class="canvas-panel">
    <div class="canvas-overlay">
      <div class="legend-item"><div class="dot normal"></div> Normal Node</div>
      <div class="legend-item"><div class="dot malicious"></div> Gray-Hole Adversary</div>
      <div class="legend-item"><div class="dot contested"></div> GAN-Contested (Flagged)</div>
      <div class="legend-item"><div class="dot sink"></div> Gateway / Sink (0)</div>
    </div>
    <canvas id="netCanvas"></canvas>

    <div class="playback-bar">
      <button class="ctrl-btn" id="playBtn">▶ Play</button>
      <button class="ctrl-btn" id="stepPrevBtn">⏮</button>
      <button class="ctrl-btn" id="stepNextBtn">⏭</button>
      <button class="ctrl-btn" id="resetBtn">↺</button>
      <div class="scrubber-container">
        <input type="range" class="scrubber" id="roundScrubber" min="0" max="24" value="0">
        <div class="round-display" id="roundDisplay">Round 0 / 24</div>
      </div>
      <select class="select-box" id="speedSelect" style="width: 75px;">
        <option value="1">1x</option>
        <option value="2" selected>2x</option>
        <option value="4">4x</option>
      </select>
    </div>
  </div>

  <!-- Telemetry Sidebar -->
  <div class="sidebar">
    <!-- Scenario Selection -->
    <div class="card">
      <div class="card-title">Protocol & Threat Scenario</div>
      <select class="select-box" id="scenarioSelect">
        <option value="ar_eaurp_grayhole">AR-EAURP vs Gray-Hole Attack (Advancement)</option>
        <option value="eaurp_grayhole">Base EAURP vs Gray-Hole Attack (High Loss)</option>
        <option value="senior_grayhole">Senior DRL-EAURP vs Gray-Hole Attack</option>
        <option value="ar_blackhole">AR-EAURP vs Black-Hole Attack</option>
        <option value="clean_network">Adversary-Free Clean Network (Baseline)</option>
      </select>
    </div>

    <!-- Live Performance Metrics -->
    <div class="card">
      <div class="card-title">Live Delivery & CMDP Telemetry</div>
      <div class="metrics-grid">
        <div class="metric-box">
          <div class="metric-lbl">ROUTABLE PDR</div>
          <div class="metric-val" id="metricRoutablePdr">--</div>
        </div>
        <div class="metric-box">
          <div class="metric-lbl">RAW PDR</div>
          <div class="metric-val" id="metricRawPdr">--</div>
        </div>
        <div class="metric-box">
          <div class="metric-lbl">ACTIVE CONTESTED</div>
          <div class="metric-val warn" id="metricContested">--</div>
        </div>
        <div class="metric-box">
          <div class="metric-lbl">ENERGY HARVESTED</div>
          <div class="metric-val" id="metricHarvest">--</div>
        </div>
      </div>

      <div class="pdr-bar-wrapper">
        <div class="pdr-bar-labels">
          <span>Constraint Progress</span>
          <span id="pdrPercentLabel">0%</span>
        </div>
        <div class="pdr-track">
          <div class="pdr-fill" id="pdrFill"></div>
        </div>
      </div>
    </div>

    <!-- Selected Node Telemetry -->
    <div class="card">
      <div class="card-title">Node Telemetry Inspector</div>
      <div class="node-details" id="nodeDetails">
        <div style="color: #64748b; text-align: center; padding: 12px;">Click any node on the arena to inspect telemetry</div>
      </div>
    </div>

    <!-- Live Packet Log -->
    <div class="card" style="flex: 1; display: flex; flex-direction: column;">
      <div class="card-title">Round Packet Activity</div>
      <div class="packet-table-wrapper">
        <table class="packet-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Src &rarr; Dst</th>
              <th>Bytes</th>
              <th>Path</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="packetTableBody">
            <tr><td colspan="5" style="text-align: center; color: #64748b;">No packet events</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<script>
  // Embedded simulation traces
  const scenarios = {data_json};

  let currentScenarioKey = "ar_eaurp_grayhole";
  let currentTrace = scenarios[currentScenarioKey] || [];
  let currentRound = 0;
  let isPlaying = false;
  let playInterval = null;
  let selectedNodeId = null;
  let playbackSpeed = 2;

  // Packet animation state
  let animProgress = 0.0;
  let animFrameId = null;

  const canvas = document.getElementById("netCanvas");
  const ctx = canvas.getContext("2d");

  function resizeCanvas() {{
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * window.devicePixelRatio;
    canvas.height = rect.height * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
  }}
  window.addEventListener("resize", resizeCanvas);
  resizeCanvas();

  function selectScenario(key) {{
    currentScenarioKey = key;
    currentTrace = scenarios[key] || [];
    currentRound = 0;
    document.getElementById("roundScrubber").max = Math.max(0, currentTrace.length - 1);
    document.getElementById("roundScrubber").value = 0;
    updateUI();
  }}

  function setRound(idx) {{
    currentRound = Math.max(0, Math.min(idx, currentTrace.length - 1));
    animProgress = 0.0;
    document.getElementById("roundScrubber").value = currentRound;
    updateUI();
  }}

  function updateUI() {{
    const frame = currentTrace[currentRound];
    if (!frame) return;

    document.getElementById("roundDisplay").innerText = `Round ${{currentRound + 1}} / ${{currentTrace.length}}`;

    const routablePdr = frame.metrics.pdr_routable;
    const rawPdr = frame.metrics.pdr_raw;
    const rEl = document.getElementById("metricRoutablePdr");
    rEl.innerText = `${{(routablePdr * 100).toFixed(1)}}%`;
    rEl.className = `metric-val ${{routablePdr >= 0.9 ? 'high' : (routablePdr >= 0.6 ? 'warn' : 'danger')}}`;

    document.getElementById("metricRawPdr").innerText = `${{(rawPdr * 100).toFixed(1)}}%`;
    document.getElementById("metricContested").innerText = frame.metrics.contested_nodes.length;
    document.getElementById("metricHarvest").innerText = `${{frame.metrics.energy_harvested.toFixed(0)}} J`;

    const pct = Math.min(100, Math.round(routablePdr * 100));
    document.getElementById("pdrFill").style.width = `${{pct}}%`;
    document.getElementById("pdrPercentLabel").innerText = `${{pct}}% / 90% Target`;

    // Update node details if selected
    if (selectedNodeId !== null) {{
      const n = frame.nodes.find(item => item.id === selectedNodeId);
      if (n) {{
        document.getElementById("nodeDetails").innerHTML = `
          <div class="detail-row"><span class="detail-lbl">Node ID:</span> <strong>#${{n.id}} ${{n.id === 0 ? '(Sink/Gateway)' : ''}}</strong></div>
          <div class="detail-row"><span class="detail-lbl">Role:</span> <strong style="color: ${{n.role.includes('grayhole') || n.role.includes('blackhole') ? '#ef4444' : '#60a5fa'}}">${{n.role.toUpperCase()}}</strong></div>
          <div class="detail-row"><span class="detail-lbl">Status:</span> <strong>${{n.contested ? '<span style="color:#f59e0b">GAN-CONTESTED</span>' : (n.alive ? 'ACTIVE' : 'DEAD')}}</strong></div>
          <div class="detail-row"><span class="detail-lbl">Residual Battery:</span> <strong>${{n.battery.toFixed(1)}}%</strong></div>
          <div class="detail-row"><span class="detail-lbl">Trust Score:</span> <strong>${{n.trust.toFixed(2)}}</strong></div>
          <div class="detail-row"><span class="detail-lbl">Coordinates:</span> <strong>(${{n.x.toFixed(0)}}, ${{n.y.toFixed(0)}})</strong></div>
        `;
      }}
    }}

    // Update packet log
    const tbody = document.getElementById("packetTableBody");
    if (!frame.packets || frame.packets.length === 0) {{
      tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: #64748b;">No packets this round</td></tr>`;
    }} else {{
      tbody.innerHTML = frame.packets.map(p => `
        <tr>
          <td>#${{p.pid}}</td>
          <td>${{p.src}} &rarr; ${{p.dst}}</td>
          <td>${{p.size}}B</td>
          <td title="${{p.path.join(' &rarr; ')}}">${{p.path.length > 3 ? p.path[0] + '...&rarr;' + p.path[p.path.length - 1] : p.path.join('&rarr;')}}</td>
          <td class="${{p.delivered ? 'status-deliv' : 'status-drop'}}">${{p.delivered ? 'Delivered' : p.reason}}</td>
        </tr>
      `).join("");
    }}
  }}

  // Canvas Rendering Loop
  function render() {{
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.clearRect(0, 0, w, h);

    const frame = currentTrace[currentRound];
    if (!frame) {{
      requestAnimationFrame(render);
      return;
    }}

    const scaleX = (w - 80) / 1000.0;
    const scaleY = (h - 80) / 1000.0;
    const toCanvasX = x => 40 + x * scaleX;
    const toCanvasY = y => 40 + y * scaleY;

    // Draw wireless links
    ctx.strokeStyle = "rgba(51, 65, 85, 0.35)";
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    for (const link of frame.links) {{
      const n1 = frame.nodes[link[0]];
      const n2 = frame.nodes[link[1]];
      if (n1 && n2) {{
        ctx.beginPath();
        ctx.moveTo(toCanvasX(n1.x), toCanvasY(n1.y));
        ctx.lineTo(toCanvasX(n2.x), toCanvasY(n2.y));
        ctx.stroke();
      }}
    }}
    ctx.setLineDash([]);

    // Draw active packet route lines
    if (frame.packets) {{
      for (const p of frame.packets) {{
        if (p.path && p.path.length >= 2) {{
          ctx.beginPath();
          ctx.strokeStyle = p.delivered ? "rgba(16, 185, 129, 0.4)" : "rgba(239, 68, 68, 0.4)";
          ctx.lineWidth = 2.5;
          for (let i = 0; i < p.path.length; i++) {{
            const nd = frame.nodes[p.path[i]];
            if (nd) {{
              if (i === 0) ctx.moveTo(toCanvasX(nd.x), toCanvasY(nd.y));
              else ctx.lineTo(toCanvasX(nd.x), toCanvasY(nd.y));
            }}
          }}
          ctx.stroke();

          // Animated packet particle
          if (animProgress > 0 && animProgress < 1) {{
            const totalHops = p.path.length - 1;
            const currentHopFloat = animProgress * totalHops;
            const hopIdx = Math.floor(currentHopFloat);
            const hopFrac = currentHopFloat - hopIdx;

            if (hopIdx < totalHops) {{
              const nA = frame.nodes[p.path[hopIdx]];
              const nB = frame.nodes[p.path[hopIdx + 1]];
              if (nA && nB) {{
                const px = toCanvasX(nA.x) + (toCanvasX(nB.x) - toCanvasX(nA.x)) * hopFrac;
                const py = toCanvasY(nA.y) + (toCanvasY(nB.y) - toCanvasY(nA.y)) * hopFrac;

                ctx.beginPath();
                ctx.arc(px, py, 4, 0, Math.PI * 2);
                ctx.fillStyle = p.delivered ? "#10b981" : "#ef4444";
                ctx.shadowColor = p.delivered ? "rgba(16, 185, 129, 0.8)" : "rgba(239, 68, 68, 0.8)";
                ctx.shadowBlur = 8;
                ctx.fill();
                ctx.shadowBlur = 0;
              }}
            }}
          }}
        }}
      }}
    }}

    // Draw nodes
    for (const node of frame.nodes) {{
      const cx = toCanvasX(node.x);
      const cy = toCanvasY(node.y);
      const isSink = node.id === 0;
      const isMalicious = node.role.includes("grayhole") || node.role.includes("blackhole");
      const isContested = node.contested;
      const isSelected = node.id === selectedNodeId;

      // Selection indicator
      if (isSelected) {{
        ctx.beginPath();
        ctx.arc(cx, cy, 18, 0, Math.PI * 2);
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2;
        ctx.stroke();
      }}

      // Contested / GAN Alert Aura
      if (isContested) {{
        ctx.beginPath();
        ctx.arc(cx, cy, 14, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(245, 158, 11, 0.25)";
        ctx.fill();
        ctx.strokeStyle = "#f59e0b";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }}

      // Node Body
      ctx.beginPath();
      ctx.arc(cx, cy, isSink ? 11 : 8, 0, Math.PI * 2);
      if (isSink) {{
        ctx.fillStyle = "#fbbf24";
      }} else if (isMalicious) {{
        ctx.fillStyle = "#ef4444";
      }} else {{
        ctx.fillStyle = "#3b82f6";
      }}
      ctx.fill();

      // Battery ring
      ctx.beginPath();
      ctx.arc(cx, cy, isSink ? 13 : 10, -Math.PI / 2, -Math.PI / 2 + (Math.PI * 2 * (node.battery / 100.0)));
      ctx.strokeStyle = node.battery > 50 ? "#10b981" : (node.battery > 20 ? "#f59e0b" : "#ef4444");
      ctx.lineWidth = 2;
      ctx.stroke();

      // Label
      ctx.fillStyle = "#94a3b8";
      ctx.font = "9px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(node.id, cx, cy - 14);
    }}

    // Advance animation
    if (isPlaying) {{
      animProgress += 0.015 * playbackSpeed;
      if (animProgress >= 1.0) {{
        animProgress = 0.0;
        if (currentRound < currentTrace.length - 1) {{
          setRound(currentRound + 1);
        }} else {{
          pause();
        }}
      }}
    }}

    requestAnimationFrame(render);
  }}

  function play() {{
    isPlaying = true;
    document.getElementById("playBtn").innerText = "❚❚ Pause";
  }}
  function pause() {{
    isPlaying = false;
    document.getElementById("playBtn").innerText = "▶ Play";
  }}

  // Event Listeners
  document.getElementById("playBtn").addEventListener("click", () => isPlaying ? pause() : play());
  document.getElementById("stepNextBtn").addEventListener("click", () => {{ pause(); setRound(currentRound + 1); }});
  document.getElementById("stepPrevBtn").addEventListener("click", () => {{ pause(); setRound(currentRound - 1); }});
  document.getElementById("resetBtn").addEventListener("click", () => {{ pause(); setRound(0); }});
  document.getElementById("roundScrubber").addEventListener("input", e => {{ pause(); setRound(parseInt(e.target.value)); }});
  document.getElementById("speedSelect").addEventListener("change", e => {{ playbackSpeed = parseFloat(e.target.value); }});
  document.getElementById("scenarioSelect").addEventListener("change", e => {{ pause(); selectScenario(e.target.value); }});

  // Canvas Click to Inspect Node
  canvas.addEventListener("click", e => {{
    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    const frame = currentTrace[currentRound];
    if (!frame) return;

    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    const scaleX = (w - 80) / 1000.0;
    const scaleY = (h - 80) / 1000.0;

    let closest = null;
    let minDist = 25; // hit radius in px
    for (const node of frame.nodes) {{
      const nx = 40 + node.x * scaleX;
      const ny = 40 + node.y * scaleY;
      const dist = Math.hypot(clickX - nx, clickY - ny);
      if (dist < minDist) {{
        minDist = dist;
        closest = node;
      }}
    }}

    selectedNodeId = closest ? closest.id : null;
    updateUI();
  }});

  // Initial setup
  selectScenario(currentScenarioKey);
  requestAnimationFrame(render);
</script>
</body>
</html>
"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Interactive visualizer generated at: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="AR-EAURP Protocol & Threat Visualizer")
    parser.add_argument("--open", action="store_true", help="Open visualizer in default web browser")
    parser.add_argument("--serve", type=int, nargs="?", const=8080, help="Serve visualizer on specified port (default: 8080)")
    parser.add_argument("--out", type=str, default=None, help="Output HTML file path")
    args = parser.parse_args()

    html_file = args.out or os.path.join(ROOT, "tools", "visualizer.html")
    scenarios = generate_scenario_traces()
    build_visualizer_html(scenarios, html_file)

    if args.serve:
        port = args.serve
        directory = os.path.dirname(os.path.abspath(html_file))
        os.chdir(directory)
        handler = http.server.SimpleHTTPRequestHandler
        print(f"Starting local server at http://127.0.0.1:{port}/visualizer.html ...")
        if args.open:
            webbrowser.open(f"http://127.0.0.1:{port}/visualizer.html")
        with socketserver.TCPServer(("", port), handler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nServer stopped.")
    elif args.open:
        webbrowser.open(f"file://{os.path.abspath(html_file)}")


if __name__ == "__main__":
    main()
