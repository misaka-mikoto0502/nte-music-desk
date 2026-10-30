import assert from 'node:assert/strict';
import {RemainingTime,timeLabel} from './eta.js';
import {withCpuFallback} from './runtime.js';
const eta=new RemainingTime();eta.reset(0);
assert.equal(eta.remaining(3),null);
eta.update(.25,10);assert.equal(eta.remaining(10),30);
eta.update(.5,20);assert.equal(eta.remaining(25),15);
eta.update(.4,21);assert.equal(eta.fraction,.5);
assert.equal(eta.remaining(60),null); // Stalled work must not promise zero seconds.
eta.update(1,61);assert.equal(eta.remaining(61),null);
eta.reset(100);assert.equal(eta.remaining(101),null);
eta.update(.1,110);const early=eta.remaining(110);
eta.update(.2,111);assert.ok(eta.remaining(111)<early);
assert.equal(timeLabel(61.1),'1 分 2 秒');
console.log('Remaining-time warm-up, rate changes, stale progress and reset passed');
for (const prepare of [async()=>false, async()=>{throw new Error('missing wasm');}]) {
  const calls=[];let warnings=0;
  assert.equal(await withCpuFallback(prepare,async backend=>{calls.push(backend);return 42;},()=>warnings++),42);
  assert.deepEqual(calls,['cpu']);assert.equal(warnings,1);
}
const calls=[];let warnings=0;
assert.equal(await withCpuFallback(async()=>true,async backend=>{
  calls.push(backend);if(backend==='wasm')throw new Error('runtime failure');return 7;
},()=>warnings++),7);
assert.deepEqual(calls,['wasm','cpu']);assert.equal(warnings,1);
await assert.rejects(withCpuFallback(async()=>false,async()=>{throw new Error('cpu failed');},()=>{}),/cpu failed/);
assert.equal(await withCpuFallback(async()=>true,async backend=>backend,()=>{throw Error('unexpected fallback');}),'wasm');
console.log('Missing/failed WASM, runtime retry, CPU failure and accelerated success passed');
