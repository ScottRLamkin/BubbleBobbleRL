#!/bin/zsh
# Quick round 3: the first seconds are a lottery (on 64 of 100 levels an idle
# player is dead within 6 s). Give the learner a grace period before enemies
# enter and anneal it away; evaluation always uses no grace.
set -e
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
source scripts/campaigns/mlflow_env.sh
COMMON=(--levels 1-100 --total-steps 20000000 --eval-every 1000000 --no-tensorboard --quiet --experiment quick-1011)
SHAPED=(--time-penalty 0.01 --stationary-penalty 0.005 --stationary-window 120 --stationary-band 32 --death-penalty 5)
run() { local name=$1; shift; uv run python scripts/train_ppo.py "$@" --run-name $name > runs/$name.log 2>&1 & }

run G1_grace240_anneal50        "${COMMON[@]}" --grace-frames 240 --grace-anneal 0.5 --seed 51
run G2_grace240_anneal80        "${COMMON[@]}" --grace-frames 240 --grace-anneal 0.8 --seed 52
run G3_grace480_anneal80        "${COMMON[@]}" --grace-frames 480 --grace-anneal 0.8 --seed 53
run G4_grace240_anneal80_shaped "${COMMON[@]}" --grace-frames 240 --grace-anneal 0.8 "${SHAPED[@]}" --seed 54
run G5_grace240_anneal80_ego    "${COMMON[@]}" --grace-frames 240 --grace-anneal 0.8 --obs ego --seed 55
run G6_grace240_fixed           "${COMMON[@]}" --grace-frames 240 --seed 56
run G7_grace240_anneal80_lives3 "${COMMON[@]}" --grace-frames 240 --grace-anneal 0.8 --lives 3 --seed 57
run G8_plain_state_seed3        "${COMMON[@]}" --seed 58
wait
echo "quick round 3 done"
