#!/usr/bin/env bash
set -euo pipefail
LOG="/Users/wthierry/Development/pc_booster_control/shutdown_monitor.log"
URL="http://192.168.5.149:8000/api/health"

echo "=== monitor start $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG"
while true; do
  ts=$(date '+%Y-%m-%d %H:%M:%S')
  json=$(curl -s --max-time 2 "$URL" || true)
  if [[ -z "$json" ]]; then
    echo "$ts OFFLINE" | tee -a "$LOG"
    break
  fi
  pct=$(printf '%s' "$json" | sed -n 's/.*"battery_percent":\([0-9][0-9]*\).*/\1/p')
  st=$(printf '%s' "$json" | sed -n 's/.*"battery_status":"\([^"]*\)".*/\1/p')
  src=$(printf '%s' "$json" | sed -n 's/.*"battery_source":"\([^"]*\)".*/\1/p')
  echo "$ts ONLINE battery_percent=${pct:-na} status=${st:-na} source=${src:-na}" | tee -a "$LOG"
  sleep 5
done

echo "=== monitor end $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG"
