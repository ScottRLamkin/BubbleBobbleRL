#!/bin/zsh
# The pipeline that produced the best agent, run at full length, no screening:
#   stage 1: from scratch, all 100 levels, the shaped reward the champion's
#            lineage settled on (time 0.01, still 0.005 over 32 px / 8 s,
#            death 5), state obs, lr 2.5e-4, 200M steps, six seeds in parallel
#            (~5 h). All-level evaluation every 1M steps (the cadence of the quick rounds).
#   stage 2: score the six on the standard seeds, take the best, and run the
#            evolution exactly as evo10 did (10 generations x 24 children x
#            8M steps, 12 mutating genes, lr mutations are what paid off).
set -e
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
source scripts/campaigns/mlflow_env.sh
RECIPE=(--levels 1-100 --time-penalty 0.01 --stationary-penalty 0.005 --stationary-window 120 --stationary-band 32 --death-penalty 5
        --total-steps 200000000 --eval-every 1000000 --no-tensorboard --quiet --experiment full-1012)
for s in 1 2 3 4 5 6; do
  uv run python scripts/train_ppo.py "${RECIPE[@]}" --seed $s --run-name F_scratch200M_s$s > runs/F_scratch200M_s$s.log 2>&1 &
done
wait
echo "stage 1 done: $(date)"

best=""; bestn=-1
for s in 1 2 3 4 5 6; do
  n=$(uv run python scripts/evaluate.py runs/F_scratch200M_s$s/model.pt --episodes 10 --seed 4242 2>/dev/null | sed -E 's/.*cleared ([0-9]+)\/1000.*/\1/')
  echo "seed $s: cleared $n/1000"
  if [ "$n" -gt "$bestn" ]; then bestn=$n; best=runs/F_scratch200M_s$s/model.pt; fi
done
echo "best: $best ($bestn/1000)"

uv run python scripts/evolve.py --base $best --name full1012 --generations 10 --population 24 --survivors 10 --steps 8000000 --workers 8
echo "stage 2 done: $(date)"
