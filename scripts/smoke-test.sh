#!/usr/bin/env bash
# Docker smoke test: assumes `docker compose up --build -d` has been run.
# Checks health, the web page, a live three-world session, an intervention,
# a quick experiment through the API and the experiment CLI inside the container.
set -euo pipefail
URL="${SWARM_URL:-http://localhost:8080}"
export MSYS_NO_PATHCONV=1  # keep Git Bash on Windows from rewriting container paths

# The expression passed to json() is always a literal written in this file (never external input).
json() { python -c "import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1]))" "$1"; }
post() { curl -fsS -X POST -H 'Content-Type: application/json' -d "$2" "$URL$1"; }

echo "1. services";            docker compose ps --format '{{.Service}}: {{.Status}}'
echo "2. backend health:       $(curl -fsS "$URL/api/health")"
PAGE=$(curl -fsS "$URL/")
[[ "$PAGE" == *"<title>Swarm Mind"* ]] || { echo "frontend page is missing its title"; exit 1; }
echo "3. frontend:             page served, title present (${#PAGE} bytes)"
SID=$(post /api/session '{"seed": 1}' | json "d['session_id']")
echo "4. session initialised:  $SID"
for _ in 1 2 3; do post "/api/session/$SID/step" '{"n": 200}' > /dev/null; done
echo "5. after 600 steps:      $(post "/api/session/$SID/step" '{"n": 1}' | json "{m: w['metrics']['food_delivered'] for m, w in d['worlds'].items()}")"
echo "6. obstacle applied:     $(post "/api/session/$SID/obstacle" '{}' | json "d['applied']")"
echo "7. quick experiment:     $(post /api/experiments/quick '{"seeds": 2, "steps": 400}' | json "{m: v['mean'] for m, v in d['food_delivered'].items()}")"
echo "8. experiment CLI (reduced, written to a scratch dir inside the container):"
docker compose exec -T api python -m app.experiments.run --seeds 2 --steps 400 --out /tmp/smoke | sed 's/^/     /'
docker compose exec -T api ls /tmp/smoke | tr '\n' ' '; echo
echo "9. stored results:       available=$(curl -fsS "$URL/api/experiments/results" | json "d['available']")"
echo "SMOKE TEST PASSED"
