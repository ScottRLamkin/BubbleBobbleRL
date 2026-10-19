#!/bin/zsh
# Replication and extension of fixes-1018 (same budget: 60 min wall, one core
# each, standard test every 1M steps, best.pt kept). Seeds 102/103.
#  R1 A control, seed 102            (noise estimate for the control)
#  R2 B +control obs, seed 102       (replicates the critique-3 effect)
#  R3 G, seed 102; R4 G, seed 103    (replicates the best arm)
#  R5 G continued: +60 min from runs/X7_G_killobj_ego/best.pt, optimizer resumed, lr 1e-4
#  R6 G + nearest-first slots;  R7 G + hidden 512;  R8 G + hard-level sampling
set -e
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
source scripts/campaigns/mlflow_env.sh
COMMON=(--levels 1-99 --time-penalty 0.01 --stationary-penalty 0.005 --stationary-window 120 --stationary-band 32
        --death-penalty 5 --timeout-penalty 4 --total-steps 400000000 --max-minutes 60
        --eval-every 1000000 --log-every 20 --no-tensorboard --quiet --experiment fixes-1018)
G=(--control-obs --max-episode-frames 3600 --no-score-reward --kill-bonus 2 --obs ego)
run() { local name=$1; shift; uv run python scripts/train_ppo.py "$@" --run-name $name > runs/$name.log 2>&1 & }

run R1_A_control_s102    "${COMMON[@]}" --max-episode-frames 14400 --seed 102
run R2_B_controlobs_s102 "${COMMON[@]}" --max-episode-frames 14400 --control-obs --seed 102
run R3_G_s102            "${COMMON[@]}" "${G[@]}" --seed 102
run R4_G_s103            "${COMMON[@]}" "${G[@]}" --seed 103
run R5_G_continued       "${COMMON[@]}" "${G[@]}" --seed 104 --init-model runs/X7_G_killobj_ego/best.pt --lr 1e-4
run R6_G_nearest         "${COMMON[@]}" "${G[@]}" --seed 105 --nearest-first
run R7_G_hidden512       "${COMMON[@]}" "${G[@]}" --seed 106 --hidden 512
run R8_G_hardlevels      "${COMMON[@]}" "${G[@]}" --seed 107 --level-sampling hard
wait
echo "arms done: $(date)"
mkdir -p runs/analysis/fixes-1018
for r in R1_A_control_s102 R2_B_controlobs_s102 R3_G_s102 R4_G_s103 R5_G_continued R6_G_nearest R7_G_hidden512 R8_G_hardlevels; do
  flags=(); [[ $r == R1* ]] || flags+=(--control-obs); [[ $r == R[3-8]* ]] && flags+=(--obs ego); [[ $r == R6* ]] && flags+=(--nearest-first)
  for ck in best final; do
    f=runs/$r/best.pt; [[ $ck == final ]] && f=runs/$r/model.pt
    for seed in 777 92731; do
      uv run python scripts/evaluate.py $f --seed $seed "${flags[@]}" --per-level-out runs/analysis/fixes-1018/${r}_${ck}_seed${seed}.json 2>/dev/null \
        | sed -E "s|^.*cleared ([0-9]+)/990 episodes \(([0-9]+) levels\), died ([0-9]+), timed out ([0-9]+), mean score ([0-9]+), kills/episode ([0-9.]+)|$r $ck seed$seed: cleared \1 levels \2 died \3 timeout \4 kills \6|" >> runs/analysis/fixes-1018/heldout_round2.txt &
    done
  done
  wait
done
echo "held-out scoring done: $(date)"
