import { api, type SessionParams } from "./api";
import { LineChart, type Marker } from "./charts/lineChart";
import { fmt, fmtPct, fmtSigned } from "./decode";
import { WorldView } from "./simulation-view/worldView";
import { WORLD_MODES, type ModeComparison, type Paired, type QuickResult, type SessionState, type StoredResults, type WorldMode } from "./types";

const SERIES_COLORS: Record<WorldMode, string> = {
  independent: "#3987e5",
  collective: "#d95926",
  interrupted: "#199e70",
};
const NAMES: Record<WorldMode, string> = {
  independent: "Independent",
  collective: "Collective",
  interrupted: "Breakdown",
};
const TICK_MS = 33; // target interval between step requests; steps per request = speed

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

/** Tiny DOM builder — all dynamic text goes through textContent. */
function el<K extends keyof HTMLElementTagNameMap>(tag: K, text?: string, className?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function table(head: string[], rows: string[][]): HTMLTableElement {
  const t = el("table");
  const hr = t.createTHead().insertRow();
  head.forEach((h) => hr.append(el("th", h)));
  const body = t.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    row.forEach((cell, i) => tr.append(el(i === 0 ? "th" : "td", cell)));
  }
  return t;
}

// ----------------------------------------------------------------------- state
let state: SessionState | null = null;
let running = false;
let busy = false; // a request that mutates the session is in flight
let showPheromone = true;
const params: SessionParams = { seed: 1, agent_count: 60, deposit: 1, interruption_step: 1500 };

const views = {} as Record<WorldMode, WorldView>;
const panels = {} as Record<WorldMode, HTMLElement>;
for (const mode of WORLD_MODES) {
  panels[mode] = document.querySelector<HTMLElement>(`[data-world="${mode}"]`)!;
  views[mode] = new WorldView(panels[mode].querySelector("canvas")!);
}
const chart = new LineChart($<HTMLCanvasElement>("chart"), $("chart-tooltip"));

// Exposed for the browser tests: the exact backend state the page is showing.
declare global {
  interface Window { __swarm: { state: SessionState | null; frames: number } }
}
window.__swarm = { state: null, frames: 0 };

// ------------------------------------------------------------------- rendering
function applyState(next: SessionState): void {
  state = next;
  window.__swarm.state = next;
  const now = performance.now();
  for (const mode of WORLD_MODES) views[mode].update(next, next.worlds[mode], now);
  renderText(next);
}

function chipFor(s: SessionState, mode: WorldMode): [string, string, string] {
  const m = s.worlds[mode].metrics;
  if (mode === "independent") return ["No communication", "off", "Baseline control — every agent forages alone."];
  if (mode === "collective") return ["Pheromone on", "on", "Same agents, plus pheromone marks they leave and smell."];
  if (m.communication_active) {
    return ["Pheromone on", "on", `Same as Collective until communication is cut at step ${s.interruption_step}.`];
  }
  return [`Cut at step ${m.communication_disabled_step}`, "cut", "Communication is off: old trails fade and no agent smells them."];
}

function renderText(s: SessionState): void {
  $("step-count").textContent = String(s.step);
  $("seed-label").textContent = String(s.config.seed);
  $("version").textContent = ` Simulator v${s.version}.`;

  const badge = $("mode-badge");
  const exploratory = s.mode === "exploratory";
  badge.textContent = exploratory ? "Exploratory mode" : "Controlled scenario";
  badge.classList.toggle("warn", exploratory);
  $("mode-note").textContent = exploratory
    ? `Exploratory mode — this run is no longer the default controlled scenario (${s.exploratory_reasons.join("; ")}). Explore freely; use the controlled experiments below for conclusions.`
    : "Controlled scenario — default parameters, identical map and agents in all three worlds; the only difference is pheromone communication.";

  for (const mode of WORLD_MODES) {
    const w = s.worlds[mode];
    const chip = panels[mode].querySelector<HTMLElement>("[data-chip]")!;
    const [text, kind, role] = chipFor(s, mode);
    chip.textContent = text;
    chip.dataset.kind = kind;
    panels[mode].querySelector(".role")!.textContent = role;
    const stats = panels[mode].querySelector("dl")!;
    const items: [string, string][] = [
      ["Food delivered", fmt(w.metrics.food_delivered)],
      ["Per 100 steps (recent)", fmt(w.metrics.recent_rate_per_100, 1)],
      ["Area explored", fmtPct(w.metrics.exploration_coverage)],
    ];
    stats.replaceChildren(...items.flatMap(([k, v], i) => {
      const dd = el("dd", v);
      if (i === 0) dd.dataset.testid = `delivered-${mode}`;
      return [el("dt", k), dd];
    }));
  }

  // Chart: backend series and backend-recorded events only.
  const markers: Marker[] = [];
  for (const e of s.worlds.interrupted.events) {
    if (e.type === "communication_disabled") markers.push({ step: e.step, label: "communication cut" });
  }
  for (const e of s.worlds.collective.events) {
    if (e.type === "obstacle_added") markers.push({ step: e.step, label: "wall added" });
  }
  chart.setData(
    WORLD_MODES.map((m) => ({ name: NAMES[m], color: SERIES_COLORS[m], steps: s.worlds[m].series.steps, values: s.worlds[m].series.delivered })),
    markers,
  );

  const m = (mode: WorldMode) => s.worlds[mode].metrics;
  const diff = m("collective").food_delivered - m("independent").food_delivered;
  const rows: string[][] = [
    ["Food delivered", ...WORLD_MODES.map((k) => fmt(m(k).food_delivered)), fmtSigned(diff)],
    ["First delivery (step)", ...WORLD_MODES.map((k) => fmt(m(k).first_delivery_step)), "—"],
    ["Delivery rate / 100 steps", ...WORLD_MODES.map((k) => fmt(m(k).delivery_rate_per_100, 1)),
      fmtSigned(sub(m("collective").delivery_rate_per_100, m("independent").delivery_rate_per_100), 1)],
    ["Area explored", ...WORLD_MODES.map((k) => fmtPct(m(k).exploration_coverage)),
      fmtSigned((m("collective").exploration_coverage - m("independent").exploration_coverage) * 100) + " pts"],
    ["Travel efficiency", ...WORLD_MODES.map((k) => fmtPct(m(k).travel_efficiency)),
      fmtSigned(scale(sub(m("collective").travel_efficiency, m("independent").travel_efficiency), 100)) + " pts"],
    ["Food sources emptied", ...WORLD_MODES.map((k) => fmt(m(k).food_relocations)), "—"],
  ];
  $("metrics-table").replaceChildren(
    ...table(["", "Independent", "Collective", "Breakdown", "Collective − Independent"], rows).children);

  const log = $("event-log");
  const events = WORLD_MODES.flatMap((mode) => s.worlds[mode].events.map((e) => ({ ...e, mode })))
    .filter((e) => e.type === "communication_disabled" || e.mode === "collective")
    .sort((a, b) => a.step - b.step);
  log.replaceChildren(...(events.length
    ? events.map((e) => el("li", e.type === "communication_disabled"
        ? `Step ${e.step}: pheromone communication cut in the Breakdown world (${e.source}).`
        : `Step ${e.step}: wall inserted in all three worlds (${e.source}).`))
    : [el("li", "No interventions yet.", "muted")]));
}

const sub = (a: number | null, b: number | null) => (a === null || b === null ? null : a - b);
const scale = (a: number | null, k: number) => (a === null ? null : a * k);

function frame(now: number): void {
  window.__swarm.frames++;
  for (const mode of WORLD_MODES) {
    if (panels[mode].offsetParent !== null) views[mode].draw(now, showPheromone, running);
  }
  requestAnimationFrame(frame);
}

// ------------------------------------------------------------------ simulation
function setRunning(value: boolean): void {
  running = value;
  $("run-state").textContent = value ? "Running" : "Paused";
  $<HTMLButtonElement>("btn-start").disabled = value;
  $<HTMLButtonElement>("btn-pause").disabled = !value;
}

async function loop(): Promise<void> {
  while (running && state) {
    const started = performance.now();
    if (!busy) {
      busy = true;
      try {
        const sessionId = state.session_id;
        const next = await api.step(sessionId, Number($<HTMLSelectElement>("speed").value));
        if (state?.session_id === sessionId) applyState(next); // ignore replies for a replaced session
      } catch (err) {
        setRunning(false);
        showError(err);
      } finally {
        busy = false;
      }
    }
    // Slow rendering or a slow server only delays the next request; each step is still one fixed step.
    await new Promise((r) => setTimeout(r, Math.max(0, TICK_MS - (performance.now() - started))));
  }
}

async function exclusive(action: () => Promise<void>): Promise<void> {
  while (busy) await new Promise((r) => setTimeout(r, 5));
  busy = true;
  try {
    await action();
  } catch (err) {
    showError(err);
  } finally {
    busy = false;
  }
}

function showError(err: unknown): void {
  $("mode-note").textContent = `Could not reach the simulation server: ${err instanceof Error ? err.message : String(err)}`;
}

async function restart(): Promise<void> {
  setRunning(false);
  await exclusive(async () => applyState(await api.createSession(params)));
}

// -------------------------------------------------------------------- controls
$("btn-start").addEventListener("click", () => {
  if (running || !state) return;
  setRunning(true);
  void loop();
});
$("btn-pause").addEventListener("click", () => setRunning(false));
$("btn-reset").addEventListener("click", () => void restart());
$("btn-new").addEventListener("click", () => {
  params.seed = Math.floor(Math.random() * 100000) + 1; // only picks which reproducible scenario to load
  void restart();
});
$("btn-apply").addEventListener("click", () => {
  params.agent_count = Number($<HTMLInputElement>("agent-count").value);
  params.deposit = Number($<HTMLInputElement>("deposit").value);
  params.interruption_step = Math.max(0, Math.round(Number($<HTMLInputElement>("interruption-step").value) || 0));
  void restart();
});
$("agent-count").addEventListener("input", (e) => ($("out-agents").textContent = (e.target as HTMLInputElement).value));
$("deposit").addEventListener("input", (e) => ($("out-deposit").textContent = Number((e.target as HTMLInputElement).value).toFixed(2)));
$("show-pheromone").addEventListener("change", (e) => (showPheromone = (e.target as HTMLInputElement).checked));

$("btn-interrupt").addEventListener("click", () =>
  void exclusive(async () => {
    if (state) applyState(await api.interrupt(state.session_id));
  }));

async function addObstacle(point?: { x: number; y: number }): Promise<void> {
  await exclusive(async () => {
    if (!state) return;
    const next = await api.obstacle(state.session_id, point);
    applyState(next);
    if (next.applied === false) {
      $("mode-note").textContent = "That wall was not inserted: it would cover the nest or a food source, or cut a food source off completely.";
    }
  });
}
$("btn-obstacle").addEventListener("click", () => void addObstacle());
for (const mode of WORLD_MODES) {
  panels[mode].querySelector("canvas")!.addEventListener("click", (e) => {
    if (!e.shiftKey) return;
    const point = views[mode].toWorld(e.clientX, e.clientY);
    if (point) void addObstacle(point);
  });
}

document.querySelectorAll<HTMLButtonElement>("[data-view]").forEach((button) => {
  if (button.tagName !== "BUTTON") return;
  button.addEventListener("click", () => {
    $("worlds").dataset.view = button.dataset.view;
    document.querySelectorAll("button[data-view]").forEach((b) => b.classList.toggle("active", b === button));
  });
});

// ----------------------------------------------------------------- experiments
function effectText(p: Paired, unit = ""): string {
  if (p.mean_difference === null || p.ci95 === null) return "undefined";
  const rel = p.relative_difference_pct === null ? "" : ` (${fmtSigned(p.relative_difference_pct)}%)`;
  return `${fmtSigned(p.mean_difference, 1)}${unit}${rel}, 95% interval ${fmtSigned(p.ci95[0], 1)} to ${fmtSigned(p.ci95[1], 1)}`;
}

function renderStored(r: StoredResults | null): void {
  const box = $("stored-results");
  if (!r) {
    box.replaceChildren(el("p", "No stored experiment found. Generate one with: docker compose exec api python -m app.experiments.run", "muted"));
    return;
  }
  const spec = r.manifest.spec;
  const e1 = r.results.exp1_baseline_food_collection;
  const e2 = r.results.exp2_trail_emergence;
  const e3 = r.results.exp3_communication_failure;
  const e4 = r.results.exp4_dynamic_obstacle;
  const row = (label: string, c: ModeComparison, digits: number, k = 1): string[] => [
    label, fmt(scale(c.independent.mean, k), digits), fmt(scale(c.collective.mean, k), digits),
    fmtSigned(scale(c.communication_effect.mean_difference, k), digits),
    c.communication_effect.ci95 ? `${fmtSigned(c.communication_effect.ci95[0] * k, digits)} to ${fmtSigned(c.communication_effect.ci95[1] * k, digits)}` : "—",
  ];
  box.classList.remove("muted");
  box.replaceChildren(
    el("p", `${spec.seeds.length} seeds × ${spec.steps} steps per world, simulator v${r.manifest.simulator_version}, generated ${r.manifest.generated_utc.slice(0, 10)}. Mean over seeds; difference is Collective − Independent, paired by seed.`, "hint"),
    table(["Metric", "Independent", "Collective", "Difference", "95% interval"], [
      row("Food delivered", e1.food_delivered, 0),
      row("Travel efficiency (%)", e1.travel_efficiency, 1, 100),
      row("Area explored (%)", e1.exploration_coverage, 1, 100),
      ["Traffic on busiest 5% of cells (%)", fmt(scale(e2.independent.mean, 100), 1), fmt(scale(e2.collective.mean, 100), 1),
        fmtSigned(scale(e2.difference.mean_difference, 100), 1),
        e2.difference.ci95 ? `${fmtSigned(e2.difference.ci95[0] * 100, 1)} to ${fmtSigned(e2.difference.ci95[1] * 100, 1)}` : "—"],
    ]),
    el("p", `After communication is cut at step ${spec.interruption_step}, the Breakdown world delivered ${fmt(e3.post_deliveries.interrupted.mean)} units on average versus ${fmt(e3.post_deliveries.collective.mean)} in the uninterrupted Collective world and ${fmt(e3.post_deliveries.independent.mean)} in the Independent world (difference to Collective: ${effectText(e3.interrupted_vs_collective_post)}).`),
    el("p", `Dynamic wall at step ${spec.obstacle_step}: late-window delivery rate relative to before the wall was ${fmt(scale(e4.collective.recovery_ratio.mean, 100))}% in Collective and ${fmt(scale(e4.independent.recovery_ratio.mean, 100))}% in Independent (no-wall controls: ${fmt(scale(e4.collective.control_ratio.mean, 100))}% and ${fmt(scale(e4.independent.control_ratio.mean, 100))}%).`),
    el("p", "Full tables, charts and limitations: docs/results-and-limitations.md", "hint"),
  );
}

function renderQuick(q: QuickResult): void {
  const rows = q.seeds.map((seed, i) => [
    `Seed ${seed}`, ...WORLD_MODES.map((m) => String(q.per_seed[m][i])),
  ]);
  rows.push(["Mean", ...WORLD_MODES.map((m) => fmt(q.food_delivered[m].mean, 1))]);
  $("quick-results").replaceChildren(
    table(["Food delivered", "Independent", "Collective", "Breakdown"], rows),
    el("p", `Collective − Independent: ${effectText(q.collective_vs_independent)}. Breakdown − Collective: ${effectText(q.interrupted_vs_collective)}. n = ${q.seeds.length} seeds, ${q.steps} steps, cut at step ${q.interruption_step}.`),
  );
}

$("btn-quick").addEventListener("click", async () => {
  const button = $<HTMLButtonElement>("btn-quick");
  button.disabled = true;
  button.textContent = "Running simulations…";
  try {
    renderQuick(await api.quickExperiment(4, 1000));
  } catch (err) {
    $("quick-results").replaceChildren(el("p", `Experiment failed: ${err instanceof Error ? err.message : String(err)}`, "muted"));
  } finally {
    button.disabled = false;
    button.textContent = "Run quick experiment";
  }
});

// ------------------------------------------------------------------------ boot
const urlSeed = Number(new URLSearchParams(location.search).get("seed"));
if (Number.isInteger(urlSeed) && urlSeed > 0) params.seed = urlSeed;
void restart();
api.storedResults().then(renderStored).catch(() => renderStored(null));
requestAnimationFrame(frame);
