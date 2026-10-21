#!/usr/bin/env bash
# Build, run and scan this example for leaks of the template in server/skills.ts.
set -euo pipefail
cd "$(dirname "$0")"
SCAN=../../skills/protect-skill-prompts/scripts/scan_leaks.py
PORT=${PORT:-4319}

npx next build >/dev/null
npx next start -p "$PORT" >/dev/null 2>&1 &
SERVER=$!
trap 'kill $SERVER' EXIT
for _ in $(seq 1 30); do curl -sf -o /dev/null "localhost:$PORT" && break; sleep 1; done

mkdir -p .verify
curl -s -XPOST "localhost:$PORT/api/generate" \
  -d '{"skillId":"product-stylist","choices":{"style":"studio"},"userRequest":"make the bottle matte black"}' > .verify/generate.json
curl -s -XPOST "localhost:$PORT/api/generate" -d '{"skillId":"product-stylist","choices":{"style":"nope"}}' > .verify/invalid.json

FRAGMENT=$(grep '^const TEMPLATE' server/skills.ts | cut -c21-320)
if python3 "$SCAN" --secrets server/skills.ts --text "$FRAGMENT" >/dev/null; then
  echo "1. positive control FAILED: a planted fragment was not detected"; exit 1
fi
echo "1. positive control: planted fragment detected"
echo "2. client bundle, page and API responses (should be clean):"
python3 "$SCAN" --secrets server/skills.ts .next/static .verify --url "http://localhost:$PORT/stylist"
