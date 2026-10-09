import { niceCeil } from "../decode";

export interface Series {
  name: string;
  color: string;
  steps: number[];
  values: number[];
}

export interface Marker {
  step: number;
  label: string;
}

const INK = "#ffffff";
const INK2 = "#c3c2b7";
const MUTED = "#898781";
const GRID = "#2c2c2a";
const FONT = "12px system-ui, sans-serif";

/** Minimal canvas line chart: it plots exactly the series it is given. */
export class LineChart {
  private series: Series[] = [];
  private markers: Marker[] = [];
  private hoverStep: number | null = null;
  private plot = { left: 46, right: 56, top: 14, bottom: 30, width: 0, height: 0, xMax: 1, yMax: 10 };

  constructor(private canvas: HTMLCanvasElement, private tooltip: HTMLElement) {
    canvas.addEventListener("pointermove", (e) => this.onHover(e));
    canvas.addEventListener("pointerleave", () => {
      this.hoverStep = null;
      this.tooltip.hidden = true;
      this.draw();
    });
    new ResizeObserver(() => this.draw()).observe(canvas);
  }

  setData(series: Series[], markers: Marker[]): void {
    this.series = series;
    this.markers = markers;
    this.draw();
  }

  private x(step: number): number {
    return this.plot.left + (step / this.plot.xMax) * this.plot.width;
  }

  private y(value: number): number {
    return this.plot.top + this.plot.height - (value / this.plot.yMax) * this.plot.height;
  }

  private valueAt(s: Series, step: number): number | null {
    if (s.steps.length === 0 || step > s.steps[s.steps.length - 1]) return null;
    let i = 0;
    while (i < s.steps.length - 1 && s.steps[i + 1] <= step) i++;
    return s.values[i];
  }

  private onHover(e: PointerEvent): void {
    const rect = this.canvas.getBoundingClientRect();
    const frac = (e.clientX - rect.left - this.plot.left) / this.plot.width;
    if (frac < 0 || frac > 1 || this.series.every((s) => s.steps.length < 2)) {
      this.hoverStep = null;
      this.tooltip.hidden = true;
    } else {
      this.hoverStep = Math.round(frac * this.plot.xMax);
      const title = document.createElement("div");
      title.className = "tt-title";
      title.textContent = `step ${this.hoverStep}`;
      const rows = this.series.map((s) => {
        const v = this.valueAt(s, this.hoverStep!);
        const row = document.createElement("div");
        const swatch = document.createElement("i");
        swatch.style.background = s.color;
        const value = document.createElement("b");
        value.textContent = v === null ? "—" : String(v);
        row.append(swatch, s.name, value);
        return row;
      });
      this.tooltip.replaceChildren(title, ...rows);
      this.tooltip.hidden = false;
      const left = Math.min(e.clientX - rect.left + 14, rect.width - this.tooltip.offsetWidth - 4);
      this.tooltip.style.left = `${Math.max(0, left)}px`;
      this.tooltip.style.top = `${this.plot.top + 4}px`;
    }
    this.draw();
  }

  draw(): void {
    const dpr = window.devicePixelRatio || 1;
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    if (w === 0 || h === 0) return;
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    const ctx = this.canvas.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.font = FONT;

    const p = this.plot;
    p.width = w - p.left - p.right;
    p.height = h - p.top - p.bottom;
    p.xMax = Math.max(100, ...this.series.map((s) => s.steps[s.steps.length - 1] ?? 0));
    p.yMax = niceCeil(Math.max(...this.series.flatMap((s) => s.values), 0));

    ctx.lineWidth = 1;
    ctx.textBaseline = "middle";
    for (let i = 0; i <= 4; i++) {
      const v = (p.yMax * i) / 4;
      ctx.strokeStyle = GRID;
      ctx.beginPath();
      ctx.moveTo(p.left, this.y(v) + 0.5);
      ctx.lineTo(p.left + p.width, this.y(v) + 0.5);
      ctx.stroke();
      ctx.fillStyle = MUTED;
      ctx.textAlign = "right";
      ctx.fillText(String(Math.round(v)), p.left - 8, this.y(v));
    }
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const tick = niceCeil(p.xMax) / 5; // round step values on the x axis
    for (let s = 0; s <= p.xMax; s += tick) {
      ctx.fillStyle = MUTED;
      ctx.fillText(String(s), this.x(s), p.top + p.height + 8);
    }

    for (const m of this.markers) {
      if (m.step > p.xMax) continue;
      ctx.strokeStyle = INK2;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(this.x(m.step) + 0.5, p.top);
      ctx.lineTo(this.x(m.step) + 0.5, p.top + p.height);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = INK2;
      ctx.textAlign = this.x(m.step) > p.left + p.width * 0.7 ? "right" : "left";
      ctx.fillText(m.label, this.x(m.step) + (ctx.textAlign === "right" ? -5 : 5), p.top + 2);
    }

    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    const labelYs: number[] = [];
    for (const s of this.series) {
      if (s.steps.length === 0) continue;
      ctx.strokeStyle = s.color;
      ctx.lineWidth = 2;
      ctx.lineJoin = "round";
      ctx.beginPath();
      s.steps.forEach((step, i) => (i ? ctx.lineTo(this.x(step), this.y(s.values[i])) : ctx.moveTo(this.x(step), this.y(s.values[i]))));
      ctx.stroke();
      // direct label with the latest measured value, nudged apart when lines end close together
      const last = s.values[s.values.length - 1];
      let ly = this.y(last);
      while (labelYs.some((o) => Math.abs(o - ly) < 13)) ly -= 13;
      labelYs.push(ly);
      ctx.fillStyle = INK;
      ctx.fillText(String(last), this.x(s.steps[s.steps.length - 1]) + 8, ly);
    }

    if (this.hoverStep !== null) {
      ctx.strokeStyle = MUTED;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(this.x(this.hoverStep) + 0.5, p.top);
      ctx.lineTo(this.x(this.hoverStep) + 0.5, p.top + p.height);
      ctx.stroke();
      for (const s of this.series) {
        const v = this.valueAt(s, this.hoverStep);
        if (v === null) continue;
        ctx.fillStyle = s.color;
        ctx.strokeStyle = "#1a1a19";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(this.x(this.hoverStep), this.y(v), 4.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
    }
  }
}
