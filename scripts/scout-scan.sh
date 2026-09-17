#!/usr/bin/env bash
# Seed Anthracite capabilities if no profile exists, scan DSIP, write a digest,
# and ping the desktop when something looks worth a look. Never runs the council.
set -euo pipefail

API="${SCOUT_API:-http://127.0.0.1:8000}"
SHARE="${XDG_DATA_HOME:-$HOME/.local/share}/scout"
REPO="/home/melgar/Desktop/scout"
PACK="$REPO/data/anthracite-capabilities.md"
THRESHOLD="${SCOUT_MATCH_MIN:-18}"
TOP_N="${SCOUT_DIGEST_N:-8}"

mkdir -p "$SHARE"

wait_api() {
  local i
  for i in $(seq 1 30); do
    if curl -sf "$API/api/system/health" >/dev/null; then
      return 0
    fi
    sleep 2
  done
  echo "SCOUT API not up at $API" >&2
  return 1
}

cd "$REPO"
/usr/bin/docker compose up -d >/dev/null
wait_api

active="$(curl -sf "$API/api/resume/active" || echo null)"
if [ "$active" = "null" ] || [ -z "$active" ]; then
  python3 - "$API" "$PACK" <<'PY'
import json, pathlib, sys, urllib.request
api, pack = sys.argv[1], pathlib.Path(sys.argv[2])
body = json.dumps({"name": "Anthracite capabilities", "text": pack.read_text()}).encode()
req = urllib.request.Request(
    f"{api}/api/resume/text", data=body,
    headers={"Content-Type": "application/json"}, method="POST",
)
urllib.request.urlopen(req, timeout=60).read()
PY
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
if ! curl -sf -X POST "$API/api/matches/scan" -o "$tmp"; then
  echo "scan failed" >&2
  exit 1
fi

python3 - "$SHARE" "$THRESHOLD" "$TOP_N" "$tmp" <<'PY'
import json, os, subprocess, sys
from datetime import datetime

share, thresh, topn, src = sys.argv[1], float(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
data = json.loads(open(src).read())
matches = data.get("matches") or []
good = [m for m in matches if float(m.get("score") or 0) >= thresh][:topn]
if not good:
    good = matches[: min(5, len(matches))]
path = os.path.join(share, "inbox.md")
prev_path = os.path.join(share, "seen-ids.txt")
seen = set()
if os.path.exists(prev_path):
    seen = {ln.strip() for ln in open(prev_path) if ln.strip()}
new = [m for m in good if m.get("topic_id") not in seen]
lines = [
    f"# SCOUT inbox — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    "",
    f"Scanned {data.get('match_count', len(matches))} open topics against "
    f"**{(data.get('resume') or {}).get('name', 'profile')}**.",
    f"Queries: {', '.join(data.get('queries') or []) or '—'}",
    "",
]
for m in good:
    flag = "NEW" if m.get("topic_id") not in seen else "keep"
    code = m.get("topic_code") or m.get("topic_id")
    title = m.get("title") or ""
    why = "; ".join((m.get("reasons") or [])[:3])
    score = float(m.get("score") or 0)
    lines.append(f"- **{flag}** `{code}` ({score:.0f}) {title}")
    if why:
        lines.append(f"  - {why}")
    lines.append(f"  - http://localhost:8080/topic/{m.get('topic_id')}")
lines += ["", "Open the inbox: http://localhost:8080"]
open(path, "w").write("\n".join(lines) + "\n")
with open(prev_path, "w") as f:
    for m in matches:
        if m.get("topic_id"):
            f.write(m["topic_id"] + "\n")
n_new = len(new)
top = good[0] if good else None
summary = "No strong matches this scan."
if top:
    label = f"{top.get('topic_code') or ''} {top.get('title') or ''}".strip()
    if n_new:
        summary = f"{n_new} new fit{'s' if n_new != 1 else ''} (top: {label[:80]})"
    else:
        summary = f"{len(good)} ranked (top: {label[:80]})"
print(summary)
if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
    if n_new or (top and float(top.get("score") or 0) >= thresh):
        subprocess.run(
            ["notify-send", "-a", "SCOUT", "-u", "normal", "SCOUT found topics", summary],
            check=False,
        )
PY
