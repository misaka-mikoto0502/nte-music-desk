import assert from 'node:assert/strict';
import {validateFile} from './pipeline.js';

// Run the actual page handlers with a controlled clock and asynchronous worker.
// No model, browser, network or wall-clock sleeps are needed for long stages.
const keys=['document','window','location','performance','NteAudio','fetch','setInterval'];
const originals=new Map(keys.map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
const elements=new Map(),timers=new Map(),downloads=[];
let clock=100,worker,finish;
const element=id=>{
  if(!elements.has(id))elements.set(id,{value:'',textContent:'',disabled:false,hidden:false,dataset:{},
    setAttribute(){},replaceChildren(){},append(){},classList:{add(){},remove(){},toggle(){}},click(){},remove(){}});
  return elements.get(id);
};
try {
  globalThis.document={getElementById:element,querySelectorAll:()=>[],addEventListener(){},
    body:{append(){},classList:{toggle(){}}},createElement(){return {click(){downloads.push(this.href);},remove(){}};}};
  globalThis.window={addEventListener(){}};
  globalThis.location={href:'http://127.0.0.1:1234/local/'};
  Object.defineProperty(globalThis,'performance',{value:{now:()=>clock*1000},configurable:true});
  globalThis.fetch=async()=>({ok:true,json:async()=>({open:true})});
  globalThis.setInterval=(callback,interval)=>{timers.set(interval,callback);return interval;};
  globalThis.NteAudio={validateFile,convertFile(file,settings,options){
    assert.equal(file.name,'自己的短句.wav');
    worker=options.onEvent;options.onJob('fixture');
    return new Promise((resolve,reject)=>{
      finish=resolve;
      options.signal.addEventListener('abort',()=>reject(new DOMException('cancel','AbortError')),{once:true});
    }).finally(()=>options.onJob(null));
  }};
  element('form').elements=[element('file'),element('start'),element('end'),element('profile'),element('align')];
  element('profile').value='polyphonic';element('end').value='20';
  await import('./main.js');
  element('file').files=[new File(['fixture'],'自己的短句.wav',{type:'audio/wav'})];
  element('file').onchange();
  const submission=element('form').onsubmit({preventDefault(){}});
  worker({phase:'inference',progress:0,audioSeconds:20});
  clock=110;worker({phase:'inference',progress:.25});
  assert.match(element('eta').textContent,/40–50 秒（含整理与保存）/);
  clock=140;worker({phase:'postprocess',progress:0});
  assert.equal(element('phase').textContent,'整理曲谱');
  assert.match(element('eta').textContent,/10–20 秒（含保存）/);
  clock=161;timers.get(500)();
  assert.match(element('eta').textContent,/重新估计/);
  assert.ok(element('progress').value<100);
  assert.equal(element('cancel').disabled,false);
  clock=165;worker({phase:'postprocess',progress:1/3});
  assert.match(element('eta').textContent,/约 .*（含保存）/);
  clock=180;worker({phase:'postprocess',progress:1});worker({phase:'saving'});
  assert.equal(element('cancel').disabled,true);
  assert.equal(element('progress').value,99);
  finish({result:'results/fixture.mid',filename:'自己的短句.mid',notes:16});
  await submission;
  assert.equal(element('progress').value,100);
  assert.equal(element('eta').textContent,'已完成');
  assert.equal(downloads.length,1);
  clock=190;timers.get(500)();assert.equal(element('eta').textContent,'已完成');
  clock=200;
  const next=element('form').onsubmit({preventDefault(){}});
  worker({phase:'postprocess',progress:0,audioSeconds:15});
  assert.match(element('eta').textContent,/10–20 秒/);
  element('cancel').onclick();timers.get(500)();
  assert.equal(element('eta').textContent,'正在取消…');
  await next;
  timers.get(500)();assert.equal(element('eta').textContent,'任务已取消');
  assert.equal(downloads.length,1);
  console.log('Production page ETA, delayed postprocessing, save completion, next task and cancellation passed');
} finally {
  for(const [key,descriptor] of originals) {
    if(descriptor)Object.defineProperty(globalThis,key,descriptor);
    else delete globalThis[key];
  }
}
