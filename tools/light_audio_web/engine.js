// Portions derived from Spotify Basic Pitch, Copyright 2022 Spotify AB,
// Apache-2.0. NTE changes: stream one window at a time, dispose tensors,
// CPU-only runtime, selectable weak-note filtering, bounded clip output.
import * as tf from '@tensorflow/tfjs-core';
import {loadGraphModel} from '@tensorflow/tfjs-converter';
import '@tensorflow/tfjs-backend-cpu';
import {noteFramesToTime, outputToNotesPoly} from '@spotify/basic-pitch/esm/toMidi.js';

export async function transcribe(samples, modelOrUrl, profile, progress = () => {}, backend = 'cpu') {
  await tf.setBackend(backend);
  await tf.ready();
  const model = typeof modelOrUrl === 'string' ? await loadGraphModel(modelOrUrl) : modelOrUrl;
  const windowSize = 43844, overlap = 7680, hop = windowSize - overlap;
  const frames = [], onsets = [];
  const frameLimit = Math.floor(samples.length * 86 / 22050);
  progress(0, {phase: 'inference', backend});
  try {
    for (let offset = 0; offset < samples.length + overlap / 2 && frames.length < frameLimit; offset += hop) {
      const window = new Float32Array(windowSize);
      const start = offset - overlap / 2;
      const from = Math.max(0, start), to = Math.min(samples.length, start + windowSize);
      if (to > from) window.set(samples.subarray(from, to), from - start);
      const values = tf.tidy(() => {
        const input = tf.tensor3d(window, [1, windowSize, 1]);
        return model.execute(input, ['Identity_1', 'Identity_2']).map(t =>
          tf.reshape(tf.slice(t, [0, 15, 0], [1, t.shape[1] - 30, -1]), [t.shape[1] - 30, 88]));
      });
      try {
        const output = values.map(t => t.dataSync());
        for (let i = 0; i < values[0].shape[0] && frames.length < frameLimit; i++) {
          frames.push(Array.from(output[0].subarray(i * 88, (i + 1) * 88)));
          onsets.push(Array.from(output[1].subarray(i * 88, (i + 1) * 88)));
        }
      } finally { tf.dispose(values); }
      progress(Math.min(1, frames.length / frameLimit), {phase: 'inference', backend});
      await new Promise(resolve => setTimeout(resolve, 0));
    }
    progress(1, {phase: 'postprocess', backend});
    const detailed = profile === 'detail';
    const raw = noteFramesToTime(outputToNotesPoly(frames, onsets, .5, .3, detailed ? 7 : 11, true, null, null, true));
    const notes = noteFramesToTime(outputToNotesPoly(frames, onsets, detailed ? .55 : .7, detailed ? .3 : .4, detailed ? 7 : 11, true, null, null, false))
      .filter(note => profile !== 'melody' || note.amplitude >= .55);
    const seconds = samples.length / 22050;
    const clip = list => list.map(n => ({...n, startTimeSeconds: Math.max(0, n.startTimeSeconds),
      durationSeconds: Math.min(seconds, n.startTimeSeconds + n.durationSeconds) - Math.max(0, n.startTimeSeconds)}))
      .filter(n => n.durationSeconds > 0 && n.startTimeSeconds < seconds);
    return {notes: clip(notes), raw_notes: clip(raw), tensors_after_windows: tf.memory().numTensors};
  } finally { model.dispose(); }
}
