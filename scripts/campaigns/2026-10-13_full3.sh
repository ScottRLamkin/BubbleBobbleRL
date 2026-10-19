#!/bin/zsh
# Round 3 of the full pipeline, with the fix the previous rounds exposed:
# a run's result is now its best evaluated checkpoint (best.pt), not whatever
# the last update happened to be (final checkpoints scored 8-72 of 990 while
# the best along the way scored 59-113). Six seeds x 200M, then each best.pt
# is scored on the standard seed and on an independent seed (777) so the
# winner's-curse inflation of "best of 200 evaluations" is measured, then
# the four best seed the shared evolution.
set -e
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
source scripts/campaigns/mlflow_env.sh
RECIPE=(--levels 1-99 --time-penalty 0.01 --stationary-penalty 0.005 --stationary-window 120 --stationary-band 32
        --death-penalty 5 --timeout-penalty 4 --total-steps 200000000 --eval-every 1000000
        --no-tensorboard --quiet --experiment full-1013)
score() { uv run python scripts/evaluate.py $1 --seed $2 2>/dev/null | sed -E 's/.*cleared ([0-9]+)\/[0-9]+.*/\1/'; }

for s in 19 20 21 22 23 24; do
  uv run python scripts/train_ppo.py "${RECIPE[@]}" --seed $s --run-name F3_scratch200M_s$s > runs/F3_scratch200M_s$s.log 2>&1 &
done
wait
echo "stage 1 done: $(date)"

: > runs/full1013_scores.txt
for s in 19 20 21 22 23 24; do
  a=$(score runs/F3_scratch200M_s$s/best.pt 4242); b=$(score runs/F3_scratch200M_s$s/best.pt 777); f=$(score runs/F3_scratch200M_s$s/model.pt 777)
  echo "seed $s: best.pt standard $a/990, best.pt independent-seed $b/990, final model.pt independent-seed $f/990" | tee -a runs/full1013_scores.txt
done
BASES=($(sort -t' ' -k6 -n -r runs/full1013_scores.txt | head -4 | sed -E 's/seed ([0-9]+):.*/runs\/F3_scratch200M_s\1\/best.pt/'))
echo "stage 2 bases (top 4 by independent-seed score): ${BASES[@]}"
uv run python scripts/evolve.py --base "${BASES[@]}" --timeout-penalty 4 --name full1013 --generations 10 --population 24 --survivors 10 --steps 8000000 --workers 8
echo "stage 2 done: $(date)"
