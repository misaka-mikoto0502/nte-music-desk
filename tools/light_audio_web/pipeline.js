// One production conversion path shared by the desktop window and browser.
export function validateFile(file) {
  if (!file || !file.size || file.size > 64*1024*1024) throw Error('请选择不超过 64 MB 的本地音频。');
  if (!/\.(wav|mp3|flac|ogg|m4a|aac|wma|opus|webm)$/i.test(file.name) && !file.type?.startsWith('audio/')) throw Error('请拖入 WAV、MP3、FLAC 等音频文件。');
}
export function settingsFor(duration, values={}) {
  if (!Number.isFinite(duration) || duration<=0 || duration>600) throw Error('源文件支持 10 分钟以内，请先裁短；每次转谱最多 3 分钟。');
  const start=Number(values.start ?? 0), end=values.end==null || values.end==='' ? Math.min(duration,start+180) : Number(values.end);
  if (!Number.isFinite(start) || !Number.isFinite(end) || start<0 || end<=start || end>duration+.02 || end-start>180) throw Error('请选择有效起止秒数，每次最多 3 分钟。');
  const profile=values.profile ?? 'polyphonic',align_ms=values.align_ms ?? 0;
  if (!['polyphonic','melody','detail'].includes(profile) || ![0,24].includes(align_ms)) throw Error('识别设置无效。');
  return {start,end,profile,align_ms};
}
function check(signal) {if(signal?.aborted)throw new DOMException('任务已取消。','AbortError');}
function abortable(promise,signal) {
  if(!signal)return promise;
  check(signal);
  return new Promise((resolve,reject)=> {
    const abort=()=>reject(new DOMException('任务已取消。','AbortError'));
    signal.addEventListener('abort',abort,{once:true});
    promise.then(resolve,reject).finally(()=>signal.removeEventListener('abort',abort));
  });
}
async function durationOf(file,signal) {
  const audio=new Audio(),url=URL.createObjectURL(file);let timer;
  try {
    return await abortable(new Promise((resolve,reject)=> {
      timer=setTimeout(()=>reject(Error('读取时长超时，请换用 WAV 或 MP3。')),10000);
      audio.onloadedmetadata=()=>resolve(audio.duration);
      audio.onerror=()=>reject(Error('无法解码此格式，请换用 WAV 或 MP3。'));
      audio.preload='metadata';audio.src=url;
    }),signal);
  } finally {clearTimeout(timer);audio.removeAttribute('src');audio.load();URL.revokeObjectURL(url);}
}
export async function convertFile(file,values={},options={}) {
  const {signal,onEvent=()=>{},onJob=()=>{}}=options;
  const base=new URL(options.base ?? '.',location.href);
  let job=null,worker=null,completed=false;
  const api=async(route,data)=> {
    const response=await fetch(new URL(route,base),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),signal:AbortSignal.timeout(15000)});
    const result=await response.json();
    if(!response.ok)throw Error(result.error || '本地工作台连接失败。');
    return result;
  };
  const emit=event=> {check(signal);onEvent(event);};
  try {
    validateFile(file);check(signal);emit({phase:'preparing'});
    const duration=await durationOf(file,signal),settings=settingsFor(duration,values);
    const data=await abortable(file.arrayBuffer(),signal);
    const hash=await abortable(crypto.subtle.digest('SHA-256',data),signal);
    const sha256=Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,'0')).join('');
    const created=await api('begin',{name:file.name,bytes:file.size,duration,...settings,sha256});
    job=created.job_id;onJob(job);check(signal);
    const context=new AudioContext();let decoded;
    try {decoded=await abortable(context.decodeAudioData(data),signal);} finally {await context.close();}
    check(signal);
    const offline=new OfflineAudioContext(1,Math.ceil((settings.end-settings.start)*22050),22050);
    const source=offline.createBufferSource();source.buffer=decoded;source.connect(offline.destination);source.start(0,settings.start,settings.end-settings.start);
    const samples=(await abortable(offline.startRendering(),signal)).getChannelData(0).slice();
    emit({phase:'loading'});
    const output=await new Promise((resolve,reject)=> {
      worker=new Worker(new URL('worker.js',base));
      const abort=()=>{worker.terminate();reject(new DOMException('任务已取消。','AbortError'));};
      signal?.addEventListener('abort',abort,{once:true});
      const finish=(fn,value)=>{signal?.removeEventListener('abort',abort);fn(value);};
      worker.onmessage=({data})=> {
        if(signal?.aborted)return;
        if(data.error)finish(reject,Error('转谱失败：'+data.error));
        else if(data.result)finish(resolve,data.result);
        else emit(data);
      };
      worker.onerror=error=>finish(reject,Error('计算组件启动失败：'+error.message));
      worker.postMessage({samples,model:new URL('model.json',base).href,profile:settings.profile},[samples.buffer]);
    });
    emit({phase:'saving'});
    // Once accepted by the server, saving wins over a late cancel; keep the file.
    const result=await api('complete',{job_id:job,...output});
    completed=true;return result;
  } finally {
    worker?.terminate();
    if(job && !completed)await api('cancel',{job_id:job}).catch(()=>{});
    onJob(null);
  }
}
