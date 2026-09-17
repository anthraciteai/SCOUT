#!/usr/bin/env bash
set -euo pipefail
cd /home/melgar/Desktop/scout
/usr/bin/docker compose up -d >/tmp/scout-up.log 2>&1 || true
xdg-open http://localhost:8080 >/dev/null 2>&1 || true
