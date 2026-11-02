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
