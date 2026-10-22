/* NetAnim XML reader. The same parser accepts complete files and live XML
 * elements from AnimationInterface::SetAnimWriteCallback. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.NetAnimTrace = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function attributes(tag) {
    const result = {};
    const pattern = /([\w:-]+)\s*=\s*(["'])(.*?)\2/g;
    let match;
    while ((match = pattern.exec(tag))) {
      result[match[1]] = match[3].replace(/&quot;/g, '"').replace(/&apos;/g, "'")
        .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
    }
    return result;
  }

  class Trace {
    constructor() { this.reset(); }
    reset() {
      this.nodes = new Map();
      this.packets = [];
      this.pending = new Map();
      this.counterNames = new Map();
      this.maxTime = 0;
      this.remainder = '';
      this.records = 0;
    }
    node(id) {
      if (!this.nodes.has(id)) this.nodes.set(id, {id, x: 0, y: 0, color: '#4ade80',
        description: `Node ${id}`, motion: [], counters: {}});
      return this.nodes.get(id);
    }
    push(chunk) {
      this.remainder += chunk;
      // XML elements written by ns-3 are single tags; ignore root and closing tags.
      const end = this.remainder.lastIndexOf('>');
      if (end < 0) return;
      const complete = this.remainder.slice(0, end + 1);
      this.remainder = this.remainder.slice(end + 1);
      const tags = complete.match(/<[^>]*>/g) || [];
      for (const tag of tags) this.tag(tag);
    }
    tag(xml) {
      const name = /^<([\w:-]+)/.exec(xml)?.[1];
      if (!name) return;
      const a = attributes(xml);
      const number = (key) => Number(a[key]);
      if (name === 'node') {
        const id = number('id');
        if (!Number.isInteger(id)) return;
        const n = this.node(id);
        n.x = number('locX'); n.y = number('locY');
        if (!n.motion.length && Number.isFinite(n.x) && Number.isFinite(n.y))
          n.motion.push({t: 0, x: n.x, y: n.y});
        if (a.descr) n.description = a.descr;
        if (a.r !== undefined) n.color = `rgb(${a.r},${a.g},${a.b})`;
      } else if (name === 'nu') {
        const id = number('id'), t = number('t');
        if (!Number.isInteger(id) || !Number.isFinite(t)) return;
        const n = this.node(id);
        if (a.p === 'p') {
          const x = number('x'), y = number('y');
          if (Number.isFinite(x) && Number.isFinite(y)) n.motion.push({t, x, y});
        } else if (a.p === 'c') n.color = `rgb(${a.r},${a.g},${a.b})`;
        else if (a.p === 'd') n.description = a.descr || n.description;
        this.maxTime = Math.max(this.maxTime, t);
      } else if (name === 'pr') {
        const id = a.uId, from = number('fId'), tx = number('fbTx');
        if (id === undefined || !Number.isInteger(from) || !Number.isFinite(tx)) return;
        this.pending.set(id, {from, tx, meta: a['meta-info'] || ''});
        if (this.pending.size > 10000) {
          for (const [key, value] of this.pending)
            if (value.tx < tx - 5) this.pending.delete(key);
        }
        this.maxTime = Math.max(this.maxTime, tx);
      } else if (name === 'ncs') {
        if (a.ncId !== undefined && a.n) this.counterNames.set(a.ncId, a.n);
      } else if (name === 'nc') {
        const id = number('i'), t = number('t'), value = number('v');
        const counterName = this.counterNames.get(a.c);
        if (Number.isInteger(id) && Number.isFinite(t) && Number.isFinite(value) && counterName) {
          const n = this.node(id);
          (n.counters[counterName] ||= []).push({t, value});
          this.maxTime = Math.max(this.maxTime, t);
        }
      } else if (name === 'wpr' || name === 'p' || name === 'wp') {
        const reference = this.pending.get(a.uId);
        const from = reference ? reference.from : number('fId');
        const tx = reference ? reference.tx : number('fbTx');
        const to = number('tId'), rx = number('fbRx');
        if (![from, tx, to, rx].every(Number.isFinite) || from === to) return;
        this.packets.push({from, to, tx, rx, meta: reference?.meta || a['meta-info'] || ''});
        this.maxTime = Math.max(this.maxTime, rx);
      }
      this.records++;
    }
    finish() {
      for (const n of this.nodes.values()) n.motion.sort((a, b) => a.t - b.t);
      for (const n of this.nodes.values())
        for (const series of Object.values(n.counters)) series.sort((a, b) => a.t - b.t);
      this.packets.sort((a, b) => a.rx - b.rx);
      if (!this.nodes.size) throw new Error('No NetAnim nodes found in the selected XML.');
    }
    position(node, t) {
      const motion = node.motion;
      if (!motion.length) return {x: node.x, y: node.y};
      let low = 0, high = motion.length;
      while (low < high) {
        const mid = (low + high) >> 1;
        if (motion[mid].t <= t) low = mid + 1;
        else high = mid;
      }
      const left = motion[Math.max(0, low - 1)], right = motion[Math.min(motion.length - 1, low)];
      if (left === right || right.t <= left.t) return {x: left.x, y: left.y};
      const fraction = Math.max(0, Math.min(1, (t - left.t) / (right.t - left.t)));
      return {x: left.x + (right.x - left.x) * fraction,
        y: left.y + (right.y - left.y) * fraction};
    }
    packetIndex(t) {
      let low = 0, high = this.packets.length;
      while (low < high) {
        const mid = (low + high) >> 1;
        if (this.packets[mid].rx < t) low = mid + 1;
        else high = mid;
      }
      return low;
    }
    counter(node, name, t) {
      const series = node?.counters[name];
      if (!series?.length) return null;
      let low = 0, high = series.length;
      while (low < high) {
        const mid = (low + high) >> 1;
        if (series[mid].t <= t) low = mid + 1;
        else high = mid;
      }
      return low ? series[low - 1].value : null;
    }
  }
  return {Trace};
});
