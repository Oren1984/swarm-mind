// Records real dashboard footage for the demo video (one WebM per scene).
//   node tools/record-footage.mjs <output-dir>     (stack must be up on SWARM_URL)
// Each clip is a screen recording of the actual page. To start a clip at a later
// simulation step, the same session is first advanced through the public API
// (unrendered), then the page's own Start button drives what is recorded.
import { chromium } from "@playwright/test";
import { mkdirSync, renameSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const url = process.env.SWARM_URL ?? "http://localhost:8080";
const out = resolve(process.argv[2] ?? "footage");
mkdirSync(out, { recursive: true });
const SIZE = { width: 1920, height: 1080 };

const clips = [
  { name: "independent", view: "independent", startStep: 0, seconds: 30, speed: "2" },
  { name: "collective", view: "collective", startStep: 0, seconds: 30, speed: "4" },
  { name: "three-worlds", view: "all", startStep: 500, seconds: 30, speed: "2" },
  { name: "breakdown", view: "interrupted", startStep: 1380, seconds: 30, speed: "2" },
];

const browser = await chromium.launch();
const manifest = [];

for (const clip of clips) {
  const context = await browser.newContext({ viewport: SIZE, recordVideo: { dir: out, size: SIZE } });
  const page = await context.newPage();
  const opened = Date.now();
  await page.goto(`${url}/?seed=1`);
  await page.waitForFunction(() => window.__swarm?.state !== null);
  await page.selectOption("#speed", clip.speed);

  let done = 0;
  while (done < clip.startStep) {
    const n = Math.min(200, clip.startStep - done);
    await page.evaluate(async ({ n }) => {
      const id = window.__swarm.state.session_id;
      await fetch(`/api/session/${id}/step`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ n }) });
    }, { n });
    done += n;
  }

  if (clip.view !== "all") await page.click(`[data-testid="view-${clip.view}"]`);
  await page.click("#btn-start");
  await page.waitForFunction((s) => window.__swarm.state.step > s, clip.startStep);
  // scroll after the click (clicking scrolls the button into view), then park the pointer
  await page.locator("#worlds").evaluate((el) => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 16));
  await page.mouse.move(SIZE.width - 5, SIZE.height - 5);
  // single-world clips are later cropped to the world panel (measured here, not guessed)
  let crop = null;
  if (clip.view !== "all") {
    const box = await page.locator(`[data-world="${clip.view}"]`).boundingBox();
    const even = (v) => Math.round(v / 2) * 2;
    crop = { x: even(Math.max(0, box.x - 12)), y: even(Math.max(0, box.y - 12)), w: even(box.width + 24), h: even(Math.min(box.height + 24, SIZE.height - Math.max(0, box.y - 12))) };
  }
  const from = (Date.now() - opened) / 1000 + 0.4;
  const firstStep = await page.evaluate(() => window.__swarm.state.step);
  await page.waitForTimeout(clip.seconds * 1000 + 800);
  const lastStep = await page.evaluate(() => window.__swarm.state.step);
  const video = page.video();
  await context.close();
  const file = `${clip.name}.webm`;
  renameSync(await video.path(), resolve(out, file));
  manifest.push({ ...clip, file, crop, trimStart: Number(from.toFixed(2)), firstStep, lastStep });
  console.log(`${file}: steps ${firstStep}-${lastStep}, usable from ${from.toFixed(1)}s for ${clip.seconds}s`);
}

writeFileSync(resolve(out, "footage.json"), JSON.stringify(manifest, null, 2));
await browser.close();
