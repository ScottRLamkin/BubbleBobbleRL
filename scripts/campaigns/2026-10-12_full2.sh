#!/bin/zsh
# Stage 1, twice more (seeds 7-12 and 13-18), now with a timeout penalty
# (running out the clock is nearly as bad as dying) and without level 100
# (its boss is not implemented; the level cannot be cleared). Then Stage 2
# from four bases: the best of each new batch plus the two best of the first
# batch (seeds 1 and 2), one shared evolution.
set -e
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
source scripts/campaigns/mlflow_env.sh
RECIPE=(--levels 1-99 --time-penalty 0.01 --stationary-penalty 0.005 --stationary-window 120 --stationary-band 32
        --death-penalty 5 --timeout-penalty 4 --total-steps 200000000 --eval-every 1000000
        --no-tensorboard --quiet --experiment full-1012)
score() { uv run python scripts/evaluate.py $1 --episodes 10 --seed 4242 2>/dev/null | sed -E 's/.*cleared ([0-9]+)\/[0-9]+.*/\1/'; }

for batch in "7 8 9 10 11 12" "13 14 15 16 17 18"; do
  for s in ${=batch}; do
    uv run python scripts/train_ppo.py "${RECIPE[@]}" --seed $s --run-name F_scratch200M_s$s > runs/F_scratch200M_s$s.log 2>&1 &
  done
  wait
  echo "batch $batch done: $(date)"
done

BASES=(runs/F_scratch200M_s1/model.pt runs/F_scratch200M_s2/model.pt)
for batch in "7 8 9 10 11 12" "13 14 15 16 17 18"; do
  best=""; bestn=-1
  for s in ${=batch}; do
    n=$(score runs/F_scratch200M_s$s/model.pt); echo "seed $s: cleared $n/990"
    if [ "$n" -gt "$bestn" ]; then bestn=$n; best=runs/F_scratch200M_s$s/model.pt; fi
  done
  echo "best of batch: $best ($bestn/990)"; BASES+=($best)
done
echo "stage 2 bases: ${BASES[@]}"
uv run python scripts/evolve.py --base "${BASES[@]}" --timeout-penalty 4 --name full1012b --generations 10 --population 24 --survivors 10 --steps 8000000 --workers 8
echo "stage 2 done: $(date)"
