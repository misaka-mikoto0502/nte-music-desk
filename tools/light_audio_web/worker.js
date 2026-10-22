import {transcribe} from './engine.js';
self.onmessage = async ({data}) => {
  try {
    const result = await transcribe(data.samples, data.model, data.profile,
      progress => self.postMessage({progress}));
    self.postMessage({result});
  } catch (error) { self.postMessage({error: error.message || String(error)}); }
  self.close();
};
