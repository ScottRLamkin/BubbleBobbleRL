#!/bin/zsh
# Wave B: follow the one lead from wave A - the ego observation learned a
# 10-level pool better than the state observation and better than the
# all-levels champion plays those levels. Push on it from several sides.
set -e
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
source scripts/campaigns/mlflow_env.sh
CHAMP=runs/evolve/evo10/gen_10/g10m08/model.pt
A6=runs/A6_levels10_ego_100M/model.pt
BASE=(--time-penalty 0.01 --stationary-penalty 0.005 --stationary-window 120 --stationary-band 32 --death-penalty 5 --no-tensorboard --quiet --experiment campaign-1011)
run() { local name=$1; shift; uv run python scripts/train_ppo.py "$@" --run-name $name > runs/$name.log 2>&1 & }

run B1_ego10_cont_lr1e-4_100M  "${BASE[@]}" --levels 1-10 --obs ego --init-model $A6 --lr 1e-4 --total-steps 100000000 --seed 21
run B2_ego20_scratch_100M      "${BASE[@]}" --levels 1-20 --obs ego --total-steps 100000000 --seed 22
run B3_ego10_explore05_100M    "${BASE[@]}" --levels 1-10 --obs ego --explore-bonus 0.5 --total-steps 100000000 --seed 23
run B4_ego10_randomstart_100M  "${BASE[@]}" --levels 1-10 --obs ego --random-start --total-steps 100000000 --seed 24
run B5_ego100_from_ego10_100M  "${BASE[@]}" --levels 1-100 --obs ego --init-model $A6 --lr 1e-4 --total-steps 100000000 --seed 25
run B6_state10_cont_lr1e-4_100M "${BASE[@]}" --levels 1-10 --init-model runs/A5_levels10_state_100M/model.pt --lr 1e-4 --total-steps 100000000 --seed 26
run B7_ego10_death2_100M       "${BASE[@]}" --levels 1-10 --obs ego --death-penalty 2 --total-steps 100000000 --seed 27
run B8_champ_lr3e-5_100M       "${BASE[@]}" --levels 1-100 --init-model $CHAMP --lr 3e-5 --total-steps 100000000 --seed 28
wait
echo "wave B done"
