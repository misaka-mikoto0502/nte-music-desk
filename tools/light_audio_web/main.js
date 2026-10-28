const el = id => document.getElementById(id);
const base = new URL('.', location.href);
let worker, job, audioUrl, closed = false, running = false, pulseFailures = 0, generation = 0;
const status = text => {el('status').textContent = text;};
const api = async (route, data) => {
  const response = await fetch(new URL(route, base), {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '本地工作台连接失败。');
  return result;
};
function controls(busy) {
  running = busy;
  for (const input of el('form').elements) input.disabled = busy;
  el('cancel').disabled = !busy;
}
async function cancel() {
  generation++;
  if (worker) worker.terminate();
  worker = null;
  if (job) await api('cancel', {job_id: job}).catch(() => {});
  job = null; controls(false); status('任务已取消，未导入未完成的曲谱。');
}
el('cancel').onclick = cancel;
el('file').onchange = () => {
  el('download').hidden = true;
  if (audioUrl) URL.revokeObjectURL(audioUrl);
  const file = el('file').files[0];
  if (file) {audioUrl = URL.createObjectURL(file); el('audio').src = audioUrl;}
  status(file ? '已选择本地音频，可直接生成曲谱。' : '请选择本地音频文件。');
};
async function durationOf(file) {
  const audio = new Audio(); const url = URL.createObjectURL(file);
  try {
    return await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('读取音频时长超时，请换用 WAV 或 MP3。')), 10000);
      audio.onloadedmetadata = () => {clearTimeout(timer); resolve(audio.duration);};
      audio.onerror = () => {clearTimeout(timer); reject(new Error('浏览器无法解码此格式，请换用 WAV 或 MP3。'));};
      audio.preload = 'metadata'; audio.src = url;
    });
  } finally {audio.removeAttribute('src'); audio.load(); URL.revokeObjectURL(url);}
}
el('form').onsubmit = async event => {
  event.preventDefault();
  if (running || closed) return;
  const current = ++generation;
  const check = () => {if (current !== generation || !running) throw new Error('任务已取消。');};
  el('download').hidden = true; controls(true); el('progress').value = 0;
  try {
    const file = el('file').files[0];
    if (!file || !file.size || file.size > 64 * 1024 * 1024) throw new Error('请选择不超过 64 MB 的本地音频。');
    status('正在本机读取音频…');
    const duration = await durationOf(file);
    check();
    if (!Number.isFinite(duration) || duration <= 0 || duration > 600) throw new Error('轻量模式支持 10 分钟以内的源文件，请先裁短；每次转谱最多 3 分钟。');
    const start = Number(el('start').value), end = el('end').value.trim() ? Number(el('end').value) : Math.min(duration, start + 180);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start || end > duration + .02 || end - start > 180) throw new Error('请填写有效起止秒数，每次最多 3 分钟。');
    const data = await file.arrayBuffer();
    check();
    const sha256 = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', data)), b => b.toString(16).padStart(2, '0')).join('');
    const profile = el('profile').value;
    check();
    const info = {name: file.name, bytes: file.size, duration, start, end, sha256, profile};
    const created = await api('begin', info);
    if (current !== generation || !running) {await api('cancel', {job_id: created.job_id}); return;}
    job = created.job_id;
    const context = new AudioContext();
    let decoded;
    try {decoded = await context.decodeAudioData(data);} finally {await context.close();}
    const offline = new OfflineAudioContext(1, Math.ceil((end - start) * 22050), 22050);
    const source = offline.createBufferSource(); source.buffer = decoded;
    source.connect(offline.destination); source.start(0, start, end - start);
    const samples = (await offline.startRendering()).getChannelData(0).slice();
    if (!job || !running || current !== generation) return;
    status('正在 CPU 转谱，可随时取消；复杂混音可能出现错漏音。');
    worker = new Worker(new URL('worker.js', base));
    worker.onmessage = async ({data}) => {
      if (!job || !running || current !== generation) return;
      if (data.error) {await cancel(); status('转谱失败：' + data.error); return;}
      if (data.progress !== undefined) el('progress').value = data.progress * 100;
      if (data.result) {
        worker = null;
        try {
          const result = await api('complete', {job_id: job, ...data.result});
          if (current !== generation) return;
          job = null; controls(false); el('progress').value = 100;
          el('download').href = new URL(result.result, base); el('download').hidden = false;
          status(`已生成 ${result.notes} 个音符并送回工作台。请先试听；这不是经过验证的 90–95% 准确率承诺。`);
        } catch (error) {if (current === generation) {await cancel(); status(error.message);}}
      }
    };
    worker.onerror = async error => {if (current === generation) {await cancel(); status('计算组件启动失败：' + error.message);}};
    worker.postMessage({samples, model: new URL('model.json', base).href, profile}, [samples.buffer]);
  } catch (error) {if (current === generation) {await cancel(); status(error.message || String(error));}}
};
setInterval(async () => {
  try {
    if (job) await api('pulse', {job_id: job});
    else if (!(await fetch(new URL('state', base))).ok) throw new Error();
    pulseFailures = 0;
  } catch (_) {
    if (++pulseFailures < 3) return;
    if (worker) worker.terminate(); worker = null; job = null; closed = true;
    controls(false); el('submit').disabled = true;
    status('工作台已关闭或任务过期，请回到软件重新打开轻量转谱。');
  }
}, 1500);
window.addEventListener('pagehide', () => {if (worker) worker.terminate();});
