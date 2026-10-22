#!/usr/bin/env python3
"""Resume energy, lifetime, ablation, and CMDP-floor batches concurrently."""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, json, os, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parents[1]
NS3_HOME=Path(os.environ.get("NS3_HOME","/home/abhi/.cache/ar-eaurp/ns-3.45"))
NATIVE=NS3_HOME/"build/scratch/ns3.45-ar-eaurp-sim-optimized"
PROTOCOLS=["aodv","eaurp","drl-paper","drl-senior","ar-eaurp"]

def params(exp:str, protocol:str, variant:str, run:int)->dict[str,str]:
    p={"area":"420","attack":"none","commission":"240","flows":"6","ganEpochs":"120",
       "lstmEpochs":"30","malicious":"0","nodes":"24","protocol":protocol,
       "run":str(run),"seed":"20260909","time":"120","warmup":"20"}
    if exp in {"e4_energy","e4b_lifetime"}:
        mode=variant.split("-")[-1]
        p["harvest"]="1" if mode=="solar" else "0"
        if exp=="e4b_lifetime": p.update({"time":"900","energy":"350"})
    elif exp=="e5_ablation":
        p.update({"attack":"grayhole","malicious":"0.3"})
        if variant in {"C without GAN","C bare"}: p["gan"]="0"
        if variant in {"C without LSTM","C bare"}: p["lstm"]="0"
        if variant in {"C without CMDP","C bare"}: p["cmdp"]="0"
        if variant=="C without energy excuse": p["energyExcuse"]="0"
    elif exp=="e5b_cmdp_floor":
        p.update({"attack":"grayhole","malicious":"0.3","pdrFloor":variant})
    return p

def signature(identity:str,p:dict[str,str])->str:
    text="ns-3.45 native batch v1\n"+identity+"\n"+"".join(f"{k}={p[k]}\n" for k in sorted(p))
    return hashlib.sha256(text.encode()).hexdigest()

def valid(path:Path,sig:str)->bool:
    try:
        lines=path.read_text(encoding="utf-8").splitlines()
        return lines[0]=="AR-EAURP native checkpoint 1" and lines[1]==sig and hashlib.sha256(("\n".join(lines[3:])+"\n").encode()).hexdigest()==lines[2]
    except (OSError,IndexError): return False

def run(job:tuple[str,str,str,int])->tuple[str,str]:
    exp,protocol,variant,r=job
    out=ROOT/"parts"/("e4" if exp in {"e4_energy","e4b_lifetime"} else "e5")
    identity=json.loads((out/"manifest.json").read_text(encoding="utf-8"))["source_sha256"]
    p=params(exp,protocol,variant,r); sig=signature(identity,p); cache=out/"raw"/(sig+".csv")
    if valid(cache,sig): return (f"{exp}-{variant}-{protocol}-r{r}","cached")
    cache.parent.mkdir(parents=True,exist_ok=True)
    stem=f"{exp}-{variant.replace(' ','_')}-{protocol}-r{r}"
    json_path=out/"raw_json"/(stem+".json"); log=out/"raw_json"/(stem+".log"); json_path.parent.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env["AR_EAURP_PROJECT"]=str(PROJECT);env["NS3_HOME"]=str(NS3_HOME)
    command=[str(NATIVE)]+[f"--{k}={v}" for k,v in p.items()]+[f"--json={json_path}"]
    with log.open("w",encoding="utf-8") as stream:
        done=subprocess.run(command,cwd=PROJECT,env=env,stdout=stream,stderr=subprocess.STDOUT,check=False)
    if done.returncode or not json_path.is_file(): raise RuntimeError(f"Failed {stem}; see {log}")
    raw=json.loads(json_path.read_text(encoding="utf-8"))
    metrics={k:float(v) for k,v in raw.items() if isinstance(v,(int,float)) and not isinstance(v,bool)}
    payload="".join(f"{k},{metrics[k]:.17g}\n" for k in sorted(metrics)); checksum=hashlib.sha256(payload.encode()).hexdigest()
    cache.write_text(f"AR-EAURP native checkpoint 1\n{sig}\n{checksum}\n{payload}",encoding="utf-8",newline="\n")
    return (stem,"done")

def main()->None:
    ap=argparse.ArgumentParser();ap.add_argument("--workers",type=int,default=3);a=ap.parse_args()
    jobs=[]
    for proto in PROTOCOLS:
        for mode in ["battery","solar"]:
            for run_id in range(1,6):
                jobs.append(("e4_energy",proto,mode,run_id));jobs.append(("e4b_lifetime",proto,mode,run_id))
    for variant in ["C full","C without GAN","C without LSTM","C without CMDP","C bare","C without energy excuse"]:
        for run_id in range(1,6): jobs.append(("e5_ablation","ar-eaurp",variant,run_id))
    for floor in ["0.70","0.80","0.90","0.95"]:
        for run_id in range(1,6): jobs.append(("e5b_cmdp_floor","ar-eaurp",floor,run_id))
    failures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,a.workers)) as pool:
        futures={pool.submit(run,j):j for j in jobs}
        for i,f in enumerate(concurrent.futures.as_completed(futures),1):
            try: name,status=f.result();print(f"[{i}/{len(jobs)}] {name}: {status}",flush=True)
            except Exception as e: failures.append((futures[f],str(e)));print(f"FAILED {futures[f]}: {e}",file=sys.stderr,flush=True)
    if failures: raise SystemExit(f"{len(failures)} energy/ablation runs failed; rerun to resume")
    print("All 150 E4/E4b/E5/E5b native runs are checkpointed.")

if __name__=="__main__":main()
