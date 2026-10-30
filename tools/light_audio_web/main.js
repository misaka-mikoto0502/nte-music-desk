import {RemainingTime, timeLabel} from './eta.js';
const el = id => document.getElementById(id), base = new URL('.', location.href);
let worker, job, audioUrl, selectedFile, lastResult, lastDesktopId, closed = false, running = false;
let pulseFailures = 0, pulsing = false, generation = 0, selectionVersion = 0, startedAt = 0, phase = 'idle';
const eta = new RemainingTime(), now = () => performance.now() / 1000;
const status = text => {el('status').textContent = text;};
const api = async (route, data) => {
  const response = await fetch(new URL(route, base), {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '本地工作台连接失败。');
  return result;
};
function panel(result) {
  document.body.classList.toggle('show-result', result);
  el('tab-settings').setAttribute('aria-pressed', String(!result));
  el('tab-result').setAttribute('aria-pressed', String(result));
}
el('tab-settings').onclick = () => panel(false);
el('tab-result').onclick = () => panel(true);
function controls(busy) {
  running = busy;
  for (const input of el('form').elements) input.disabled = busy;
  el('cancel').disabled = !busy;
  el('dropzone').setAttribute('aria-disabled', String(busy));
}
function progress(value) {
  value = Math.max(0, Math.min(100, value));
  el('progress').value = value; el('percent').textContent = `${Math.floor(value)}%`;
}
function setPhase(value, caption) { phase = value; el('phase').textContent = caption; }
function timing() {
  if (!startedAt) return;
  if (running) el('elapsed').textContent = '已用时 ' + timeLabel(now() - startedAt);
  if (phase === 'inference') {
    const seconds = eta.remaining(now());
    el('eta').textContent = seconds === null ? '预计剩余：正在测速…' : '预计剩余：约 ' + timeLabel(seconds);
  } else if (running) el('eta').textContent = phase === 'saving' ? '预计剩余：正在保存…' : phase === 'postprocess' ? '预计剩余：正在整理音符…' : '预计剩余：准备中…';
}
function setFile(file) {
  if (running || closed) return;
  if (!file || !file.size || file.size > 64 * 1024 * 1024) throw new Error('请选择不超过 64 MB 的本地音频。');
  if (!/\.(wav|mp3|flac|ogg|m4a|aac|wma|opus|webm)$/i.test(file.name) && !file.type.startsWith('audio/')) throw new Error('请拖入 WAV、MP3、FLAC 等音频文件。');
  selectionVersion++; selectedFile = file;
  if (audioUrl) URL.revokeObjectURL(audioUrl);
  audioUrl = URL.createObjectURL(file); el('audio').src = audioUrl;
  el('file-name').textContent = `${file.name} · ${(file.size / 1048576).toFixed(2)} MB`;
  el('file-name').title = file.name;
  status('音频已就绪。可选择片段，再开始转谱。');
  setPhase('idle', '音频已就绪'); panel(false);
}
function acceptFiles(files) {
  try { if (files.length !== 1) throw new Error('一次请只拖入一个音频文件。'); setFile(files[0]); }
  catch (error) { status(error.message); }
}
el('file').onchange = () => { if (el('file').files.length) acceptFiles(el('file').files); };
el('dropzone').onclick = event => { if (!running && !closed && event.target !== el('file')) el('file').click(); };
el('dropzone').onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (!running && !closed) el('file').click(); } };
let dragDepth = 0;
el('dropzone').ondragenter = event => { event.preventDefault(); if (!running) { dragDepth++; el('dropzone').classList.add('dragging'); } };
el('dropzone').ondragover = event => { event.preventDefault(); event.dataTransfer.dropEffect = running ? 'none' : 'copy'; };
el('dropzone').ondragleave = event => { event.preventDefault(); if (--dragDepth <= 0) el('dropzone').classList.remove('dragging'); };
el('dropzone').ondrop = event => { event.preventDefault(); event.stopPropagation(); dragDepth = 0; el('dropzone').classList.remove('dragging'); if (!running) acceptFiles(event.dataTransfer.files); };
document.addEventListener('dragover', event => event.preventDefault());
document.addEventListener('drop', event => { event.preventDefault(); if (!running) status('请把音频拖到“把音频拖到这里”区域。'); });
function showResult(result, automatic = false) {
  if (!result || !result.result || result.result === lastResult?.result) return;
  lastResult = result;
  const download = el('download');
  download.href = new URL(result.result, base); download.download = result.filename || '轻量转谱.mid'; download.hidden = false;
  el('result-name').textContent = download.download; el('result-name').title = download.download;
  el('download-status').textContent = automatic ? '已发起自动下载。若浏览器拦截，请点击上方按钮；工作台另有已保存副本。' : '工作台已保存副本，可再次点击下载。';
  if (automatic) download.click();
}
async function cancel() {
  generation++;
  if (worker) worker.terminate(); worker = null;
  const oldJob = job; job = null;
  if (oldJob) await api('cancel', {job_id:oldJob}).catch(() => {});
  controls(false); setPhase('cancelled', '已取消'); el('eta').textContent = '任务已取消';
  status('已取消本次计算，未完成的结果不会导入。之前保存的 MIDI 仍可下载。');
}
el('cancel').onclick = cancel;
async function durationOf(file) {
  const audio = new Audio(), url = URL.createObjectURL(file);
  try {
    return await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('读取时长超时，请换用 WAV 或 MP3。')), 10000);
      audio.onloadedmetadata = () => {clearTimeout(timer); resolve(audio.duration);};
      audio.onerror = () => {clearTimeout(timer); reject(new Error('浏览器无法解码此格式，请换用 WAV 或 MP3。'));};
      audio.preload = 'metadata'; audio.src = url;
    });
  } finally {audio.removeAttribute('src'); audio.load(); URL.revokeObjectURL(url);}
}
el('form').onsubmit = async event => {
  event.preventDefault(); if (running || closed) return;
  const current = ++generation, file = selectedFile;
  const check = () => {if (current !== generation || !running) throw new Error('任务已取消。');};
  controls(true); startedAt = now(); progress(0); setPhase('preparing', '读取音频'); panel(true); timing();
  try {
    if (!file) throw new Error('请先选择或拖入一个本地音频。');
    status('正在本机读取音频…');
    const duration = await durationOf(file); check();
    if (!Number.isFinite(duration) || duration <= 0 || duration > 600) throw new Error('源文件支持 10 分钟以内，请先裁短；每次转谱最多 3 分钟。');
    const start = Number(el('start').value), end = el('end').value.trim() ? Number(el('end').value) : Math.min(duration, start + 180);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start || end > duration + .02 || end - start > 180) throw new Error('请选择有效起止秒数，每次最多 3 分钟。');
    const data = await file.arrayBuffer(); check();
    const sha256 = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', data)), b => b.toString(16).padStart(2,'0')).join(''); check();
    const created = await api('begin', {name:file.name,bytes:file.size,duration,start,end,sha256,profile:el('profile').value});
    if (current !== generation || !running) {await api('cancel', {job_id:created.job_id}); return;}
    job = created.job_id;
    const context = new AudioContext(); let decoded;
    try {decoded = await context.decodeAudioData(data);} finally {await context.close();}
    const offline = new OfflineAudioContext(1, Math.ceil((end-start)*22050),22050);
    const source = offline.createBufferSource(); source.buffer = decoded; source.connect(offline.destination); source.start(0,start,end-start);
    const samples = (await offline.startRendering()).getChannelData(0).slice(); check();
    status('正在加载本机计算组件，首次测速后会显示剩余时间。'); setPhase('loading','加载模型');
    worker = new Worker(new URL('worker.js',base));
    worker.onmessage = async ({data}) => {
      if (!job || !running || current !== generation) return;
      if (data.error) {await cancel(); status('转谱失败：'+data.error); return;}
      if (data.phase === 'inference') {
        if (phase !== 'inference') eta.reset(now());
        setPhase('inference', data.backend === 'wasm' ? 'CPU 加速识别' : 'CPU 识别');
        eta.update(data.progress,now()); progress(2+data.progress*94);
        status('正在识别旋律与和弦。可以先处理其他事情，请保留工作台和此页面。');
        if (!pulsing) heartbeat();
      } else if (data.phase === 'postprocess') {setPhase('postprocess','整理音符'); progress(97); status('识别完成，正在整理音符与和弦。');}
      else if (data.phase === 'fallback') {setPhase('loading','兼容模式'); status('加速组件不可用，已自动改用兼容 CPU 模式。');}
      timing();
      if (data.result) {
        worker = null; setPhase('saving','保存 MIDI'); progress(99); timing();
        try {
          const result = await api('complete',{job_id:job,...data.result});
          if (current !== generation) return;
          job = null; controls(false); progress(100); setPhase('complete','已保存');
          el('elapsed').textContent = '总用时 '+timeLabel(now()-startedAt); el('eta').textContent = '已完成';
          showResult(result,true); status(`已生成 ${result.notes} 个音符并送回工作台。请先试听检查错漏音。`);
        } catch (error) {if (current === generation) {await cancel(); status(error.message);}}
      }
    };
    worker.onerror = async error => {if (current === generation) {await cancel(); status('计算组件启动失败：'+error.message);}};
    worker.postMessage({samples,model:new URL('model.json',base).href,profile:el('profile').value},[samples.buffer]);
  } catch (error) {if (current === generation) {await cancel(); status(error.message || String(error));}}
};
async function heartbeat() {
  if (pulsing || closed) return;
  pulsing = true; const currentJob = job;
  try {
    if (currentJob) await api('pulse',{job_id:currentJob});
    else {
      const response = await fetch(new URL('state',base)); if (!response.ok) throw new Error('工作台连接已断开');
      const state = await response.json();
      if (!running) {
        showResult(state.latest_result);
        if (state.desktop_file && state.desktop_file.id !== lastDesktopId) {
          lastDesktopId = state.desktop_file.id; const version = selectionVersion;
          try {
            const audio = await fetch(new URL('input/'+lastDesktopId,base));
            if (!audio.ok) throw new Error((await audio.json()).error || '读取本地音频失败。');
            const blob = await audio.blob();
            if (!running && version === selectionVersion) setFile(new File([blob],state.desktop_file.name,{type:blob.type}));
          } catch (error) {status(error.message || '读取本地音频失败，请重新选择或拖入文件。');}
        }
      }
    }
    pulseFailures = 0;
  } catch (_) {
    if (currentJob && currentJob !== job) return;
    if (++pulseFailures >= 3) {
      if (worker) worker.terminate(); worker = null; job = null; closed = true; controls(false); el('submit').disabled = true;
      setPhase('closed','工作台已关闭'); el('eta').textContent = '连接已断开';
      status('请回到工作台重新打开转谱页面。已生成的文件仍保存在工作台数据目录。');
    }
  } finally {pulsing = false;}
}
setInterval(heartbeat,1500); setInterval(timing,500); heartbeat();
document.addEventListener('visibilitychange',()=>{if (!document.hidden) heartbeat();});
window.addEventListener('pagehide',()=>{
  if (worker) worker.terminate();
  if (job) fetch(new URL('cancel',base),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_id:job}),keepalive:true}).catch(()=>{});
  if (audioUrl) URL.revokeObjectURL(audioUrl);
});
