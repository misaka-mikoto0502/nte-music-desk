import assert from 'node:assert/strict';
import {RemainingTime,timeLabel} from './eta.js';
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
