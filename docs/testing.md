# Testing

All results below are from actual runs on 9 October 2026 against a clean rebuild (`docker compose build --no-cache`). Environment: Windows 11, Docker 29.8 with Compose v5.5, Python 3.12.10, Node 24.21, Playwright 1.64 with its bundled Chromium.

## Summary

| Suite | Tool | Passed | Failed | Skipped | Blocked |
|---|---|---|---|---|---|
| Backend: unit | pytest | 31 | 0 | 0 | 0 |
| Backend: scientific integrity | pytest | 12 | 0 | 0 | 0 |
| Backend: API integration and experiment runner | pytest | 13 | 0 | 0 | 0 |
| Frontend: unit | Vitest | 5 | 0 | 0 | 0 |
| Frontend: type check | `tsc --noEmit` | clean | — | — | — |
| Browser end-to-end, desktop 1440×900 | Playwright | 14 | 0 | 0 | 0 |
| Browser end-to-end, mobile (Pixel 7 profile) | Playwright | 14 | 0 | 0 | 0 |
| Docker smoke test | `scripts/smoke-test.sh` | 9 checks | 0 | — | — |

Backend total: 56 passed (one deprecation warning from the test client library, unrelated to this code). Browser total: 28 passed.

## Commands

```bash
# backend (from backend/)
pip install -r requirements-dev.txt
python -m pytest

# frontend unit tests and type check (from frontend/)
npm ci
npx tsc --noEmit
npm test

# browser tests: the stack must be running on http://localhost:8080
docker compose up --build -d
cd frontend && npx playwright install chromium && npm run e2e

# Docker smoke test (from the repository root, stack running)
bash scripts/smoke-test.sh
```

## Backend unit tests — `backend/tests/test_simulation.py`

| Area | What is asserted |
|---|---|
| Agent movement | One speed unit per unblocked step; agents never enter a wall or leave the arena over 400 steps; walking distance to the nest never jumps (no tunnelling through walls); a blocked agent stays put. |
| Local perception limits | Food is invisible beyond patch radius + 4 cells and behind walls; antenna rays report walls and read no pheromone or scent through them. |
| Food pickup | The source is decremented, the agent turns around; a nearly empty source is not over-harvested and relocates. |
| Food delivery | Counted once; first-delivery step and required-distance bookkeeping are correct. |
| Pheromone deposition | Carriers deposit only in communicating worlds; searchers never deposit; deposits fade with time since pickup. |
| Evaporation and diffusion | Exact decay; cap enforced; diffusion spreads without creating pheromone. |
| Pheromone response | With no pheromone the three-way choice is uniform; with pheromone it is strongly but not deterministically biased; blocked rays are never chosen; carriers follow nest scent and ignore pheromone. |
| Communication disablement | After the cut, observations contain no pheromone and nothing is deposited. |
| Dynamic obstacle | Cells are blocked; everything stays reachable; a wall on the nest is refused. |
| Metrics | Undefined metrics are `None`, not 0; values after a run match their definitions; traffic concentration is 0.05 for uniform traffic and 1 for a single cell; statistics helpers handle missing values. |
| Seed reproducibility | Same seed gives an identical state hash and delivery history in each of the three world modes; different seeds differ. |

## Scientific integrity tests — `backend/tests/test_integrity.py`

| Test | Why it matters |
|---|---|
| World configs differ only in `communication` and `interruption_step` | Nothing else can explain a difference between worlds. |
| Worlds start from the identical map, food and agents | Matched initial conditions. |
| Independent world never deposits or senses pheromone | The control really has no channel. |
| Independent world ignores a pheromone field planted by hand | The control does not read the field even if one existed. |
| Collective world uses the declared mechanism | Deposits and sensing actually occur. |
| Collective equals independent until the first deposit | The baseline is not weakened in any hidden way. |
| **Collective with deposit strength 0 equals independent exactly** | Any advantage can only come through the pheromone field. There is no hidden bonus, route or memory attached to the collective mode. |
| Interrupted world matches collective exactly until the cut | The intervention starts from a common state. |
| Interrupted world stops all communication at the configured step | After the cut no deposit is added and no pheromone is read, while the old field remains and only fades. |
| The decision function cannot see the world | Its parameters are local observations; its source may not mention the world, map, food coordinates or obstacle grid. |
| Trails are not hardcoded | Each map's pheromone lies along its own nest-to-food lines (over 90% of mass) and fits another map's layout clearly worse. |
| Step batching does not change the outcome | Rendering speed cannot alter results. |

## API integration tests — `backend/tests/test_api.py`

Health and defaults; session creation with three matched worlds; stepping; **API state equals a direct engine run** (metrics, delivery series and agent positions for all three worlds — this is the "what the dashboard shows is what the engine measured" check at the API boundary); scheduled and manual interruption; obstacle insertion in every world; refusal and rollback of an invalid wall; exploratory-mode flagging; input validation and unknown sessions; the quick experiment returns real simulation output; stored-results endpoint; the experiment runner produces every file and is reproducible with 1 and with 2 worker processes.

## Browser end-to-end tests — `frontend/e2e/dashboard.spec.ts`

Run in real Chromium against the Docker stack, once per viewport profile.

| Scenario | Checks |
|---|---|
| Initial page load | Title, three world panels, canvases contain drawn pixels, matched initial agents. |
| Layout | Desktop: three panels in one row. Mobile: stacked. No horizontal overflow in either. A screenshot is captured and its size checked. |
| Start, pause, reset | Step counter advances, freezes, and returns to 0. |
| Keyboard | Start with Enter, change speed with the arrow key, pause with Space. |
| New scenario | A different seed and a different wall layout load. |
| Changing settings | Agent count (slider, keyboard) and pheromone strength are applied only through a restart; the run is labelled exploratory with the reason. |
| World C intervention, scheduled | Communication is off from the configured step; chip, log and backend state agree; World B is unaffected. |
| World C intervention, manual | Same, triggered by the button. |
| Obstacle insertion | By button and by Shift-click on the canvas; all three worlds receive the wall; the run continues. |
| Pheromone rendering | Trail-coloured pixels exist in the collective canvas, none in the independent canvas, none after "Show pheromone" is unticked. |
| Charts and numbers | Displayed deliveries, the chart's series and the table equal a fresh `GET` of the session from the backend; the chart canvas contains series-coloured pixels; hovering shows the tooltip. |
| Focus and comparison modes | One world visible, then all three. |
| Stored experiment | The table shows the stored mean and seed count. |
| Running an experiment | The quick experiment completes and renders 4 seed rows plus a mean. |
| Console errors and failed requests | Every test fails if the browser logs a console error, a page error, a failed request, or any HTTP status of 400 or above. None occurred. |

### What "real browser interaction" means here, and its limits

- Clicks, mouse movement, Shift-click, typing and key presses are issued through Playwright's input API, which drives Chromium's own input pipeline. No test dispatches synthetic DOM events.
- The browser is **headless** Chromium. Firefox and Safari/WebKit were not tested.
- The "mobile" profile is Chromium emulating a Pixel 7 viewport, pixel ratio and user agent. It is **not** a physical phone, and touch gestures were not exercised: taps are delivered as clicks. Shift-click has no touch equivalent, so wall placement at a chosen point is effectively desktop-only (the *Inject obstacle* button works everywhere).
- Speed select is changed with the keyboard in one test and through `selectOption` in helpers.
- Canvas checks count pixels by colour. They show that trails, agents and chart lines are drawn; they do not verify that every agent is drawn at the correct coordinate. Positional correctness rests on the API-equals-engine test plus visual review of the screenshots.
- Frame rate was measured once by hand, not asserted in a test: about 60 rendered frames per second in headless Chromium at 1600×1000 while the simulation ran.

## Docker validation

Performed on a clean state: `docker compose down`, `docker compose build --no-cache`, `docker compose up -d`.

| # | Check | Result |
|---|---|---|
| 1 | Fresh build | Both images built without cache. |
| 2 | Container startup | `api` and `web` up; `web` waits for `api` to be healthy. |
| 3 | Backend health | `{"status":"ok","version":"1.0.0"}` through the web port. |
| 4 | Frontend availability | Page served at http://localhost:8080 with the expected title. |
| 5 | Simulation initialization | Session created; after 600 steps: independent 129, collective 300, breakdown 300 deliveries (seed 1). |
| 6 | Intervention | Obstacle applied to all worlds. |
| 7 | Experiment through the API | Quick experiment returned means for three worlds. |
| 8 | Experiment execution in the container | `docker compose exec api python -m app.experiments.run` completed: 580 runs in 339 s (an earlier identical run took 288 s) and wrote all result files. A reduced run is part of the smoke script. |
| 9 | Results generation | `summary.json`, `runs.csv`, `series.json` and six charts present; served by the API. |
| 10 | Logs | `docker compose logs` contained no error or traceback lines. |
| 11 | Clean shutdown | `docker compose down` removed containers and network; `experiments/results/` on the host was untouched. |

## Known limitations of the testing

- No continuous integration; tests were run locally on one machine.
- No load or long-duration soak tests. Sessions are capped at 16 in memory.
- No cross-browser or physical-device testing (see above).
- Video and audio were validated by measurement and by inspecting extracted frames, not by a human listening test — see [demo-video/validation.md](demo-video/validation.md).
- Cross-platform numeric identity is not guaranteed (see [experiment-design.md](experiment-design.md#reproduction)).
