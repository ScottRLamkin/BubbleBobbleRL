#!/bin/zsh
# Wave A of the 10-hour campaign (eight runs in parallel, ~2.5 h).
# Questions: how far does the champion go at the right learning rate; does
# paying for ground covered produce movement; can a moving agent be learned
# on 10 levels instead of 100.
set -e
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
CHAMP=runs/evolve/evo10/gen_10/g10m08/model.pt
BASE=(--time-penalty 0.01 --stationary-penalty 0.005 --stationary-window 120 --stationary-band 32 --death-penalty 5 --no-tensorboard --quiet --experiment campaign-1011)
run() { local name=$1; shift; uv run python scripts/train_ppo.py "$@" --run-name $name > runs/$name.log 2>&1 & }

run A1_champ_lr5e-5_100M     "${BASE[@]}" --levels 1-100 --init-model $CHAMP --lr 5e-5 --total-steps 100000000 --seed 11
run A2_champ_lr1e-4_100M     "${BASE[@]}" --levels 1-100 --init-model $CHAMP --lr 1e-4 --total-steps 100000000 --seed 12
run A3_explore05_scratch_100M "${BASE[@]}" --levels 1-100 --explore-bonus 0.5 --total-steps 100000000 --seed 13
run A4_explore05_champ_50M   "${BASE[@]}" --levels 1-100 --explore-bonus 0.5 --init-model $CHAMP --lr 5e-5 --total-steps 50000000 --seed 14
run A5_levels10_state_100M   "${BASE[@]}" --levels 1-10 --total-steps 100000000 --seed 15
run A6_levels10_ego_100M     "${BASE[@]}" --levels 1-10 --obs ego --total-steps 100000000 --seed 16
run A7_explore1_still05_scratch_100M "${BASE[@]}" --levels 1-100 --explore-bonus 1.0 --stationary-penalty 0.05 --total-steps 100000000 --seed 17
run A8_explore05_levels10_100M "${BASE[@]}" --levels 1-10 --explore-bonus 0.5 --total-steps 100000000 --seed 18
wait
echo "wave A done"
