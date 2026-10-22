(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const canvas = $('canvas'), ctx = canvas.getContext('2d');
  const trace = new NetAnimTrace.Trace();
  let current = 0, playing = false, following = false, live = false;
  let selected = null, lastFrame = performance.now(), pollTimer = null, cursor = 0, polling = false;
  let bounds = null, transform = null, lastUi = 0, finalResult = null, activeProtocol = null;
  const comparisons = [];

  function addComparison(result, source) {
    if (result.engine !== 'ns-3' || !result.protocol || !Number.isFinite(result.pdr) ||
        !Number.isFinite(result.app_tx) || !Number.isFinite(result.app_rx))
      throw new Error('This is not a native ns-3 scenario result JSON.');
    const index = comparisons.findIndex(item => item.result.protocol === result.protocol &&
      item.result.cfg_seed === result.cfg_seed && item.result.cfg_run === result.cfg_run);
    if (index >= 0) comparisons.splice(index, 1);
    comparisons.push({result, source});
    if (comparisons.length > 100) comparisons.shift();
    renderComparison();
  }
  function renderComparison() {
    const table = $('compareTable'); table.replaceChildren();
    if (!comparisons.length) { $('compareNote').textContent = 'Run or load two protocols to compare their measured results.'; return; }
    const results = comparisons.map(item => item.result);
    const settings = ['attack', 'cfg_nodes', 'cfg_area', 'cfg_flows', 'cfg_duration',
      'cfg_warmup', 'cfg_cooldown', 'cfg_malicious', 'cfg_seed', 'cfg_run',
      'cfg_max_speed', 'cfg_rate', 'cfg_harvest', 'cfg_ecc', 'cfg_energy_j',
      'cfg_realtime'];
    const comparableSettings = settings.filter(key => key !== 'cfg_seed' && key !== 'cfg_run');
    const mismatched = comparableSettings.filter(key => results.some(r => r[key] !== results[0][key]));
    const missing = settings.filter(key => results.some(r => r[key] === undefined));
    const protocols = [...new Set(results.map(r => r.protocol))];
    const groups = protocols.map(protocol => ({protocol,
      results: results.filter(r => r.protocol === protocol)}));
    const summarize = (group, key) => {
      const values = group.results.map(r => r[key]).filter(Number.isFinite);
      if (!values.length) return null;
      const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
      const sd = values.length > 1 ? Math.sqrt(values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1)) : 0;
      return {mean, sd, n: values.length};
    };
    const show = (group, key, scale = 1, digits = 1, suffix = '') => {
      const s = summarize(group, key);
      return s ? `${(s.mean * scale).toFixed(digits)}${s.n > 1 ? ` ± ${(s.sd * scale).toFixed(digits)}` : ''}${suffix}` : '—';
    };
    const showDetected = (group, key) => {
      const measured = group.results.filter(r => r.detector_windows > 0);
      return measured.length ? show({...group, results: measured}, key, 100, 1, '%') : 'unmeasured';
    };
    const details = `${results[0].cfg_nodes} nodes · ${results[0].cfg_flows} flows · ` +
      `${results[0].attack} @ ${Math.round(100 * results[0].cfg_malicious)}% hostile · ` +
      `${results[0].cfg_duration}s · ${protocols.map(p => `${p}: n=${results.filter(r => r.protocol === p).length}`).join(', ')}.`;
    $('compareNote').textContent = (mismatched.length ? `Settings differ: ${mismatched.join(', ')}. ` :
      'Recorded settings match. ') + details +
      (missing.length ? ` Not recorded in every file: ${missing.join(', ')}.` : '') +
      results.filter(r => r.protocol === 'ar-eaurp' && r.cfg_train).slice(0, 1).map(r =>
        ` AR-EAURP commissioning: ${r.cfg_commission}s, GAN ${r.cfg_gan_epochs} epochs, LSTM ${r.cfg_lstm_epochs} epochs.`).join('') +
      (results.some(r => r.protocol === 'ar-eaurp' && r.detector_windows === 0) ?
        ' Some AR-EAURP runs had zero detector windows; those runs are excluded from detection-rate averages.' : '');
    const rows = [
      ['Runs', g => String(g.results.length)],
      ['Application packets sent (mean)', g => show(g, 'app_tx', 1, 1)],
      ['Application packets received (mean)', g => show(g, 'app_rx', 1, 1)],
      ['Application PDR (mean ± SD)', g => show(g, 'pdr', 100, 1, '%')],
      ['Mean app delay (mean ± SD)', g => show(g, 'mean_delay_s', 1000, 1, ' ms')],
      ['GAN window TPR (mean ± SD)', g => g.protocol !== 'ar-eaurp' ? 'n/a' :
        g.results.some(r => r.contested_tpr === undefined) ? 'legacy/mixed metric' : showDetected(g, 'detect_tpr')],
      ['GAN window FPR (mean ± SD)', g => g.protocol !== 'ar-eaurp' ? 'n/a' :
        g.results.some(r => r.contested_tpr === undefined) ? 'legacy/mixed metric' : showDetected(g, 'detect_fpr')],
      ['GAN score AUC (mean ± SD)', g => g.protocol !== 'ar-eaurp' ? 'n/a' : show(g, 'detector_auc', 1, 2)],
      ['Two-witness contested TPR', g => g.protocol !== 'ar-eaurp' ? 'n/a' : show(g, 'contested_tpr', 100, 1, '%')],
      ['Revocation TPR (mean)', g => show(g, 'revoke_tpr', 100, 1, '%')],
      ['Control packets (mean)', g => show(g, 'control_packets', 1, 1)],
      ['Adversary drops (mean)', g => show(g, 'adversary_drops', 1, 1)],
      ['GAN trained', g => g.protocol === 'ar-eaurp' ? `${g.results.filter(r => r.gan_trained).length}/${g.results.length}` : 'n/a'],
      ['LSTM selected for routing', g => g.protocol === 'ar-eaurp' ? `${g.results.filter(r => r.lstm_selected).length}/${g.results.length}` : 'n/a'],
      ['Detector windows (mean)', g => g.protocol === 'ar-eaurp' ? show(g, 'detector_windows', 1, 1) : 'n/a'],
      ['CMDP decisions (mean)', g => g.protocol === 'ar-eaurp' ? show(g, 'cmdp_decisions', 1, 1) : 'n/a']
    ];
    const header = document.createElement('tr');
    for (const label of ['Metric', ...groups.map(g => g.protocol.toUpperCase())]) {
      const cell = document.createElement('th'); cell.textContent = label; header.append(cell);
    }
    table.append(header);
    for (const [label, format] of rows) {
      const row = document.createElement('tr'), heading = document.createElement('td');
      heading.textContent = label; row.append(heading);
      groups.forEach(group => {
        const cell = document.createElement('td'); cell.textContent = format(group); row.append(cell);
      });
      table.append(row);
    }
  }

  function status(message, kind = '') {
    $('status').textContent = message;
    $('status').className = `status ${kind}`;
  }
  function reset() {
    trace.reset(); current = 0; selected = null; bounds = null; finalResult = null; activeProtocol = null;
    playing = false; following = false;
    for (const id of ['pdr', 'delay', 'tpr', 'lambda']) $(id).textContent = '—';
    $('events').textContent = 'Events appear when actual receptions are read.';
    $('inspector').textContent = 'Click a node to inspect its recorded role, IP and flow counts.';
    refreshUi();
  }
  function refreshUi() {
    $('nodeCount').textContent = trace.nodes.size || '—';
    $('packetCount').textContent = trace.nodes.size ? trace.packets.length.toLocaleString() : '—';
    $('empty').hidden = trace.nodes.size > 0;
    $('play').disabled = !trace.nodes.size;
    $('seek').disabled = !trace.nodes.size;
    $('seek').max = Math.max(0.001, trace.maxTime).toString();
    $('seek').value = Math.min(current, trace.maxTime).toString();
    $('clock').textContent = `${current.toFixed(2)} / ${trace.maxTime.toFixed(2)} s`;
    $('play').textContent = playing ? 'Pause' : 'Play';
    const main = [...trace.nodes.values()][0];
    const tx = trace.counter(main, 'AppTx', current), rx = trace.counter(main, 'AppRx', current);
    const latency = trace.counter(main, 'MeanAppDelayMs', current);
    const tpr = trace.counter(main, 'DetectTPR', current);
    const lambda = trace.counter(main, 'CmdpLambda', current);
    $('pdr').textContent = tx > 0 ? `${(100 * rx / tx).toFixed(1)}%` : '—';
    $('delay').textContent = rx > 0 && latency !== null ? `${latency.toFixed(1)} ms` : '—';
    const hasAttackers = [...trace.nodes.values()].some(n => /\| (grayhole|blackhole|trust_poisoning) \|/.test(n.description));
    const protocol = activeProtocol || /\| protocol ([\w-]+)/.exec(main?.description || '')?.[1];
    $('tpr').textContent = protocol === 'ar-eaurp' && finalResult?.detector_windows > 0 &&
      hasAttackers && tpr !== null ? `${(100 * tpr).toFixed(1)}%` : '—';
    $('lambda').textContent = protocol === 'ar-eaurp' && lambda !== null ? lambda.toFixed(3) : '—';
    if (finalResult && current >= trace.maxTime - 0.001) {
      if (Number.isFinite(finalResult.pdr)) $('pdr').textContent = `${(finalResult.pdr * 100).toFixed(1)}%`;
      if (Number.isFinite(finalResult.mean_delay_s)) $('delay').textContent = `${(finalResult.mean_delay_s * 1000).toFixed(1)} ms`;
      if (protocol === 'ar-eaurp' && finalResult.detector_windows > 0 &&
          Number.isFinite(finalResult.detect_tpr) && hasAttackers)
        $('tpr').textContent = `${(finalResult.detect_tpr * 100).toFixed(1)}%`;
      if (protocol === 'ar-eaurp' && Number.isFinite(finalResult.cmdp_lambda))
        $('lambda').textContent = finalResult.cmdp_lambda.toFixed(3);
    }
  }
  function updateInspector() {
    const n = trace.nodes.get(selected);
    if (!n) return;
    const pos = trace.position(n, current);
    const battery = trace.counter(n, 'BatteryJ', current);
    const contested = trace.counter(n, 'ContestedWitnesses', current);
    const revoked = trace.counter(n, 'RevokedWitnesses', current);
    $('inspector').textContent = `${n.description}\nPosition: ${pos.x.toFixed(1)}, ${pos.y.toFixed(1)} m` +
      `\nBattery: ${battery === null ? 'unavailable' : `${battery.toFixed(2)} J`}` +
      `\nHonest observers ever flagging: ${contested ?? 'unavailable'}` +
      `\nHonest observers ever revoking: ${revoked ?? 'unavailable'}` +
      `\nRecorded position updates: ${n.motion.length}`;
  }
  function updateEvents() {
    if (!trace.packets.length) return;
    // A live stream is chronologically ordered; replay files are sorted on load.
    const index = trace.packetIndex(current + 0.00001);
    const recent = trace.packets.slice(Math.max(0, index - 12), index);
    const list = $('events'); list.replaceChildren();
    for (const p of recent.reverse()) {
      const line = document.createElement('div');
      line.textContent = `${p.rx.toFixed(3)}s  ${p.from} → ${p.to}  wireless receive${p.meta ? ` · ${p.meta.slice(0, 90)}` : ''}`;
      line.title = p.meta || '';
      list.append(line);
    }
  }
  function recomputeBounds() {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of trace.nodes.values()) for (const p of n.motion.length ? n.motion : [n]) {
      minX = Math.min(minX, p.x); minY = Math.min(minY, p.y);
      maxX = Math.max(maxX, p.x); maxY = Math.max(maxY, p.y);
    }
    if (!Number.isFinite(minX)) return;
    const pad = Math.max(20, Math.max(maxX - minX, maxY - minY) * 0.07);
    bounds = {minX: minX - pad, minY: minY - pad, maxX: maxX + pad, maxY: maxY + pad};
  }
  function resize() {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width * dpr));
    const height = Math.max(1, Math.round(rect.height * dpr));
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return rect;
  }
  function draw() {
    const rect = resize();
    ctx.clearRect(0, 0, rect.width, rect.height);
    if (!trace.nodes.size) return;
    if (!bounds) recomputeBounds();
    const w = bounds.maxX - bounds.minX, h = bounds.maxY - bounds.minY;
    const scale = Math.min((rect.width - 36) / w, (rect.height - 36) / h);
    const ox = (rect.width - w * scale) / 2, oy = (rect.height - h * scale) / 2;
    transform = p => ({x: ox + (p.x - bounds.minX) * scale,
      y: rect.height - oy - (p.y - bounds.minY) * scale});

    ctx.strokeStyle = '#1d3448'; ctx.lineWidth = 1;
    const grid = 100;
    for (let x = Math.ceil(bounds.minX / grid) * grid; x < bounds.maxX; x += grid) {
      const sx = transform({x, y: 0}).x;
      ctx.beginPath(); ctx.moveTo(sx, 0); ctx.lineTo(sx, rect.height); ctx.stroke();
    }
    for (let y = Math.ceil(bounds.minY / grid) * grid; y < bounds.maxY; y += grid) {
      const sy = transform({x: 0, y}).y;
      ctx.beginPath(); ctx.moveTo(0, sy); ctx.lineTo(rect.width, sy); ctx.stroke();
    }

    const first = trace.packetIndex(Math.max(0, current - 0.22));
    const end = trace.packetIndex(current + 0.00001);
    const stride = Math.max(1, Math.ceil((end - first) / 450));
    for (let i = first; i < end; i += stride) {
      const p = trace.packets[i], from = trace.nodes.get(p.from), to = trace.nodes.get(p.to);
      if (!from || !to) continue;
      const a = transform(trace.position(from, p.tx)), b = transform(trace.position(to, p.rx));
      ctx.globalAlpha = Math.max(0.08, 1 - (current - p.rx) / 0.22) * 0.75;
      ctx.strokeStyle = '#6bd8f0'; ctx.lineWidth = 1.3;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    for (const n of trace.nodes.values()) {
      const p = transform(trace.position(n, current));
      const isSelected = selected === n.id;
      if (isSelected) { ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(p.x, p.y, 11, 0, Math.PI * 2); ctx.stroke(); }
      ctx.fillStyle = n.color; ctx.beginPath(); ctx.arc(p.x, p.y, isSelected ? 6 : 4.5, 0, Math.PI * 2); ctx.fill();
      const contested = trace.counter(n, 'ContestedWitnesses', current);
      const revoked = trace.counter(n, 'RevokedWitnesses', current);
      if (contested >= 2) {
        ctx.strokeStyle = '#fbbf24'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(p.x, p.y, 8, 0, Math.PI * 2); ctx.stroke();
      }
      if (revoked >= 1) {
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(p.x - 3, p.y - 3); ctx.lineTo(p.x + 3, p.y + 3);
        ctx.moveTo(p.x + 3, p.y - 3); ctx.lineTo(p.x - 3, p.y + 3); ctx.stroke();
      }
      if (trace.nodes.size <= 60 || isSelected) {
        ctx.fillStyle = '#c7d9e6'; ctx.font = '11px system-ui'; ctx.fillText(String(n.id), p.x + 7, p.y - 6);
      }
    }
  }
  function frame(now) {
    const dt = Math.min(0.1, (now - lastFrame) / 1000); lastFrame = now;
    if (playing) {
      if (following) current = trace.maxTime;
      else current = Math.min(trace.maxTime, current + dt * Number($('speed').value));
      if (!live && current >= trace.maxTime) playing = false;
    }
    draw();
    if (now - lastUi > 160) { lastUi = now; refreshUi(); updateInspector(); updateEvents(); }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  canvas.addEventListener('click', event => {
    if (!transform) return;
    const rect = canvas.getBoundingClientRect();
    let best = 14, id = null;
    for (const n of trace.nodes.values()) {
      const p = transform(trace.position(n, current));
      const distance = Math.hypot(p.x - (event.clientX - rect.left), p.y - (event.clientY - rect.top));
      if (distance < best) { best = distance; id = n.id; }
    }
    selected = id; updateInspector();
  });
  $('play').addEventListener('click', () => {
    if (!playing && current >= trace.maxTime && !live) current = 0;
    playing = !playing;
    if (live && playing) following = true;
    refreshUi();
  });
  $('seek').addEventListener('input', () => {
    current = Number($('seek').value); following = false; playing = false; refreshUi();
  });

  $('files').addEventListener('change', async event => {
    const files = [...event.target.files]; if (!files.length) return;
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    live = false; reset(); status('Reading XML…');
    try {
      files.sort((a, b) => {
        const suffix = file => Number(/-(\d+)$/.exec(file.name)?.[1] || 0);
        return suffix(a) - suffix(b);
      });
      for (const file of files) {
        const reader = file.stream().getReader(), decoder = new TextDecoder();
        while (true) {
          const {value, done} = await reader.read(); if (done) break;
          trace.push(decoder.decode(value, {stream: true}));
        }
        trace.push(decoder.decode());
      }
      trace.finish(); recomputeBounds(); current = 0;
      status(`Loaded ${files.length} NetAnim file${files.length === 1 ? '' : 's'}`);
      refreshUi();
    } catch (error) { status(error.message, 'error'); }
  });
  $('resultFiles').addEventListener('change', async event => {
    try {
      for (const file of event.target.files) addComparison(JSON.parse(await file.text()), file.name);
    } catch (error) { $('compareNote').textContent = error.message; }
    event.target.value = '';
  });
  $('clearCompare').addEventListener('click', () => { comparisons.length = 0; renderComparison(); });

  async function request(path, options) {
    const response = await fetch(path, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Server error ${response.status}`);
    return data;
  }
  function setRunButtons(running) { $('start').disabled = running; $('stop').disabled = !running; }
  async function poll() {
    if (polling) return;
    polling = true;
    try {
      const data = await request(`/api/events?since=${cursor}`);
      if (data.overflow) {
        clearInterval(pollTimer); pollTimer = null; live = false; setRunButtons(false);
        status(data.message, 'error'); $('runInfo').textContent = data.trace;
        return;
      }
      for (const event of data.events) { trace.push(event.xml); cursor = event.seq; }
      if (data.events.length) { bounds = null; if (following) current = trace.maxTime; }
      if (data.result) finalResult = data.result;
      if (data.state === 'running' || data.state === 'commissioning') {
        status(data.state === 'commissioning' ? 'Commissioning models…' : 'Live ns-3 evaluation', 'live');
        $('runInfo').textContent = data.message || '';
      } else if (data.state === 'finished' || data.state === 'failed' || data.state === 'stopped') {
        if (cursor < data.latestSeq) {
          status('Loading remaining native trace…');
          return;
        }
        clearInterval(pollTimer); pollTimer = null; live = false; following = false;
        if (trace.nodes.size) trace.finish();
        setRunButtons(false);
        if (data.state === 'finished' && finalResult) addComparison(finalResult, 'live run');
        status(data.state === 'finished' ? 'Run complete · trace saved' : (data.message || data.state), data.state === 'finished' ? '' : 'error');
        $('runInfo').textContent = data.trace || data.message || '';
      }
    } catch (error) { status(error.message, 'error'); clearInterval(pollTimer); pollTimer = null; setRunButtons(false); }
    finally { polling = false; }
  }
  $('start').addEventListener('click', async () => {
    const config = {
      protocol: $('protocol').value, attack: $('attack').value,
      nodes: Number($('nodes').value), flows: Number($('flows').value),
      malicious: Number($('malicious').value), duration: Number($('duration').value),
      train: $('train').checked, realtime: $('realtime').checked
    };
    if (config.attack === 'none' || config.protocol === 'ns3-aodv') config.malicious = 0;
    if (config.protocol === 'ns3-aodv') config.attack = 'none';
    try {
      if (pollTimer) clearInterval(pollTimer);
      reset(); activeProtocol = config.protocol; cursor = 0; live = true; following = true; playing = true;
      await request('/api/start', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(config)});
      setRunButtons(true); status('Starting ns-3…', 'live');
      pollTimer = setInterval(poll, 350); await poll();
    } catch (error) { live = false; playing = false; setRunButtons(false); status(error.message, 'error'); }
  });
  $('stop').addEventListener('click', async () => { try { await request('/api/stop', {method:'POST'}); await poll(); } catch (error) { status(error.message, 'error'); } });

  async function loadSavedTrace(runId) {
    live = false; following = false; reset(); status('Loading saved NetAnim trace…');
    try {
      const response = await fetch(`/api/trace?run=${encodeURIComponent(runId)}`, {cache:'no-store'});
      if (!response.ok) {
        let message = `Could not load saved trace (${response.status}).`;
        try { message = (await response.json()).error || message; } catch {}
        throw new Error(message);
      }
      const reader = response.body?.getReader();
      if (reader) {
        const decoder = new TextDecoder();
        while (true) {
          const {value, done} = await reader.read(); if (done) break;
          trace.push(decoder.decode(value, {stream:true}));
        }
        trace.push(decoder.decode());
      } else trace.push(await response.text());
      trace.finish(); recomputeBounds(); current = 0;
      try {
        const {runs} = await request('/api/results');
        const saved = (runs || []).find(run => run.id === runId);
        if (saved) {
          finalResult = saved.data; activeProtocol = saved.data.protocol;
          if (finalResult?.engine === 'ns-3') addComparison(finalResult, 'saved run');
        }
      } catch { /* The trace itself remains replayable if result metadata is unavailable. */ }
      playing = trace.nodes.size > 0; following = false;
      status(`Replaying saved trace · ${runId}`);
      $('runInfo').textContent = `Saved trace: ${runId}`;
      refreshUi();
    } catch (error) { status(error.message, 'error'); }
  }

  const savedTraceId = new URLSearchParams(location.search).get('trace');
  if (savedTraceId) loadSavedTrace(savedTraceId);
})();
