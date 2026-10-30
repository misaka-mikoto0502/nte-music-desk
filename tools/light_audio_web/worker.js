import {transcribe} from './engine.js';
import * as tf from '@tensorflow/tfjs-core';
import {setWasmPaths, setThreadsCount} from '@tensorflow/tfjs-backend-wasm';
self.onmessage = async ({data}) => {
  try {
    self.postMessage({phase: 'loading'});
    let backend = 'cpu';
    try {
      setThreadsCount(1);
      tf.env().set('WASM_HAS_MULTITHREAD_SUPPORT', false);
      setWasmPaths(new URL('.', data.model).href);
      if (await tf.setBackend('wasm')) {await tf.ready(); backend = 'wasm';}
      else self.postMessage({phase: 'fallback'});
    } catch (_) {self.postMessage({phase: 'fallback'});}
    const report = (progress, meta) => self.postMessage({progress, ...meta});
    let result;
    try {result = await transcribe(data.samples, data.model, data.profile, report, backend);}
    catch (error) {
      if (backend !== 'wasm') throw error;
      self.postMessage({phase: 'fallback'});
      result = await transcribe(data.samples, data.model, data.profile, report, 'cpu');
    }
    self.postMessage({result});
  } catch (error) { self.postMessage({error: error.message || String(error)}); }
  self.close();
};
