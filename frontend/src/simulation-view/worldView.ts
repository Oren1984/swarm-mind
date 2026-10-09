import { base64ToBytes, unpackBits } from "../decode";
import type { SessionState, WorldState } from "../types";

// Colours are part of the visual legend in index.html — keep them in sync.
export const PALETTE = {
  background: "#101014",
  obstacle: "#5b5a55",
  nest: "#ffffff",
  food: "#35c46a",
  pheromone: [224, 86, 160] as const, // active trails
  pheromoneStale: [150, 150, 158] as const, // trails that are no longer sensed
  behaviour: ["#86b6ef", "#f2c230", "#2ee6c8"], // exploring, following a trail, returning with food
};

/** Draws one world exactly as the backend reports it. Positions are only
 *  interpolated between two consecutive backend states for smooth motion. */
export class WorldView {
  private ctx: CanvasRenderingContext2D;
  private field = document.createElement("canvas");
  private walls = document.createElement("canvas");
  private wallsKey = "";
  private prev: WorldState | null = null;
  private curr: WorldState | null = null;
  private currAt = 0;
  private interval = 33;
  private session: SessionState | null = null;

  constructor(private canvas: HTMLCanvasElement) {
    this.ctx = canvas.getContext("2d")!;
  }

  update(session: SessionState, world: WorldState, now: number): void {
    const sameRun = this.session?.session_id === session.session_id;
    this.prev = sameRun ? this.curr : null;
    this.interval = sameRun ? Math.min(250, Math.max(16, now - this.currAt)) : 33;
    this.curr = world;
    this.currAt = now;
    this.session = session;
    this.paintField(world, session);
    if (world.obstacles !== this.wallsKey) this.paintWalls(world, session);
  }

  private paintField(world: WorldState, s: SessionState): void {
    this.field.width = s.width;
    this.field.height = s.height;
    if (!world.pheromone) return;
    const values = base64ToBytes(world.pheromone);
    const [r, g, b] = world.metrics.communication_active ? PALETTE.pheromone : PALETTE.pheromoneStale;
    const image = new ImageData(s.width, s.height);
    for (let i = 0; i < values.length; i++) {
      const o = i * 4;
      image.data[o] = r;
      image.data[o + 1] = g;
      image.data[o + 2] = b;
      image.data[o + 3] = Math.min(255, Math.sqrt(values[i] / 255) * 420); // perceptual boost for faint trails
    }
    this.field.getContext("2d")!.putImageData(image, 0, 0);
  }

  private paintWalls(world: WorldState, s: SessionState): void {
    this.wallsKey = world.obstacles;
    this.walls.width = s.width;
    this.walls.height = s.height;
    const bits = unpackBits(base64ToBytes(world.obstacles), s.width * s.height);
    const c = this.walls.getContext("2d")!;
    c.fillStyle = PALETTE.obstacle;
    for (let i = 0; i < bits.length; i++) if (bits[i]) c.fillRect(i % s.width, Math.floor(i / s.width), 1, 1);
  }

  /** Converts a pointer position on the canvas to world coordinates. */
  toWorld(clientX: number, clientY: number): { x: number; y: number } | null {
    if (!this.session) return null;
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: ((clientX - rect.left) / rect.width) * this.session.width,
      y: ((clientY - rect.top) / rect.height) * this.session.height,
    };
  }

  draw(now: number, showPheromone: boolean, animate: boolean): void {
    const s = this.session;
    const world = this.curr;
    if (!s || !world) return;
    const dpr = window.devicePixelRatio || 1;
    const cssWidth = this.canvas.clientWidth;
    const width = Math.round(cssWidth * dpr);
    const height = Math.round((cssWidth * s.height * dpr) / s.width);
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    const ctx = this.ctx;
    const k = width / s.width; // device pixels per world unit
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = PALETTE.background;
    ctx.fillRect(0, 0, width, height);

    if (showPheromone && world.pheromone) {
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(this.field, 0, 0, width, height);
    }
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(this.walls, 0, 0, width, height);

    ctx.setTransform(k, 0, 0, k, 0, 0);
    for (const f of world.food) {
      ctx.globalAlpha = 0.25;
      ctx.fillStyle = PALETTE.food;
      ctx.beginPath();
      ctx.arc(f.x, f.y, f.r + 1.2, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
      // the filled core shrinks as the source is harvested
      ctx.beginPath();
      ctx.arc(f.x, f.y, Math.max(0.8, f.r * Math.sqrt(Math.min(1, f.amount / s.config.food_capacity))), 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.strokeStyle = PALETTE.nest;
    ctx.lineWidth = 0.7;
    ctx.fillStyle = "rgba(255,255,255,0.14)";
    ctx.beginPath();
    ctx.arc(s.nest.x, s.nest.y, s.nest.r, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    const a = world.agents;
    const p = this.prev?.agents;
    const blend = animate && p && p.x.length === a.x.length ? Math.min(1, (now - this.currAt) / this.interval) : 1;
    for (let i = 0; i < a.x.length; i++) {
      let x = a.x[i];
      let y = a.y[i];
      if (blend < 1 && p) {
        const dx = x - p.x[i];
        const dy = y - p.y[i];
        if (dx * dx + dy * dy < 400) { // skip interpolation across teleports (e.g. obstacle relocation)
          x = p.x[i] + dx * blend;
          y = p.y[i] + dy * blend;
        }
      }
      const h = a.heading[i];
      const cos = Math.cos(h);
      const sin = Math.sin(h);
      ctx.fillStyle = PALETTE.behaviour[a.behaviour[i]];
      ctx.beginPath();
      ctx.moveTo(x + cos * 1.5, y + sin * 1.5);
      ctx.lineTo(x - cos * 0.9 - sin * 0.8, y - sin * 0.9 + cos * 0.8);
      ctx.lineTo(x - cos * 0.9 + sin * 0.8, y - sin * 0.9 - cos * 0.8);
      ctx.closePath();
      ctx.fill();
    }
  }
}
