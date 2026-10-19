#!/bin/zsh
# Round 4: same protocol as round 3 (best.pt, independent-seed scoring), with
# stage 1 doubled to 400M steps since the best seed was still climbing at
# 200M. Stage 2 from the top four best.pt plus the round-3 champion.
set -e
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
source scripts/campaigns/mlflow_env.sh
RECIPE=(--levels 1-99 --time-penalty 0.01 --stationary-penalty 0.005 --stationary-window 120 --stationary-band 32
        --death-penalty 5 --timeout-penalty 4 --total-steps 400000000 --eval-every 1000000
        --no-tensorboard --quiet --experiment full-1013)
score() { uv run python scripts/evaluate.py $1 --seed $2 2>/dev/null | sed -E 's/.*cleared ([0-9]+)\/[0-9]+.*/\1/'; }

for s in 25 26 27 28 29 30; do
  uv run python scripts/train_ppo.py "${RECIPE[@]}" --seed $s --run-name F4_scratch400M_s$s > runs/F4_scratch400M_s$s.log 2>&1 &
done
wait
echo "stage 1 done: $(date)"

: > runs/full1013b_scores.txt
for s in 25 26 27 28 29 30; do
  a=$(score runs/F4_scratch400M_s$s/best.pt 4242); b=$(score runs/F4_scratch400M_s$s/best.pt 777)
  echo "seed $s: best.pt standard $a/990, best.pt independent-seed $b/990" | tee -a runs/full1013b_scores.txt
done
BASES=($(sort -t' ' -k6 -n -r runs/full1013b_scores.txt | head -4 | sed -E 's/seed ([0-9]+):.*/runs\/F4_scratch400M_s\1\/best.pt/'))
BASES+=(runs/evolve/full1013/gen_10/g10m20/model.pt)
echo "stage 2 bases: ${BASES[@]}"
uv run python scripts/evolve.py --base "${BASES[@]}" --timeout-penalty 4 --name full1013b --generations 10 --population 25 --survivors 10 --steps 8000000 --workers 8
echo "stage 2 done: $(date)"
