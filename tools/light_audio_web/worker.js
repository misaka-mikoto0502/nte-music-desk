import {transcribe} from './engine.js';
import * as tf from '@tensorflow/tfjs-core';
import {setWasmPaths, setThreadsCount} from '@tensorflow/tfjs-backend-wasm';
import {withCpuFallback} from './runtime.js';
self.onmessage = async ({data}) => {
  try {
    self.postMessage({phase: 'loading'});
    const result = await withCpuFallback(async () => {
      setThreadsCount(1);
      tf.env().set('WASM_HAS_MULTITHREAD_SUPPORT', false);
      setWasmPaths(new URL('.', data.model).href);
      if (!await tf.setBackend('wasm')) return false;
      await tf.ready(); return true;
    }, backend => transcribe(data.samples, data.model, data.profile,
      (progress, meta) => self.postMessage({progress, ...meta}), backend),
    () => self.postMessage({phase: 'fallback'}));
    self.postMessage({result});
  } catch (error) { self.postMessage({error: error.message || String(error)}); }
  self.close();
};
