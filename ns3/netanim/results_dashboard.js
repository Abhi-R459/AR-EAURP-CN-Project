(() => {
  const $ = id => document.getElementById(id);
  const state = {runs: [], selected: new Set(), active: null};
  const esc = v => String(v == null ? "" : v).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const n = v => Number.isFinite(Number(v)) ? Number(v) : null;
  const compact = v => {const x=n(v);if(x===null)return "—";if(Math.abs(x)>=1e6)return (x/1e6).toFixed(2)+"M";if(Math.abs(x)>=1e3)return (x/1e3).toFixed(2)+"k";return Number.isInteger(x)?String(x):x.toFixed(3).replace(/0+$/,"").replace(/\.$/,"");};
  const pct = v => n(v)===null?"—":(Number(v)*100).toFixed(1)+"%";
  const sec = v => n(v)===null?"—":Number(v).toFixed(3)+" s";
  const proto = r => String(r.data.protocol||"unknown").toUpperCase();
  const attack = r => String(r.data.attack||"unknown").replaceAll("_"," ");
  const title = r => proto(r)+" · "+attack(r)+" · "+r.name;
  const value = (r,k) => r.data[k];
  const detailFields = [
    ["Application", [["app_tx","Packets sent"],["app_rx","Packets received"],["loss_packets","Lost packets"],["pdr","Packet delivery ratio"],["mean_delay_s","Mean delay"],["delay_std_s","Delay standard deviation"],["throughput_bps","Throughput"],["mean_hops","Mean hops"]]],
    ["Detection and response", [["detector_auc","Detector AUC"],["detect_tpr","Window true positive rate"],["detect_fpr","Window false positive rate"],["detector_windows","Measured windows"],["detector_positive_windows","Positive windows"],["detector_negative_windows","Negative windows"],["contested_tpr","Contested true positive rate"],["contested_fpr","Contested false positive rate"],["revoke_tpr","Revocation true positive rate"],["revoke_fpr","Revocation false positive rate"],["adversary_drops","Adversary drops"]]],
    ["Network overhead", [["control_packets","Control packets"],["control_bytes","Control bytes"],["crypto_packets","Crypto packets"],["crypto_overhead_bytes","Crypto overhead bytes"],["route_discoveries","Route discoveries"],["route_discovery_failures","Failed discoveries"],["link_failures","Link failures"],["local_repairs","Local repairs"]]],
    ["Energy and lifetime", [["residual_energy_j","Residual energy"],["harvested_j","Harvested energy"],["energy_drops","Energy drops"],["dead_nodes","Dead nodes"],["first_death_s","First node death"],["lifetime_horizon_s","Lifetime horizon"]]],
    ["Learning and runtime", [["gan_trained","GAN trained"],["gan_train_windows","GAN training windows"],["gan_threshold","GAN threshold"],["lstm_selected","LSTM selected"],["lstm_mae_w","LSTM validation MAE"],["lstm_persistence_mae_w","Persistence baseline MAE"],["cmdp_decisions","CMDP decisions"],["cmdp_violations","CMDP violations"],["cmdp_lambda","CMDP λ"],["wall_clock_seconds","Wall clock runtime"]]]
  ];
  function filtered(){
    const p=$("protocolFilter").value,a=$("attackFilter").value,q=$("search").value.trim().toLowerCase();
    return state.runs.filter(r=>(!p||r.data.protocol===p)&&(!a||r.data.attack===a)&&(!q||(r.name+" "+r.id+" "+r.data.protocol+" "+r.data.attack).toLowerCase().includes(q)));
  }
  function updateFilters(){
    const p=$("protocolFilter").value,a=$("attackFilter").value;
    const ps=[...new Set(state.runs.map(r=>r.data.protocol).filter(Boolean))].sort(),as=[...new Set(state.runs.map(r=>r.data.attack).filter(Boolean))].sort();
    $("protocolFilter").innerHTML='<option value="">All protocols</option>'+ps.map(x=>'<option value="'+esc(x)+'">'+esc(x.toUpperCase())+'</option>').join("");
    $("attackFilter").innerHTML='<option value="">All scenarios</option>'+as.map(x=>'<option value="'+esc(x)+'">'+esc(x.replaceAll("_"," "))+'</option>').join("");
    $("protocolFilter").value=ps.includes(p)?p:"";$("attackFilter").value=as.includes(a)?a:"";
  }
  function summary(rows){
    $("runCount").textContent=rows.length;
    const avg=k=>{const xs=rows.map(r=>n(value(r,k))).filter(x=>x!==null);return xs.length?xs.reduce((a,b)=>a+b,0)/xs.length:null;};
    $("avgPdr").textContent=pct(avg("pdr"));
    $("avgThroughput").textContent=avg("throughput_bps")===null?"—":compact(avg("throughput_bps"))+" bps";
    $("avgDelay").textContent=avg("mean_delay_s")===null?"—":sec(avg("mean_delay_s"));
  }
  function renderRows(rows){
    $("empty").hidden=rows.length>0;
    $("runRows").innerHTML=rows.map(r=>'<tr class="'+(state.active===r.id?"active":"")+'" data-id="'+esc(r.id)+'"><td><input type="checkbox" aria-label="Compare '+esc(title(r))+'" data-compare="'+esc(r.id)+'" '+(state.selected.has(r.id)?"checked":"")+'></td><td><span class="badge">'+esc(proto(r))+'</span></td><td><span class="badge attack">'+esc(attack(r))+'</span></td><td class="mono">'+esc(r.data.cfg_nodes??"—")+'</td><td class="mono">'+pct(r.data.pdr)+'</td><td class="mono">'+sec(r.data.mean_delay_s)+'</td><td class="mono">'+(n(r.data.throughput_bps)===null?"—":compact(r.data.throughput_bps)+" bps")+'</td><td title="'+esc(r.id)+'">'+esc(r.name)+'</td></tr>').join("");
    summary(rows);renderComparison();
  }
  function detailValue(k,v){
    if(v===undefined||v===null)return "Not recorded";
    if(["pdr","detect_tpr","detect_fpr","contested_tpr","contested_fpr","revoke_tpr","revoke_fpr","detector_auc","mean_residual_fraction","watchdog_observation_rate"].includes(k))return pct(v);
    if(k.endsWith("_s"))return sec(v);if(k.endsWith("_j"))return Number(v).toFixed(2)+" J";if(k.endsWith("_bps"))return compact(v)+" bps";
    if(["gan_trained","lstm_trained","lstm_selected","cfg_realtime","cfg_train"].includes(k))return Number(v)?"Yes":"No";
    return typeof v==="number"?compact(v):String(v);
  }
  function renderDetails(r){
    if(!r){$("selected").innerHTML='<p class="muted">Choose a run in the table to inspect settings and detailed metrics.</p>';return;}
    const d=r.data;let html="<h3>"+esc(proto(r))+" · "+esc(attack(r))+"</h3><p class=\"notice\">"+esc(r.id)+(r.modified?" · "+esc(new Date(r.modified).toLocaleString()):"")+"</p>";
    if(r.traceAvailable||r.runAgainAvailable){html+='<div class="detail-actions">'+(r.traceAvailable?'<button class="primary" data-run-action="replay" data-id="'+esc(r.id)+'">Replay saved trace</button>':'')+(r.runAgainAvailable?'<button data-run-action="again" data-id="'+esc(r.id)+'">Run again with these settings</button>':'')+'</div><p class="notice">Replay opens the saved NetAnim trace. Run again starts a new ns-3 simulation using this run’s recorded settings.</p>';}
    html+='<div class="detail-grid" style="margin:12px 0"><div class="detail"><small>Topology</small><strong>'+esc(d.cfg_nodes??"—")+' nodes · '+esc(d.cfg_flows??"—")+' flows</strong></div><div class="detail"><small>Scenario</small><strong>'+esc(d.cfg_duration??"—")+' s · '+pct(d.cfg_malicious)+' hostile</strong></div></div>';
    if(d.detector_windows===undefined||d.contested_tpr===undefined)html+='<p class="notice" style="color:var(--amber)">Legacy result schema: this file lacks newer window-level and contested-response fields. Treat detector scores as legacy and compare cautiously.</p>';
    for(const group of detailFields){const fields=group[1].filter(f=>d[f[0]]!==undefined);if(!fields.length)continue;html+='<h3 style="margin:14px 0 7px">'+group[0]+'</h3><div class="detail-grid">'+fields.map(f=>'<div class="detail"><small>'+esc(f[1])+'</small><strong>'+esc(detailValue(f[0],d[f[0]]))+'</strong></div>').join("")+'</div>';}
    $("selected").innerHTML=html;
  }
  function renderChart(){
    let rs=state.selected.size?state.runs.filter(r=>state.selected.has(r.id)).slice(0,8):state.runs.filter(r=>r.id===state.active);
    if(!rs.length){$("chart").innerHTML='<p class="empty">Select a run to see its measured outcomes.</p>';return;}
    const ms=[["pdr","Packet delivery ratio",pct,1],["throughput_bps","Throughput (bars scale to largest selected run)",v=>compact(v)+" bps","max"],["mean_delay_s","Mean delay (bars scale to largest selected run)",sec,"max"]];
    $("chart").innerHTML=ms.map(m=>{const vals=rs.map(r=>n(value(r,m[0]))),max=m[3]==="max"?Math.max(...vals.filter(x=>x!==null),0):m[3];return '<div><h3>'+m[1]+'</h3><div class="chart-list">'+rs.map((r,i)=>{const v=vals[i],w=v===null||!max?0:Math.max(1,Math.min(100,v/max*100));return '<div class="bar-row" title="'+esc(title(r))+'"><span>'+esc(proto(r))+'</span><div class="bar-track"><div class="bar '+(m[0]==="mean_delay_s"?"delay":"")+'" style="width:'+w+'%"></div></div><span class="mono">'+(v===null?"—":esc(m[2](v)))+'</span></div>';}).join("")+'</div></div>';}).join("")+'<p class="legend">PDR bars use 0–100%. Throughput and delay bars scale to the largest selected value. Select up to eight runs to compare.</p>';
  }
  function renderComparison(){
    const rs=state.runs.filter(r=>state.selected.has(r.id));
    if(!rs.length){$("comparison").innerHTML="";renderChart();return;}
    const cols=[["pdr","PDR"],["mean_delay_s","Mean delay"],["throughput_bps","Throughput"],["detect_tpr","Window TPR"],["detect_fpr","Window FPR"],["contested_tpr","Contested TPR"],["control_packets","Control packets"],["residual_energy_j","Residual J"]];
    $("comparison").innerHTML="<h3>Selected run comparison ("+rs.length+")</h3><p class=\"notice\">Values are taken directly from each result file. A dash means the field is absent.</p><table><thead><tr><th>Measurement</th>"+rs.map(r=>"<th>"+esc(title(r))+"</th>").join("")+"</tr></thead><tbody>"+cols.map(c=>"<tr><td>"+c[1]+"</td>"+rs.map(r=>{const k=c[0],v=value(r,k),out=["pdr","detect_tpr","detect_fpr","contested_tpr","contested_fpr"].includes(k)?pct(v):k==="mean_delay_s"?sec(v):k==="throughput_bps"?(n(v)===null?"—":compact(v)+" bps"):detailValue(k,v);return "<td>"+esc(out)+"</td>";}).join("")+"</tr>").join("")+"</tbody></table>";
    renderChart();
  }
  function render(){
    const rows=filtered();if(!rows.some(r=>r.id===state.active))state.active=rows[0]?.id||null;
    renderRows(rows);renderDetails(state.runs.find(r=>r.id===state.active));renderChart();
  }
  async function refresh(){
    $("status").textContent="Loading saved results…";
    try{const response=await fetch("/api/results",{cache:"no-store"});if(!response.ok)throw new Error("server returned "+response.status);const json=await response.json();const imported=state.runs.filter(r=>r.imported);state.runs=[...(json.runs||[]),...imported];updateFilters();render();$("status").textContent=(json.runs?.length||0)+" saved runs · refreshed "+new Date().toLocaleTimeString();}
    catch(e){$("status").textContent="Could not load saved runs: "+e.message+". Start the local viewer server and refresh.";}
  }
  $("runRows").addEventListener("click",e=>{const box=e.target.closest("[data-compare]");if(box){box.checked?state.selected.add(box.dataset.compare):state.selected.delete(box.dataset.compare);renderComparison();return;}const row=e.target.closest("tr[data-id]");if(row){state.active=row.dataset.id;render();}});
  $("selected").addEventListener("click",async e=>{
    const button=e.target.closest("[data-run-action]");if(!button)return;
    const run=state.runs.find(item=>item.id===button.dataset.id);if(!run)return;
    if(button.dataset.runAction==="replay"){
      location.href="/?trace="+encodeURIComponent(run.id);return;
    }
    if(button.dataset.runAction!=="again"||!run.runAgainAvailable)return;
    const d=run.data;
    const config={protocol:d.protocol,attack:d.attack,nodes:Number(d.cfg_nodes),flows:Number(d.cfg_flows),malicious:Number(d.cfg_malicious),duration:Number(d.cfg_duration),train:d.cfg_train===undefined?true:Boolean(d.cfg_train),realtime:d.cfg_realtime===undefined?true:Boolean(d.cfg_realtime)};
    if(config.attack==="none"||config.protocol==="ns3-aodv")config.malicious=0;
    if(config.protocol==="ns3-aodv")config.attack="none";
    button.disabled=true;button.textContent="Starting simulation…";$("status").textContent="Starting a new ns-3 run with the saved settings…";
    try{
      const response=await fetch("/api/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(config)});
      const data=await response.json();if(!response.ok)throw new Error(data.error||"Server returned "+response.status);
      location.href="/";
    }catch(error){button.disabled=false;button.textContent="Run again with these settings";$("status").textContent="Could not start the simulation: "+error.message;}
  });
  $("refresh").addEventListener("click",refresh);$("search").addEventListener("input",render);$("protocolFilter").addEventListener("change",render);$("attackFilter").addEventListener("change",render);
  $("upload").addEventListener("change",async e=>{const files=[...e.target.files];let loaded=0;for(const file of files)try{const data=JSON.parse(await file.text());if(!data||typeof data!=="object"||Array.isArray(data))throw new Error("not a JSON object");state.runs.push({id:"upload:"+file.name+":"+Date.now()+":"+Math.random().toString(36).slice(2,7),name:file.name,modified:new Date(file.lastModified).toISOString(),data,imported:true});loaded++;}catch(err){console.warn("Skipping "+file.name+": "+err.message);}updateFilters();render();$("status").textContent="Loaded "+loaded+" of "+files.length+" selected JSON file(s).";e.target.value="";});
  refresh();
  setInterval(refresh,10000);
})();
