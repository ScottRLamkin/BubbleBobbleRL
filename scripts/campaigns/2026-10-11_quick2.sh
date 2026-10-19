#!/bin/zsh
# Quick round 2: does ordering observation slots by distance (slot 0 = the
# closest enemy/bubble/shot) make the task learnable by a small MLP?
# Eight 20M-step runs on all 100 levels, all-level evaluation every 1M steps.
set -e
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
source scripts/campaigns/mlflow_env.sh
COMMON=(--levels 1-100 --total-steps 20000000 --eval-every 1000000 --no-tensorboard --quiet --experiment quick-1011)
SHAPED=(--time-penalty 0.01 --stationary-penalty 0.005 --stationary-window 120 --stationary-band 32 --death-penalty 5)
run() { local name=$1; shift; uv run python scripts/train_ppo.py "$@" --run-name $name > runs/$name.log 2>&1 & }

run R1_near_state         "${COMMON[@]}" --nearest-first --seed 41
run R2_near_state_shaped  "${COMMON[@]}" --nearest-first "${SHAPED[@]}" --seed 42
run R3_near_ego           "${COMMON[@]}" --nearest-first --obs ego --seed 43
run R4_near_ego_shaped    "${COMMON[@]}" --nearest-first --obs ego "${SHAPED[@]}" --seed 44
run R5_near_state_g995    "${COMMON[@]}" --nearest-first --gamma 0.995 --gae-lambda 0.97 --seed 45
run R6_near_ego_g995      "${COMMON[@]}" --nearest-first --obs ego --gamma 0.995 --gae-lambda 0.97 --seed 46
run R7_near_state_seed2   "${COMMON[@]}" --nearest-first --seed 47
run R8_plain_state_seed2  "${COMMON[@]}" --seed 48
wait
echo "quick round 2 done"
