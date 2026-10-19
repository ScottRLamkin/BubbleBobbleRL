#!/bin/zsh
# Memory watchdog: if free + inactive memory drops under the floor, stop the
# training processes (they keep their best.pt) and the MLflow server rather
# than let macOS swap until it panics (which happened on 2026-10-14).
FLOOR_GB=${MEMWATCH_FLOOR_GB:-2}
while true; do
  free=$(vm_stat | awk '/Pages free/ {f=$3} /Pages inactive/ {i=$3} /Pages speculative/ {s=$3} END {gsub(/\./,"",f); gsub(/\./,"",i); gsub(/\./,"",s); print (f+i+s)*16384/1e9}')
  if (( free < FLOOR_GB )); then
    echo "$(date) free+inactive ${free} GB < ${FLOOR_GB} GB: stopping training" 
    pkill -f "scripts/train_ppo.py"; pkill -f "scripts/evolve.py"; pkill -f "mlflow server"
    exit 1
  fi
  sleep 30
done
