import assert from 'node:assert/strict';
import {RemainingTime,timeLabel,timeRangeLabel,ConversionEstimate} from './eta.js';
import {withCpuFallback} from './runtime.js';
import {validateFile,settingsFor} from './pipeline.js';
await import('./test_downloads.mjs');
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
assert.equal(timeRangeLabel(10,20),'10–20 秒');
assert.equal(timeRangeLabel(58,65),'58 秒–1 分 5 秒');
const total = new ConversionEstimate();total.reset(0);
total.update({phase:'inference',progress:0,audioSeconds:20},0);
assert.match(total.label(1),/识别测速中；整理保存约 10–20 秒/);
total.update({phase:'inference',progress:.25},10);
assert.match(total.label(10),/40–50 秒（含整理与保存）/);
total.update({phase:'postprocess',progress:0},40);
assert.match(total.label(40),/10–20 秒（含保存）/);
assert.match(total.label(45),/5–15 秒/);
assert.match(total.label(61),/正在重新估计，仍在整理曲谱/);
assert.doesNotMatch(total.label(61),/约 0 秒/);
total.update({phase:'postprocess',progress:1/3},65);
assert.match(total.label(65),/预计剩余：约 .*（含保存）/);
assert.doesNotMatch(total.label(65),/重新估计/);
total.update({phase:'postprocess',progress:1},80);
assert.match(total.label(80),/1–5 秒（保存）/);
total.update({phase:'saving'},80);
assert.equal(total.label(81),'预计剩余：约 1–4 秒');
assert.match(total.label(86),/保存耗时较长/);
total.update({phase:'cancelling'},87);assert.equal(total.label(87),'正在取消…');
total.reset(100);total.update({phase:'inference',progress:0,audioSeconds:180},100);
assert.match(total.label(101),/1 分 0 秒–2 分 0 秒/); // Longer clips get a larger finishing reserve.
total.update({phase:'fallback'},102);total.update({phase:'inference',progress:0},103);
assert.match(total.label(103),/测速中/); // Failed accelerated work cannot contaminate the CPU estimate.
total.reset(200);total.update({phase:'postprocess',progress:0,audioSeconds:15},200);
assert.match(total.label(200),/10–20 秒/); // A second conversion has no previous countdown.
console.log('End-to-end ETA includes finishing, postprocess ranges, measured updates, overruns, CPU retry and reset passed');
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
assert.doesNotThrow(()=>validateFile({name:'自己的歌曲.MP3',size:100,type:''}));
for(const file of [null,{name:'bad.exe',size:100},{name:'x.wav',size:0},{name:'x.wav',size:65*1024*1024}])assert.throws(()=>validateFile(file));
assert.deepEqual(settingsFor(200,{start:'30',end:'',profile:'detail',align_ms:24}),{start:30,end:200,profile:'detail',align_ms:24});
for(const duration of [0,601,NaN,Infinity])assert.throws(()=>settingsFor(duration));
for(const values of [{start:-1},{end:11},{start:10},{profile:'bad'},{align_ms:true}])assert.throws(()=>settingsFor(10,values));
assert.deepEqual(settingsFor(300),{start:0,end:180,profile:'polyphonic',align_ms:0});
console.log('Shared file bounds, clip defaults, presets and alignment validation passed');
await import('./test_progress.mjs');
