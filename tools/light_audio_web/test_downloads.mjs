import assert from 'node:assert/strict';
import {automaticDownload,saveMidi} from './downloads.js';
const result={result:'results/fixture.mid',filename:'自己的曲谱.mid'},base='http://127.0.0.1:1234/private/';
const clicked=[],document={body:{append(){}},createElement(){return {click(){clicked.push(this.href);},remove(){}};}};
const messages=[],onStatus=text=>messages.push(text);
automaticDownload(result,base,document);
assert.equal(clicked.pop(),base+result.result); // Completion must never open Save As.
await saveMidi(result,{base,document,surface:{NteDesktop:{midiSaveDialog:true},showSaveFilePicker(){assert.fail();}},onStatus});
assert.equal(clicked.pop(),base+result.result+'?save=1');
const bytes=new Blob(['MThd-fixture']);let saved,closed=false,aborted=false;
const stream={async write(blob){saved=await blob.text();},async close(){closed=true;},async abort(){aborted=true;}};
await saveMidi(result,{base,document,onStatus,surface:{async showSaveFilePicker(options){
  assert.equal(options.suggestedName,result.filename);return {name:'自选名称.mid',async createWritable(){return stream;}};
}},async fetch(url){assert.equal(url,base+result.result);return {ok:true,async blob(){return bytes;}};}});
assert.equal(saved,'MThd-fixture');assert.ok(closed && !aborted);assert.match(messages.at(-1),/自选名称.mid/);
await saveMidi(result,{base,document,onStatus,surface:{async showSaveFilePicker(){throw new DOMException('cancel','AbortError');}},fetch(){assert.fail('Cancel must not download again');}});
assert.match(messages.at(-1),/已取消/);assert.equal(clicked.length,0);
closed=false;
await saveMidi(result,{base,document,onStatus,surface:{async showSaveFilePicker(){return {async createWritable(){return {...stream,async write(){throw Error('disk full');}};}};}},
  async fetch(){return {ok:true,async blob(){return bytes;}};}});
assert.ok(aborted && !closed);assert.match(messages.at(-1),/另存失败/);
console.log('Automatic backup, desktop Save As route, browser naming, cancellation and write failure passed');
