const assert = require('node:assert/strict');
const {test} = require('node:test');
const {Trace} = require('./trace.js');

test('reads ns-3.45 wireless packet references and mobility across chunks', () => {
  const trace = new Trace();
  trace.push('<anim><node id="0" locX="10" locY="20"/><node id="1" locX="30" locY="40"/>');
  trace.push('<nu p="d" t="0" id="0" descr="Node 0 | 10.1.0.1 | honest"/>');
  trace.push('<nu p="p" t="2" id="0" x="20" y="30"/><pr uId="8" fId="0" fbTx="1.5" meta-info="UDP &amp; IPv4"/>');
  trace.push('<wpr uId="8" tId="1" fbRx="1.501" lbRx="1.502"/><nu p="c" t="2" id="1" r="239" g="68" b="68"/></anim>');
  trace.finish();
  assert.equal(trace.nodes.size, 2);
  assert.equal(trace.packets.length, 1);
  assert.deepEqual(trace.packets[0], {from: 0, to: 1, tx: 1.5, rx: 1.501, meta: 'UDP & IPv4'});
  assert.deepEqual(trace.position(trace.nodes.get(0), 1), {x: 15, y: 25});
  assert.equal(trace.nodes.get(1).color, 'rgb(239,68,68)');
  assert.equal(trace.packetIndex(1.5), 0);
  assert.equal(trace.packetIndex(1.50101), 1);
});

test('combines split files and accepts older direct packet records', () => {
  const trace = new Trace();
  trace.push('<node id="0" locX="0" locY="0"/><node id="1" locX="1" locY="1"/><pr uId="9" fId="0" fbTx="1"/>');
  trace.push('<wpr uId="9" tId="1" fbRx="1.01"/><wp fId="1" fbTx="2" tId="0" fbRx="2.01"/>');
  trace.finish();
  assert.equal(trace.packets.length, 2);
  assert.deepEqual(trace.packets.map(p => [p.from, p.to]), [[0, 1], [1, 0]]);
});

test('rejects unrelated XML', () => {
  const trace = new Trace(); trace.push('<html><body>example</body></html>');
  assert.throws(() => trace.finish(), /No NetAnim nodes/);
});

test('tracks live native counters at playback time', () => {
  const trace = new Trace();
  trace.push('<node id="0" locX="0" locY="0"/><ncs ncId="4" n="BatteryJ" t="DOUBLE"/>');
  trace.push('<nc c="4" i="0" t="0" v="350"/><nc c="4" i="0" t="2" v="348.5"/>');
  trace.finish();
  assert.equal(trace.counter(trace.nodes.get(0), 'BatteryJ', 1), 350);
  assert.equal(trace.counter(trace.nodes.get(0), 'BatteryJ', 3), 348.5);
  assert.equal(trace.counter(trace.nodes.get(0), 'AppRx', 3), null);
});

test('indexes receptions even when concurrent transmissions overlap', () => {
  const trace = new Trace();
  trace.push('<node id="0" locX="0" locY="0"/><node id="1" locX="1" locY="1"/>');
  trace.push('<pr uId="a" fId="0" fbTx="1"/><pr uId="b" fId="1" fbTx="1.1"/>');
  trace.push('<wpr uId="b" tId="0" fbRx="1.11"/><wpr uId="a" tId="1" fbRx="1.2"/>');
  assert.equal(trace.packetIndex(1.15), 1);
});
