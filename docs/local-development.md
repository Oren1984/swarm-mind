# Local development

## With Docker (recommended)

```bash
docker compose up --build        # build and start; dashboard at http://localhost:8080
docker compose ps                # both services should report "healthy"
docker compose logs              # add -f to follow
docker compose down              # stop and remove containers; no data is deleted
```

- Only the dashboard port is published. The API is reached through it at `/api/...`.
- **Port 8080 in use?** Set another one: `SWARM_WEB_PORT=8090 docker compose up --build` (PowerShell: `$env:SWARM_WEB_PORT=8090; docker compose up --build`), or copy `.env.example` to `.env` and edit it.
- The `experiments/` folder is mounted into the `api` container. Configs are read from it and results are written back to it, so they persist on your disk.
- No cloud credentials, API keys or paid services are involved.

Run the experiments inside the container:

```bash
docker compose exec api python -m app.experiments.run                         # full: ~5 min, rewrites experiments/results/
docker compose exec api python -m app.experiments.run --seeds 3 --steps 1000 --out /tmp/check   # quick check, scratch output
```

On Windows Git Bash, prefix commands that contain container paths with `MSYS_NO_PATHCONV=1` so `/tmp/check` is not rewritten.

After changing code, rebuild: `docker compose up --build -d`.

## Without Docker

Requirements: Python 3.12 and Node 24 (older recent versions probably work but were not tested).

**Backend**

```bash
cd backend
pip install -r requirements-dev.txt
python -m uvicorn app.main:app --port 8000
python -m pytest                      # tests
python -m app.experiments.run         # experiments; writes to ../experiments/results
```

**Frontend** (second terminal)

```bash
cd frontend
npm ci
npm run dev                           # http://localhost:5173, proxies /api to 127.0.0.1:8000
npm test                              # unit tests
npm run build                         # type check and production bundle
```

If the API runs elsewhere, set `SWARM_API_URL` before `npm run dev`.

**Browser tests** need a running stack. They default to http://localhost:8080; point them elsewhere with `SWARM_URL`:

```bash
npx playwright install chromium       # once
SWARM_URL=http://localhost:5173 npm run e2e
```

## Regenerating the media

All of these read from the running application or from stored results; none invents content.

```bash
# screenshots -> showcase/screenshots/   (stack must be running)
cd frontend && node tools/capture-screenshots.mjs

# screen recordings for the video -> build/footage/
node tools/record-footage.mjs ../build/footage

# narration, music, assembly, subtitles, validation -> showcase/video/
cd .. && python scripts/build_video.py
```

The video build additionally needs FFmpeg, Pillow, and — for narration — Windows with PowerShell 7 and an installed English SAPI voice. See [demo-video/production.md](demo-video/production.md).

## Where things are

| Path | Content |
|---|---|
| `backend/app/simulation/` | Engine: `world.py`, `agents.py`, `scenario.py` |
| `backend/app/config.py` | All parameters and the per-world differences |
| `backend/app/metrics.py` | Metric definitions |
| `backend/app/experiments/` | Runner, statistics, charts |
| `backend/app/main.py`, `session.py` | API and interactive sessions |
| `backend/tests/` | pytest suites |
| `frontend/src/` | Dashboard (`main.ts`, `simulation-view/`, `charts/`, `styles/`) |
| `frontend/e2e/`, `frontend/tests/` | Playwright and Vitest tests |
| `frontend/tools/` | Screenshot and footage capture |
| `experiments/configs/`, `experiments/results/` | What was run, and what came out |
| `scripts/` | Smoke test, video build, narration helper, video script |
| `build/` | Scratch output (git-ignored) |

## Changing the simulation

- Parameters live in `SimConfig`. A new parameter is shared by all worlds unless you add it to `world_overrides`, and the integrity test will then require you to declare it there.
- Agent behaviour lives only in `agents.decide`. If it needs a new input, add a field to `Observation` and fill it in `World.observe` from cells near the agent; the integrity test lists the allowed fields.
- Bump `__version__` in `backend/app/__init__.py` when behaviour changes, and re-run the experiments: stored results record the version that produced them.
