#!/usr/bin/env bash
# Runs every browser check, each against its own fresh demo server, so no suite inherits another's data.
#   bash scripts/ui_all.sh [suite ...]        (default: all five)
set -u
cd "$(dirname "$0")/.."
SUITES=${*:-"ui_check platform_ui_check team_ui_check layout_ui_check docs_ui_check look_ui_check"}
PORT=${PORT:-8765}
SHOTS=${SHOTS:-/tmp/claude-0/shots}
mkdir -p "$SHOTS"
bad=0
for s in $SUITES; do
  fuser -k "$PORT"/tcp >/dev/null 2>&1
  sleep 1
  # These suites exercise the plan rules (and the dev plan switch), so they need a server without the owner unlock.
  case "$s" in ui_check | platform_ui_check | team_ui_check) unlock=0 ;; *) unlock=1 ;; esac
  UNLOCK_ALL=$unlock FAKE_DELAY=0 python3 backend/tests/demo_server.py "$PORT" >"/tmp/demo-$s.log" 2>&1 &
  pid=$!
  for _ in $(seq 1 40); do curl -s -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 0.5; done
  echo "===== $s"
  node "scripts/$s.cjs" "http://127.0.0.1:$PORT" "$SHOTS" || bad=$((bad + 1))
  kill "$pid" 2>/dev/null
  wait "$pid" 2>/dev/null
done
echo
[ "$bad" = 0 ] && echo "every browser suite passed" || echo "$bad suite(s) FAILED"
exit $([ "$bad" = 0 ] && echo 0 || echo 1)
