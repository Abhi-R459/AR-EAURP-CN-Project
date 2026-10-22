"""Local, read-only web UI plus a relay for genuine ns-3 NetAnim XML elements.

Python launches the compiled simulator and forwards its trace. It does not
simulate mobility, packets, energy, attacks, or routing.
"""

from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
from urllib.parse import parse_qs, urlsplit


PROJECT = Path(__file__).resolve().parents[2]
STATIC = {
    "/": PROJECT / "ns3_netanim_viewer.html",
    "/ns3_netanim_viewer.html": PROJECT / "ns3_netanim_viewer.html",
    "/ns3/netanim/trace.js": PROJECT / "ns3/netanim/trace.js",
    "/ns3/netanim/viewer.js": PROJECT / "ns3/netanim/viewer.js",
    "/results": PROJECT / "ns3/netanim/results_dashboard.html",
    "/results/": PROJECT / "ns3/netanim/results_dashboard.html",
    "/ns3/netanim/results_dashboard.js": PROJECT / "ns3/netanim/results_dashboard.js",
}
PROTOCOLS = {"ar-eaurp", "drl-senior", "drl-paper", "eaurp", "aodv", "ns3-aodv"}
ATTACKS = {"none", "grayhole", "blackhole", "trust_poisoning"}


class Run:
    def __init__(self, binary: Path):
        self.binary = binary
        self.lock = threading.Lock()
        self.process: subprocess.Popen[str] | None = None
        self.state = "idle"
        self.message = ""
        self.events: deque[tuple[int, str]] = deque(maxlen=200_000)
        self.logs: deque[str] = deque(maxlen=20)
        self.seq = 0
        self.result = None
        self.trace = ""

    def start(self, config: dict) -> None:
        protocol = config.get("protocol")
        attack = config.get("attack")
        if protocol not in PROTOCOLS or attack not in ATTACKS:
            raise ValueError("Choose a supported protocol and attack.")
        try:
            nodes = int(config["nodes"])
            flows = int(config["flows"])
            duration = float(config["duration"])
            malicious = float(config["malicious"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Nodes, flows, duration and hostile fraction must be numbers.") from exc
        if not (2 <= nodes <= 200 and 1 <= flows <= 100 and 8 <= duration <= 300
                and 0 <= malicious <= 0.5):
            raise ValueError("Run settings are outside the supported viewer range.")
        if attack == "none" and malicious != 0:
            raise ValueError("A clean run needs a zero hostile fraction.")
        if protocol == "ns3-aodv" and (attack != "none" or malicious != 0):
            raise ValueError("Upstream ns-3 AODV only supports clean runs.")
        if not self.binary.is_file():
            raise FileNotFoundError(f"Native simulator missing: {self.binary}. Build with ns3/scripts/setup.sh first.")
        with self.lock:
            if self.process and self.process.poll() is None:
                raise RuntimeError("A simulation is already running.")
            directory = PROJECT / "results" / "ns3-live" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            directory.mkdir(parents=True)
            trace = directory / "trace.xml"
            result = directory / "result.json"
            args = [str(self.binary), f"--protocol={protocol}", f"--attack={attack}",
                    f"--malicious={malicious}", f"--nodes={nodes}", f"--flows={flows}",
                    f"--time={duration}", f"--warmup={min(5.0, duration / 4)}",
                    "--area=420", "--seed=1", "--run=1",
                    f"--netanim={trace}", "--netanimStream=1",
                    f"--realtime={1 if config.get('realtime', True) else 0}",
                    f"--train={1 if config.get('train', True) else 0}", f"--json={result}"]
            (directory / "launch.json").write_text(
                json.dumps({"requested_settings": config, "command": args}, indent=2) + "\n",
                encoding="utf-8")
            self.process = subprocess.Popen(args, cwd=PROJECT, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, text=True,
                                            encoding="utf-8", errors="replace", bufsize=1)
            self.state = "commissioning" if protocol == "ar-eaurp" and config.get("train", True) else "running"
            self.message = "Native simulator started."
            self.events.clear()
            self.logs.clear()
            self.seq = 0
            self.result = None
            self.trace = str(trace)
            threading.Thread(target=self._read, args=(self.process, result), daemon=True).start()

    def _read(self, process: subprocess.Popen[str], result_file: Path) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            if line.startswith("@NETANIM@"):
                xml = line[len("@NETANIM@"):].strip()
                if not xml:
                    continue
                with self.lock:
                    self.seq += 1
                    self.events.append((self.seq, xml))
            else:
                message = line.strip()
                if message:
                    with self.lock:
                        self.logs.append(message[:240])
                        if message.startswith("[evaluation]"):
                            self.state = "running"
                        if message.startswith("[commissioning]") or message.startswith("[evaluation]"):
                            self.message = message[:240]
        code = process.wait()
        with self.lock:
            if self.state != "stopped":
                self.state = "finished" if code == 0 else "failed"
                self.message = ("Simulation complete." if code == 0 else
                                f"Native simulator exited with code {code}. " +
                                " | ".join(list(self.logs)[-3:]))
            if result_file.is_file():
                try:
                    self.result = json.loads(result_file.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    self.message += " Result JSON could not be read."

    def stop(self) -> None:
        with self.lock:
            process = self.process
            if process and process.poll() is None:
                self.state = "stopped"
                self.message = "Simulation stopped by the user."
                process.terminate()

    def snapshot(self, since: int) -> dict:
        with self.lock:
            oldest = self.events[0][0] if self.events else self.seq + 1
            if since < oldest - 1:
                return {"overflow": True, "events": [], "state": self.state,
                        "trace": self.trace,
                        "message": "Live event buffer was exceeded. Open the saved NetAnim XML for full replay."}
            items = [{"seq": seq, "xml": xml} for seq, xml in self.events if seq > since][:3000]
            return {"events": items, "latestSeq": self.seq,
                    "state": self.state, "message": self.message,
                    "result": self.result, "trace": self.trace}


class Handler(BaseHTTPRequestHandler):
    run_state: Run

    def _json(self, code: int, data: dict) -> None:
        body = json.dumps(data, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        if url.path == "/api/results":
            self._json(200, {"runs": self._saved_results()})
            return
        if url.path == "/api/trace":
            run_id = parse_qs(url.query).get("run", [""])[0]
            # Only expose traces paired with result files found by the known
            # results scanner. This keeps the endpoint from becoming a path reader.
            run = next((item for item in self._saved_results()
                        if item["id"] == run_id and item["traceAvailable"]), None)
            if run is None:
                self._json(404, {"error": "No saved NetAnim trace is available for this run."})
                return
            results_root = (PROJECT / "results").resolve()
            trace_path = (results_root / Path(run["id"]).parent / "trace.xml").resolve()
            try:
                trace_path.relative_to(results_root)
                body = trace_path.read_bytes()
            except (OSError, ValueError):
                self._json(404, {"error": "The saved NetAnim trace could not be read."})
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if url.path == "/api/events":
            try:
                since = max(0, int(parse_qs(url.query).get("since", ["0"])[0]))
            except ValueError:
                self._json(400, {"error": "Invalid event cursor."})
                return
            self._json(200, self.run_state.snapshot(since))
            return
        path = STATIC.get(url.path)
        if not path:
            self.send_error(404)
            return
        body = path.read_bytes()
        content_type = "application/javascript" if path.suffix == ".js" else "text/html"
        self.send_response(200)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _saved_results() -> list[dict]:
        """Return parsed simulation results from the project's known output folders."""
        root = PROJECT / "results"
        candidates = list((root / "ns3-live").rglob("result.json"))
        for folder in (root / "final_review_ns3_results" / "native_demo",
                       root / "final_review_ns3_results" / "native_long_runs"):
            if folder.is_dir():
                candidates.extend(folder.glob("*.json"))
        runs = []
        for path in candidates:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or data.get("engine") != "ns-3":
                    continue
                stat = path.stat()
                runs.append({
                    "id": path.relative_to(root).as_posix(),
                    "name": path.parent.name,
                    "modified": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
                    "bytes": stat.st_size,
                    "traceAvailable": path.name == "result.json" and (path.parent / "trace.xml").is_file(),
                    "runAgainAvailable": all(key in data for key in
                        ("protocol", "attack", "cfg_nodes", "cfg_flows", "cfg_malicious", "cfg_duration")),
                    "data": data,
                })
            except (OSError, ValueError):
                continue
        return sorted(runs, key=lambda run: run["modified"], reverse=True)

    def do_POST(self) -> None:
        try:
            origin = self.headers.get("Origin", "")
            expected = f"http://127.0.0.1:{self.server.server_port}"
            if origin and origin != expected:
                raise ValueError("Requests must come from this local viewer.")
            if self.path == "/api/start":
                if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                    raise ValueError("Start requests require JSON.")
            if self.path == "/api/start":
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 4096:
                    raise ValueError("Invalid run request size.")
                config = json.loads(self.rfile.read(length))
                if not isinstance(config, dict):
                    raise ValueError("Run settings must be an object.")
                self.run_state.start(config)
                self._json(200, {"state": "started"})
            elif self.path == "/api/stop":
                self.run_state.stop()
                self._json(200, {"state": "stopped"})
            else:
                self.send_error(404)
        except (ValueError, RuntimeError, FileNotFoundError, OSError) as exc:
            self._json(400, {"error": str(exc)})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns3-home", type=Path, default=Path.home() / ".cache/ar-eaurp/ns-3.45")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    Handler.run_state = Run(args.ns3_home / "build/scratch/ns3.45-ar-eaurp-sim-optimized")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"AR-EAURP viewer: http://127.0.0.1:{args.port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
