#!/bin/zsh
# Quick round 1: eight 20M-step runs on all 100 levels, evaluated on all 100
# levels every 1M steps (2 episodes per level, ~4 s). Compares fundamentals
# of the plumbing rather than reward tweaks. ~25 minutes.
set -e
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
source scripts/campaigns/mlflow_env.sh
COMMON=(--levels 1-100 --total-steps 20000000 --eval-every 1000000 --no-tensorboard --quiet --experiment quick-1011)
SHAPED=(--time-penalty 0.01 --stationary-penalty 0.005 --stationary-window 120 --stationary-band 32 --death-penalty 5)
run() { local name=$1; shift; uv run python scripts/train_ppo.py "$@" --run-name $name > runs/$name.log 2>&1 & }

run Q1_shaped_state       "${COMMON[@]}" "${SHAPED[@]}" --seed 31
run Q2_plain_state        "${COMMON[@]}" --seed 32
run Q3_plain_ego          "${COMMON[@]}" --obs ego --seed 33
run Q4_plain_frameskip2   "${COMMON[@]}" --frame-skip 2 --seed 34
run Q5_plain_lives3       "${COMMON[@]}" --lives 3 --seed 35
run Q6_plain_bigbatch     "${COMMON[@]}" --num-envs 32 --rollout-len 256 --seed 36
run Q7_plain_gamma995     "${COMMON[@]}" --gamma 0.995 --gae-lambda 0.97 --seed 37
run Q8_plain_ent03        "${COMMON[@]}" --ent-coef 0.03 --seed 38
wait
echo "quick round 1 done"
