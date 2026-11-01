// Automatic backup never prompts. Explicit exports let the user choose a name.
export function midiUrl(result, base, manual=false) {
  const url=new URL(result.result,base);
  if(manual)url.search='save=1';
  return url.href;
}
export function automaticDownload(result,base,document) {
  const link=document.createElement('a');
  link.href=midiUrl(result,base);link.download=result.filename || '轻量转谱.mid';link.hidden=true;
  document.body.append(link);
  try {link.click();} finally {link.remove();}
}
export async function saveMidi(result,{base,surface,document,fetch,onStatus}) {
  // The desktop host owns its SaveFileDialog; no generic file-system bridge.
  if(surface.NteDesktop?.midiSaveDialog || typeof surface.showSaveFilePicker!=='function') {
    onStatus(surface.NteDesktop?.midiSaveDialog ? '请选择 MIDI 的保存位置和文件名…' : '此浏览器将按下载设置保存；可在浏览器中启用“下载前询问保存位置”。');
    const link=document.createElement('a');
    link.href=midiUrl(result,base,true);link.download=result.filename || '轻量转谱.mid';link.hidden=true;
    document.body.append(link);
    try {link.click();} finally {link.remove();}
    return;
  }
  let stream;
  try {
    const handle=await surface.showSaveFilePicker({suggestedName:result.filename || '轻量转谱.mid',
      id:'nte-midi-export',startIn:'downloads',excludeAcceptAllOption:true,
      types:[{description:'MIDI 曲谱',accept:{'audio/midi':['.mid']}}]});
    const response=await fetch(midiUrl(result,base));
    if(!response.ok)throw Error('读取已保存的 MIDI 失败，请重新打开转谱窗口。');
    const blob=await response.blob();stream=await handle.createWritable();
    await stream.write(blob);await stream.close();stream=null;
    onStatus('MIDI 已另存为：'+handle.name+'。工作台副本已保留。');
  } catch(error) {
    if(stream)await stream.abort().catch(()=>{});
    onStatus(error.name==='AbortError' ? '已取消另存为；工作台副本不受影响。' : '另存失败：'+(error.message || String(error))+' 工作台副本已保留。');
  }
}
