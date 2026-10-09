import { expect, test, type Page } from "@playwright/test";

// Real Chromium, real pointer and keyboard input (Playwright drives the browser's
// input pipeline; nothing here dispatches synthetic DOM events).

const MODES = ["independent", "collective", "interrupted"] as const;

let problems: string[] = [];

test.beforeEach(async ({ page }) => {
  problems = [];
  page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text()}`));
  page.on("pageerror", (e) => problems.push(`pageerror: ${e}`));
  page.on("requestfailed", (r) => problems.push(`requestfailed: ${r.url()}`));
  page.on("response", (r) => r.status() >= 400 && problems.push(`http ${r.status()}: ${r.url()}`));
  await page.goto("/");
  await page.waitForFunction(() => window.__swarm?.state !== null);
});

test.afterEach(() => {
  expect(problems, "browser console errors / failed network requests").toEqual([]);
});

const step = (page: Page) => page.evaluate(() => window.__swarm.state!.step);
const state = (page: Page) => page.evaluate(() => window.__swarm.state!);

async function runUntil(page: Page, target: number): Promise<void> {
  await page.getByTestId("speed").selectOption("8");
  await page.getByTestId("btn-start").click();
  await page.waitForFunction((t) => window.__swarm.state!.step >= t, target, { timeout: 150_000 });
  await page.getByTestId("btn-pause").click();
  await expect(page.getByTestId("run-state")).toHaveText("Paused");
  await page.waitForTimeout(300); // let an in-flight step reply land
}

/** Counts canvas pixels matching a colour test, read back from the real canvas. */
function countPixels(page: Page, testId: string, kind: "pheromone" | "nonBackground" | "series"): Promise<number> {
  return page.getByTestId(testId).evaluate((canvas: HTMLCanvasElement, k) => {
    const data = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
    let n = 0;
    for (let i = 0; i < data.length; i += 4) {
      const [r, g, b, a] = [data[i], data[i + 1], data[i + 2], data[i + 3]];
      if (k === "pheromone" && r > 120 && b > 80 && g < 0.6 * r && r > b) n++;
      if (k === "nonBackground" && a > 0 && (Math.abs(r - 16) > 12 || Math.abs(g - 16) > 12 || Math.abs(b - 20) > 12)) n++;
      if (k === "series" && a > 200 && Math.max(r, g, b) - Math.min(r, g, b) > 90) n++;
    }
    return n;
  }, kind);
}

test("page loads with three live worlds", async ({ page }) => {
  await expect(page).toHaveTitle(/Swarm Mind/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Intelligence Without a Leader");
  for (const mode of MODES) {
    await expect(page.getByTestId(`world-${mode}`)).toBeVisible();
    await page.getByTestId(`canvas-${mode}`).scrollIntoViewIfNeeded();
    await page.waitForTimeout(150);
    expect(await countPixels(page, `canvas-${mode}`, "nonBackground")).toBeGreaterThan(500);
  }
  await expect(page.getByTestId("mode-badge")).toHaveText("Controlled scenario");
  await expect(page.getByTestId("step-count")).toHaveText("0");
  const s = await state(page);
  expect(s.worlds.independent.agents.x).toHaveLength(60);
  expect(s.worlds.independent.agents).toEqual(s.worlds.collective.agents); // matched start
});

test("layout: side by side on desktop, stacked without overflow on mobile", async ({ page }, info) => {
  const boxes = await Promise.all(MODES.map((m) => page.getByTestId(`world-${m}`).boundingBox()));
  if (info.project.name === "desktop") {
    expect(Math.abs(boxes[0]!.y - boxes[2]!.y)).toBeLessThan(2);
    expect(boxes[1]!.x).toBeGreaterThan(boxes[0]!.x + boxes[0]!.width - 1);
  } else {
    expect(boxes[1]!.y).toBeGreaterThan(boxes[0]!.y + boxes[0]!.height - 1);
    expect(boxes[2]!.y).toBeGreaterThan(boxes[1]!.y + boxes[1]!.height - 1);
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  const shot = await page.screenshot({ path: info.outputPath(`layout-${info.project.name}.png`), fullPage: true });
  expect(shot.byteLength).toBeGreaterThan(20_000);
});

test("start, pause and reset", async ({ page }) => {
  await page.getByTestId("btn-start").click();
  await expect(page.getByTestId("run-state")).toHaveText("Running");
  await page.waitForFunction(() => window.__swarm.state!.step >= 40);
  await page.getByTestId("btn-pause").click();
  await page.waitForTimeout(400);
  const paused = await step(page);
  await page.waitForTimeout(600);
  expect(await step(page)).toBe(paused);
  await expect(page.getByTestId("step-count")).toHaveText(String(paused));

  await page.getByTestId("btn-reset").click();
  await expect(page.getByTestId("step-count")).toHaveText("0");
  expect((await state(page)).config.seed).toBe(1);
});

test("keyboard: start with Enter, change speed, pause with Space", async ({ page }) => {
  await page.getByTestId("btn-start").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("run-state")).toHaveText("Running");
  await page.getByTestId("speed").focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByTestId("speed")).toHaveValue("4");
  await page.getByTestId("btn-pause").focus();
  await page.keyboard.press("Space");
  await expect(page.getByTestId("run-state")).toHaveText("Paused");
  expect(await step(page)).toBeGreaterThan(0);
});

test("new scenario loads a different reproducible map", async ({ page }) => {
  const before = await state(page);
  await page.getByTestId("btn-new").click();
  await page.waitForFunction((id) => window.__swarm.state!.session_id !== id, before.session_id);
  const after = await state(page);
  expect(after.config.seed).not.toBe(before.config.seed);
  expect(after.worlds.collective.obstacles).not.toBe(before.worlds.collective.obstacles);
  await expect(page.getByTestId("seed-label")).toHaveText(String(after.config.seed));
});

test("changing settings forces a restart and marks the run exploratory", async ({ page }) => {
  await page.getByTestId("btn-start").click();
  await page.waitForFunction(() => window.__swarm.state!.step >= 20);
  await page.getByTestId("params").locator("summary").click();
  await page.getByTestId("agent-count").focus();
  for (let i = 0; i < 4; i++) await page.keyboard.press("ArrowRight"); // 60 -> 100
  await page.getByTestId("deposit").fill("2");
  await page.getByTestId("btn-apply").click();
  await page.waitForFunction(() => window.__swarm.state!.config.agent_count === 100);
  const s = await state(page);
  expect(s.step).toBe(0); // restarted
  expect(s.config.deposit).toBe(2);
  for (const mode of MODES) expect(s.worlds[mode].agents.x).toHaveLength(100);
  await expect(page.getByTestId("mode-badge")).toHaveText("Exploratory mode");
  await expect(page.getByTestId("mode-note")).toContainText("agent_count changed");
});

test("World C: scheduled communication cut happens at the configured step", async ({ page }) => {
  await page.getByTestId("params").locator("summary").click();
  await page.getByTestId("interruption-step").fill("100");
  await page.getByTestId("btn-apply").click();
  await page.waitForFunction(() => window.__swarm.state!.interruption_step === 100);
  await expect(page.getByTestId("chip-interrupted")).toHaveText("Pheromone on");
  await runUntil(page, 160);
  const s = await state(page);
  expect(s.worlds.interrupted.metrics.communication_active).toBe(false);
  expect(s.worlds.interrupted.metrics.communication_disabled_step).toBe(100);
  expect(s.worlds.collective.metrics.communication_active).toBe(true);
  await expect(page.getByTestId("chip-interrupted")).toHaveText("Cut at step 100");
  await expect(page.getByTestId("event-log")).toContainText("Step 100: pheromone communication cut in the Breakdown world (scheduled)");
});

test("World C: manual communication cut", async ({ page }) => {
  await runUntil(page, 60);
  const at = await step(page);
  await page.getByTestId("btn-interrupt").click();
  await expect(page.getByTestId("chip-interrupted")).toHaveText(`Cut at step ${at}`);
  await expect(page.getByTestId("mode-badge")).toHaveText("Exploratory mode");
  await expect(page.getByTestId("event-log")).toContainText("(manual)");
  const s = await state(page);
  expect(s.worlds.interrupted.metrics.communication_active).toBe(false);
  expect(s.worlds.collective.metrics.communication_active).toBe(true);
});

test("obstacle injection by button and by shift-click", async ({ page }) => {
  await runUntil(page, 40);
  const before = await state(page);
  await page.getByTestId("btn-obstacle").click();
  await page.waitForFunction(() => window.__swarm.state!.worlds.collective.events.length === 1);
  let s = await state(page);
  for (const mode of MODES) {
    expect(s.worlds[mode].obstacles).not.toBe(before.worlds[mode].obstacles);
    expect(s.worlds[mode].events.at(-1)!.type).toBe("obstacle_added");
  }
  await expect(page.getByTestId("event-log")).toContainText("wall inserted in all three worlds");

  // real mouse click with the Shift modifier, a quarter of the way into the canvas
  const canvas = page.getByTestId("canvas-collective");
  await canvas.scrollIntoViewIfNeeded();
  const box = (await canvas.boundingBox())!;
  await page.keyboard.down("Shift");
  await page.mouse.click(box.x + box.width * 0.2, box.y + box.height * 0.25);
  await page.keyboard.up("Shift");
  await page.waitForFunction(() => window.__swarm.state!.worlds.collective.events.length === 2);
  s = await state(page);
  expect(s.worlds.independent.events).toHaveLength(2);
  // the simulation keeps running with the new walls
  await runUntil(page, 120);
});

test("pheromone trails render in the collective world and can be hidden", async ({ page }) => {
  await runUntil(page, 500);
  await page.getByTestId("canvas-collective").scrollIntoViewIfNeeded();
  await page.waitForTimeout(200);
  expect(await countPixels(page, "canvas-collective", "pheromone")).toBeGreaterThan(300);
  expect(await countPixels(page, "canvas-independent", "pheromone")).toBe(0);
  await page.getByTestId("show-pheromone").uncheck();
  await page.waitForTimeout(200);
  expect(await countPixels(page, "canvas-collective", "pheromone")).toBe(0);
});

test("charts and numbers show backend measurements", async ({ page }) => {
  await runUntil(page, 400);
  const shown = await state(page);
  const backend = await (await page.request.get(`/api/session/${shown.session_id}`)).json();
  expect(backend.step).toBe(shown.step);
  for (const mode of MODES) {
    const delivered = backend.worlds[mode].metrics.food_delivered;
    await expect(page.getByTestId(`delivered-${mode}`)).toHaveText(String(delivered));
    expect(shown.worlds[mode].series.delivered.at(-1)).toBe(delivered);
    expect(shown.worlds[mode].series).toEqual(backend.worlds[mode].series);
  }
  const row = page.getByTestId("metrics-table").locator("tbody tr").first();
  await expect(row).toContainText(String(backend.worlds.collective.metrics.food_delivered));
  expect(backend.worlds.collective.metrics.food_delivered).toBeGreaterThan(0);

  const chart = page.getByTestId("chart");
  await chart.scrollIntoViewIfNeeded();
  expect(await countPixels(page, "chart", "series")).toBeGreaterThan(200);
  const box = (await chart.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
  await expect(page.locator("#chart-tooltip")).toBeVisible();
  await expect(page.locator("#chart-tooltip")).toContainText("step");
});

test("focus mode and comparison mode", async ({ page }) => {
  await page.getByTestId("view-collective").click();
  await expect(page.getByTestId("world-collective")).toBeVisible();
  await expect(page.getByTestId("world-independent")).toBeHidden();
  await expect(page.getByTestId("world-interrupted")).toBeHidden();
  await page.getByTestId("view-all").click();
  for (const mode of MODES) await expect(page.getByTestId(`world-${mode}`)).toBeVisible();
});

test("stored experiment results are displayed", async ({ page }) => {
  const stored = await (await page.request.get("/api/experiments/results")).json();
  test.skip(!stored.available, "no stored experiment in experiments/results");
  const box = page.getByTestId("stored-results");
  await expect(box.locator("tbody tr").first()).toContainText("Food delivered");
  const mean = stored.results.exp1_baseline_food_collection.food_delivered.collective.mean;
  await expect(box.locator("tbody tr").first()).toContainText(mean.toFixed(0));
  await expect(box).toContainText(`${stored.manifest.spec.seeds.length} seeds`);
});

test("running a quick experiment from the page", async ({ page }) => {
  await page.getByTestId("btn-quick").click();
  await expect(page.getByTestId("btn-quick")).toBeDisabled();
  const rows = page.getByTestId("quick-results").locator("tbody tr");
  await expect(rows).toHaveCount(5, { timeout: 150_000 }); // 4 seeds + mean
  await expect(page.getByTestId("quick-results")).toContainText("Collective − Independent");
  await expect(page.getByTestId("btn-quick")).toBeEnabled();
});
