// Captures the README/docs screenshots from the real running application.
//   node tools/capture-screenshots.mjs            (stack must be up on SWARM_URL)
import { chromium, devices } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const url = process.env.SWARM_URL ?? "http://localhost:8080";
const out = fileURLToPath(new URL("../../showcase/screenshots/", import.meta.url));
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();

async function open(contextOptions) {
  const context = await browser.newContext(contextOptions);
  const page = await context.newPage();
  await page.goto(`${url}/?seed=1`);
  await page.waitForFunction(() => window.__swarm?.state !== null);
  return page;
}

/** Runs the visible simulation (through the page's own Start button) up to a step. */
async function runTo(page, target) {
  await page.selectOption("#speed", "8");
  await page.click("#btn-start");
  await page.waitForFunction((t) => window.__swarm.state.step >= t, target, { timeout: 600_000 });
  await page.click("#btn-pause");
  await page.waitForTimeout(500);
  return page.evaluate(() => window.__swarm.state.step);
}

const shot = async (page, name, options = {}) => {
  await page.screenshot({ path: `${out}${name}.png`, ...options });
  console.log(`saved ${name}.png at step ${await page.evaluate(() => window.__swarm.state.step)}`);
};

// --- desktop: the controlled default scenario (seed 1) ---------------------
const page = await open({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1.5 });
await runTo(page, 1300);
await shot(page, "hero-three-worlds", { clip: { x: 0, y: 0, width: 1600, height: 790 } });

await page.click('[data-testid="view-collective"]');
await page.locator('[data-testid="world-collective"]').scrollIntoViewIfNeeded();
await page.waitForTimeout(300);
await page.locator('[data-testid="world-collective"]').screenshot({ path: `${out}world-collective-trails.png` });
await page.click('[data-testid="view-independent"]');
await page.waitForTimeout(300);
await page.locator('[data-testid="world-independent"]').screenshot({ path: `${out}world-independent.png` });
await page.click('[data-testid="view-all"]');

await runTo(page, 1580); // shortly after the scheduled cut at step 1500
await page.evaluate(() => window.scrollTo(0, 0));
await page.click('[data-testid="view-interrupted"]');
await page.waitForTimeout(300);
await page.locator('[data-testid="world-interrupted"]').screenshot({ path: `${out}world-breakdown-after-cut.png` });
await page.click('[data-testid="view-all"]');

await runTo(page, 3000);
await page.evaluate(() => window.scrollTo(0, 0));
await shot(page, "dashboard-full", { fullPage: true });
await page.locator(".results").screenshot({ path: `${out}results-panel.png` });

// --- desktop: exploratory run with an injected wall -------------------------
const explore = await open({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1.5 });
await runTo(explore, 700);
await explore.click("#btn-obstacle");
await explore.waitForFunction(() => window.__swarm.state.worlds.collective.events.length === 1);
await runTo(explore, 1100);
await shot(explore, "dynamic-obstacle", { clip: { x: 0, y: 0, width: 1600, height: 790 } });

// --- mobile ------------------------------------------------------------------
const mobile = await open({ ...devices["Pixel 7"] });
await runTo(mobile, 600);
await shot(mobile, "mobile", { fullPage: true });

await browser.close();
