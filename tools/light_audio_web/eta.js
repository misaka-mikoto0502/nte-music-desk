// Derive time from completed work, rather than inventing loading progress.
export class RemainingTime {
  constructor() { this.reset(0); }
  reset(now) { this.fraction = 0; this.at = now; this.rate = null; this.interval = 0; }
  update(fraction, now) {
    if (!Number.isFinite(fraction) || !Number.isFinite(now) || fraction <= this.fraction || fraction > 1 || now <= this.at) return;
    const elapsed = now - this.at, measured = elapsed / (fraction - this.fraction);
    this.rate = this.rate === null ? measured : this.rate * .65 + measured * .35;
    this.interval = elapsed; this.fraction = fraction; this.at = now;
  }
  remaining(now) {
    if (this.rate === null || this.fraction >= 1 || now - this.at > Math.max(20, this.interval * 3)) return null;
    return Math.max(1, Math.ceil((1 - this.fraction) * this.rate - Math.min(now - this.at, this.interval)));
  }
}
export function timeLabel(seconds) {
  seconds = Math.max(0, Math.ceil(seconds));
  return seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

export function timeRangeLabel(low, high) {
  low = Math.max(1, Math.ceil(low)); high = Math.max(low, Math.ceil(high));
  if (low === high) return timeLabel(low);
  return high < 60 ? `${low}–${high} 秒` : `${timeLabel(low)}–${timeLabel(high)}`;
}

// Initial ranges are deliberately coarse, not a promise about a particular CPU.
// Once decoding makes progress, use its actual throughput to revise the range.
export class ConversionEstimate {
  constructor() { this.reset(0); }
  reset(now) {
    this.inference = new RemainingTime(); this.inference.reset(now);
    this.postprocess = new RemainingTime(); this.postprocess.reset(now);
    this.phase = 'preparing'; this.phaseAt = now; this.duration = 0;
  }
  update(event, now) {
    if (Number.isFinite(event.audioSeconds) && event.audioSeconds > 0) this.duration = event.audioSeconds;
    const phase = event.phase === 'fallback' ? 'loading' : event.phase;
    if (phase !== this.phase) {
      this.phase = phase; this.phaseAt = now;
      if (phase === 'inference') this.inference.reset(now);
      if (phase === 'postprocess') this.postprocess.reset(now);
    }
    if (phase === 'inference') this.inference.update(event.progress, now);
    if (phase === 'postprocess') this.postprocess.update(event.progress, now);
  }
  finishingRange() {
    const scale = Math.max(1, this.duration / 30);
    return [10 * scale, 20 * scale]; // Includes final MIDI save and handoff.
  }
  label(now) {
    const prefix = '预计剩余：', elapsed = Math.max(0, now - this.phaseAt);
    if (this.phase === 'inference') {
      const seconds = this.inference.remaining(now), [low, high] = this.finishingRange();
      return seconds === null ? `${prefix}识别测速中；整理保存约 ${timeRangeLabel(low, high)}`
        : `${prefix}约 ${timeRangeLabel(seconds + low, seconds + high)}（含整理与保存）`;
    }
    if (this.phase === 'postprocess') {
      if (this.postprocess.fraction >= 1) return `${prefix}约 1–5 秒（保存）`;
      const measured = this.postprocess.remaining(now);
      if (measured !== null) return `${prefix}约 ${timeRangeLabel(measured * .7 + 1, measured * 1.4 + 5)}（含保存）`;
      const [low, high] = this.finishingRange();
      // Do not count down to zero when dense notes or a slow machine exceed the
      // initial range. Keep the stage visible until real progress arrives.
      if (elapsed >= high) return `${prefix}正在重新估计，仍在整理曲谱…`;
      return `${prefix}约 ${timeRangeLabel(low - elapsed, high - elapsed)}（含保存）`;
    }
    if (this.phase === 'saving') return elapsed >= 5 ? `${prefix}保存耗时较长，仍在处理…`
      : `${prefix}约 ${timeRangeLabel(1, 5 - elapsed)}`;
    if (this.phase === 'cancelling') return '正在取消…';
    return `${prefix}准备中…`;
  }
}
