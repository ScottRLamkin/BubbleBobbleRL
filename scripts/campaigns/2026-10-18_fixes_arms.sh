#!/bin/zsh
# Bounded experiment after the October 18 review fixes. Eight from-scratch
# arms, one CPU core each (OMP_NUM_THREADS=1, Apple M4 Pro performance core),
# 60 minutes of wall time each INCLUDING the standard test every 1M steps
# (99 levels x 10 episodes, seed 4242, ~20 s each; best.pt kept on it).
# Afterwards every arm's best.pt and final model.pt are scored on held-out
# seeds 777 and 92731 with per-level outcomes saved. Training seed 101 for
# all arms; levels 1-99 unless stated.
#
# Arms (each line states what it isolates against the previous one):
#  A  control: the recipe used so far (time 0.01, still 0.005/32px/8s, death 5,
#     timeout 4, 4-minute training cap, no control state in the observation)
#  B  A + control state observed (prev jump/shoot, jump counter, time left)   -> critique 3
#  C  B + training cap 1 minute = the standard test's cap (timeout is termination) -> critique 5
#  D  C + explicit kill/clear objective: no score reward, kill bonus 2        -> critique 4
#  E  D + entropy 0.03 (broader exploration)                                   -> critique 2
#  F  D + random start positions (behavioural diversity)                     -> critique 2
#  G  D + egocentric observation                                              -> representation
#  H  D on levels 1-10 only (does combat/movement get learned on a small varied set) -> review rec. 3
# Success: held-out clears above A by more than 30/990 with movement or kill
# evidence in the behaviour profile. Futility: best unchanged over 20M steps.
set -e
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
source scripts/campaigns/mlflow_env.sh
COMMON=(--levels 1-99 --time-penalty 0.01 --stationary-penalty 0.005 --stationary-window 120 --stationary-band 32
        --death-penalty 5 --timeout-penalty 4 --seed 101 --total-steps 400000000 --max-minutes 60
        --eval-every 1000000 --log-every 20 --no-tensorboard --quiet --experiment fixes-1018)
KILLOBJ=(--control-obs --max-episode-frames 3600 --no-score-reward --kill-bonus 2)
run() { local name=$1; shift; uv run python scripts/train_ppo.py "$@" --run-name $name > runs/$name.log 2>&1 & }

run X1_A_control        "${COMMON[@]}" --max-episode-frames 14400
run X2_B_controlobs     "${COMMON[@]}" --max-episode-frames 14400 --control-obs
run X3_C_cap1min        "${COMMON[@]}" --max-episode-frames 3600 --control-obs
run X4_D_killobj        "${COMMON[@]}" "${KILLOBJ[@]}"
run X5_E_killobj_ent03  "${COMMON[@]}" "${KILLOBJ[@]}" --ent-coef 0.03
run X6_F_killobj_randstart "${COMMON[@]}" "${KILLOBJ[@]}" --random-start
run X7_G_killobj_ego    "${COMMON[@]}" "${KILLOBJ[@]}" --obs ego
run X8_H_killobj_levels10 "${COMMON[@]}" "${KILLOBJ[@]}" --levels 1-10
wait
echo "arms done: $(date)"

mkdir -p runs/analysis/fixes-1018
for r in X1_A_control X2_B_controlobs X3_C_cap1min X4_D_killobj X5_E_killobj_ent03 X6_F_killobj_randstart X7_G_killobj_ego X8_H_killobj_levels10; do
  flags=(); [[ $r == X2* || $r == X3* || $r == X[4-8]* ]] && flags+=(--control-obs); [[ $r == X7* ]] && flags+=(--obs ego)
  for ck in best final; do
    f=runs/$r/best.pt; [[ $ck == final ]] && f=runs/$r/model.pt
    for seed in 777 92731; do
      uv run python scripts/evaluate.py $f --seed $seed "${flags[@]}" --per-level-out runs/analysis/fixes-1018/${r}_${ck}_seed${seed}.json 2>/dev/null | sed "s|^|$r $ck seed $seed: |" | tee -a runs/analysis/fixes-1018/heldout.txt &
    done
  done
  wait
done
echo "held-out scoring done: $(date)"
