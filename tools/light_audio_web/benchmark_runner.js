import fs from 'node:fs';
import path from 'node:path';
import * as tf from '@tensorflow/tfjs-core';
import {loadGraphModel} from '@tensorflow/tfjs-converter';
import {transcribe} from './engine.js';
import {setWasmPaths,setThreadsCount} from '@tensorflow/tfjs-backend-wasm';

async function main() {
  const folder = process.argv[2], modelFolder = process.argv[3];
  const backend=process.argv[4],profile=process.argv[5];
  if(!['cpu','wasm'].includes(backend) || !['polyphonic','melody','detail'].includes(profile)) throw Error('Invalid backend or preset');
  if(backend==='wasm') {
    globalThis.fetch=undefined;setThreadsCount(1);tf.env().set('WASM_HAS_MULTITHREAD_SUPPORT',false);
    setWasmPaths(process.argv[6]+path.sep);
  }
  const manifest = JSON.parse(fs.readFileSync(path.join(modelFolder, 'model.json')));
  const bytes = fs.readFileSync(path.join(modelFolder, 'group1-shard1of1.bin'));
  const results = {};
  for (const name of JSON.parse(fs.readFileSync(path.join(folder, 'manifest.json'))).case_names) {
    const pcm = fs.readFileSync(path.join(folder, name + '.f32'));
    const samples = new Float32Array(pcm.buffer.slice(pcm.byteOffset, pcm.byteOffset + pcm.byteLength));
    await tf.setBackend(backend);
    const model = await loadGraphModel(tf.io.fromMemory({modelTopology: manifest.modelTopology,
      weightSpecs: manifest.weightsManifest.flatMap(g => g.weights),
      weightData: bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)}));
    const started = performance.now();
    const result = await transcribe(samples, model, profile,()=>{},backend);
    results[name] = {...result, seconds: (performance.now() - started) / 1000, tensors_after_dispose: tf.memory().numTensors};
    console.log(name, results[name].seconds.toFixed(2), result.notes.length, 'tensors', tf.memory().numTensors);
    if(tf.memory().numTensors)throw Error('Tensors were not released');
    fs.writeFileSync(path.join(folder, `browser-engine-results-${backend}-${profile}.json`), JSON.stringify(results));
  }
}
main().catch(error => {console.error(error);process.exitCode = 1;});
