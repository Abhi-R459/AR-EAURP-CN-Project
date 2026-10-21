"""Generate Colab notebooks that build and run ns-3, with no Python simulator."""
import base64
import json
from pathlib import Path
import zlib

ROOT = Path(__file__).resolve().parents[1]
CONTENT_ROOT = "/content/AR-EAURP-CN-Project"


def markdown(source):
    return {"cell_type": "markdown", "metadata": {}, "source": source}


def code(source, collapsed=False):
    return {"cell_type": "code", "execution_count": None, "outputs": [],
            "metadata": {"jupyter": {"source_hidden": True}} if collapsed else {},
            "source": source}


def source_bundle():
    files = []
    for directory in ("experiments", "tests", "ns3", "tools"):
        files.extend(p for p in (ROOT / directory).rglob("*")
                     if p.is_file() and p.suffix in (".py", ".cc", ".h", ".sh", ".txt"))
    files.extend((ROOT / "requirements.txt", ROOT / "pytest.ini"))
    mapping = {str(p.relative_to(ROOT)): p.read_text() for p in sorted(files)}
    return base64.b64encode(zlib.compress(json.dumps(mapping).encode(), 9)).decode()


def notebook(mode):
    cells = [markdown("""# AR-EAURP — native ns-3.45 evaluation

All packet forwarding, Wi-Fi, mobility, energy, attacks, GAN/LSTM/DQN and tabular learning run in C++. Python launches experiments and plots their measurements.

The first run downloads ns-3.45 and builds it with CMake/OpenSSL. Internet is required. Use a CPU runtime; a GPU is unnecessary. `smoke` verifies the installation, `quick` runs short paired experiments, and `full` is the multi-seed research budget. Historical Python numbers are separate.

Run the cells from the top. Raw per-seed JSON files checkpoint progress, and only matching source/configuration checkpoints are reused.""")]
    if mode == "selfcontained":
        cells.append(code(f'''# Restore the project snapshot embedded by tools/build_notebook.py.
import base64, json, os, sys, zlib
from pathlib import Path
PROJECT = Path({CONTENT_ROOT!r})
PROJECT.mkdir(parents=True, exist_ok=True)
bundle = json.loads(zlib.decompress(base64.b64decode({source_bundle()!r})))
for relative, content in bundle.items():
    target = PROJECT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
os.chdir(PROJECT)
sys.path.insert(0, str(PROJECT))
print("Restored", len(bundle), "native project files")
''', collapsed=True))
    else:
        cells.append(markdown("""The repository may require a read-only GitHub token. Add it to Colab Secrets as `GITHUB_TOKEN` with notebook access. Credentials are passed through a temporary askpass helper and are never stored in the repository URL. The embedded-source notebook works without GitHub access, but still downloads ns-3."""))
        cells.append(code(f'''import os, subprocess, sys, tempfile
from pathlib import Path
PROJECT = Path({CONTENT_ROOT!r})
REPO = "https://github.com/Abhi-R459/AR-EAURP-CN-Project.git"
if not (PROJECT / ".git").is_dir():
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(["git", "clone", "--depth=1", REPO, str(PROJECT)],
                            env=env, capture_output=True, text=True)
    if result.returncode:
        token = None
        try:
            from google.colab import userdata
            token = userdata.get("GITHUB_TOKEN")
        except Exception:
            pass
        if not token:
            raise RuntimeError("Clone failed. Add GITHUB_TOKEN to Colab Secrets, or use REVIEW2_AR_EAURP.ipynb.")
        with tempfile.TemporaryDirectory() as temp:
            askpass = Path(temp) / "askpass.sh"
            askpass.write_text('#!/bin/sh\\ncase "$1" in *Username*) echo x-access-token ;; *) printf "%s\\\\n" "$AR_GITHUB_TOKEN" ;; esac\\n')
            askpass.chmod(0o700)
            private_env = dict(env, GIT_ASKPASS=str(askpass), AR_GITHUB_TOKEN=token)
            result = subprocess.run(["git", "clone", "--depth=1", REPO, str(PROJECT)],
                                    env=private_env, capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError("Authenticated clone failed. Check token read access to this repository.")
        del token, private_env
os.chdir(PROJECT)
sys.path.insert(0, str(PROJECT))
print("Project:", PROJECT)
'''))
    cells.append(code('''# Install build tools and lightweight analysis dependencies.
import subprocess, sys
subprocess.run(["apt-get", "update", "-qq"], check=True)
subprocess.run(["apt-get", "install", "-y", "-qq", "build-essential", "cmake", "pkg-config", "libssl-dev", "curl"], check=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], check=True)
NS3_HOME = "/content/ns-3.45"
subprocess.run(["bash", "ns3/scripts/setup.sh", "--home", NS3_HOME, "--download"], check=True)
os.environ["NS3_HOME"] = NS3_HOME
'''))
    cells.append(code('''# Keep results in Google Drive to survive runtime disconnection.
USE_DRIVE = False
PROFILE = "smoke"  # smoke / quick / full
if USE_DRIVE:
    from google.colab import drive
    drive.mount("/content/drive")
    OUT_DIR = f"/content/drive/MyDrive/AR-EAURP/ns3-{PROFILE}"
else:
    OUT_DIR = f"results/ns3-{PROFILE}"
print("Results:", OUT_DIR)
'''))
    cells.append(code('''# Native model tests plus real network/process/checkpoint integration tests.
from pathlib import Path
native = next(Path(NS3_HOME).glob("build/utils/ns3.45-test-runner-*"))
subprocess.run([str(native), "--suite=ar-eaurp", "--verbose"], check=True)
subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"], check=True)
'''))
    cells.append(code('''# Every configuration launches compiled C++, including clean commissioning.
# Rerun to resume matching raw checkpoints. Add --fresh to recompute.
subprocess.run([sys.executable, "experiments/run_all.py", "--profile", PROFILE,
                "--out-dir", OUT_DIR, "--ns3-home", NS3_HOME, "--no-build"], check=True)
'''))
    cells.append(code('''from tools.make_report import make_report
from IPython.display import Image, Markdown, display
report = make_report(OUT_DIR)
# Local /content and Drive paths need Image(filename=...) in Colab.
text = Path(report).read_text()
display(Markdown("\\n".join(line for line in text.splitlines() if not line.startswith("!["))))
for line in text.splitlines():
    if line.startswith("!["):
        filename = line.split("](", 1)[1][:-1]
        display(Image(filename=filename))
'''))
    cells.append(markdown("""A smoke run validates execution only. Check training flags and detector window counts before reading learned-component results. Censored lifetime events are not measured deaths. CMDP target violations do not prove infeasibility. The report lists the remaining modelling assumptions."""))
    return {"nbformat": 4, "nbformat_minor": 5,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                         "language_info": {"name": "python"}, "colab": {"name": "AR-EAURP ns-3"}},
            "cells": [dict(cell, id=f"ns3-{i:03d}") for i, cell in enumerate(cells)]}


def main():
    for mode, name in (("selfcontained", "REVIEW2_AR_EAURP.ipynb"), ("github", "REVIEW2_FROM_GITHUB.ipynb")):
        path = ROOT / "colab" / name
        path.write_text(json.dumps(notebook(mode), indent=1) + "\n")
        print(path)


if __name__ == "__main__":
    main()
