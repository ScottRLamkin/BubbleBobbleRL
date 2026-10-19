#!/bin/zsh
# Round 3: does continuing the best arm keep paying, and is it the restart or
# the compute? Same per-arm budget (60 min wall, one core, standard test every
# 1M steps, best.pt kept) unless stated. All arms use recipe G (control obs,
# 1-minute cap, kill/clear objective, ego obs).
#  S1 R5_G_continued continued again (+60 min, lr 1e-4, optimizer resumed)   -> does the gain continue
#  S2 R4_G_s103 continued (+60 min, lr 1e-4)                                   -> replicate the continuation gain
#  S3 R3_G_s102 continued (+60 min, lr 1e-4)                                   -> replicate the continuation gain
#  S4 G from scratch with a 120-minute budget, seed 108                        -> compute-matched control for S2/S3 lineages (2 h total each)
#  S5 A control, seed 103;  S6 B control-obs, seed 103                        -> third paired seed for the A/B/G comparison (G seed 103 = R4)
#  (S7/S8 share S1's seed 110, so they are seed-matched single changes against S1)
#  S7 R5 continued with stationary penalty 0.02                                -> push movement on the strongest agent
#  S8 R5 continued with random start                                           -> push movement on the strongest agent
set -e
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
source scripts/campaigns/mlflow_env.sh
COMMON=(--levels 1-99 --time-penalty 0.01 --stationary-penalty 0.005 --stationary-window 120 --stationary-band 32
        --death-penalty 5 --timeout-penalty 4 --total-steps 800000000 --max-minutes 60
        --eval-every 1000000 --log-every 20 --no-tensorboard --quiet --experiment fixes-1018)
G=(--control-obs --max-episode-frames 3600 --no-score-reward --kill-bonus 2 --obs ego)
PIDS=(); NAMES=()
run() { local name=$1; shift; uv run python scripts/train_ppo.py "$@" --run-name $name > runs/$name.log 2>&1 & PIDS+=($!); NAMES+=($name); }

run S1_R5_cont2         "${COMMON[@]}" "${G[@]}" --seed 110 --init-model runs/R5_G_continued/best.pt --lr 1e-4
run S2_G103_cont        "${COMMON[@]}" "${G[@]}" --seed 111 --init-model runs/R4_G_s103/best.pt --lr 1e-4
run S3_G102_cont        "${COMMON[@]}" "${G[@]}" --seed 112 --init-model runs/R3_G_s102/best.pt --lr 1e-4
run S4_G_scratch120     "${COMMON[@]}" "${G[@]}" --seed 108 --max-minutes 120
run S5_A_control_s103   "${COMMON[@]}" --max-episode-frames 14400 --seed 103
run S6_B_controlobs_s103 "${COMMON[@]}" --max-episode-frames 14400 --control-obs --seed 103
run S7_R5_cont_still02  "${COMMON[@]}" "${G[@]}" --seed 110 --init-model runs/R5_G_continued/best.pt --lr 1e-4 --stationary-penalty 0.02
run S8_R5_cont_randstart "${COMMON[@]}" "${G[@]}" --seed 110 --init-model runs/R5_G_continued/best.pt --lr 1e-4 --random-start
fail=0
for i in {1..${#PIDS}}; do wait ${PIDS[$i]} || { echo "FAILED: ${NAMES[$i]} (see runs/${NAMES[$i]}.log)"; fail=1; }; done
echo "arms done: $(date) (failures: $fail)"
[[ $fail -eq 0 ]] || { echo "aborting before validation: a training arm failed"; exit 1; }
setopt pipefail
for r in S1_R5_cont2 S2_G103_cont S3_G102_cont S4_G_scratch120 S5_A_control_s103 S6_B_controlobs_s103 S7_R5_cont_still02 S8_R5_cont_randstart; do
  flags=(--control-obs --obs ego); [[ $r == S5* ]] && flags=(); [[ $r == S6* ]] && flags=(--control-obs)
  for ck in best final; do
    f=runs/$r/best.pt; [[ $ck == final ]] && f=runs/$r/model.pt
    for seed in 777 92731; do
      uv run python scripts/evaluate.py $f --seed $seed "${flags[@]}" --per-level-out runs/analysis/fixes-1018/${r}_${ck}_seed${seed}.json 2>> runs/analysis/fixes-1018/eval_errors_round3.log \
        | sed -E "s|^.*cleared ([0-9]+)/990 episodes \(([0-9]+) levels\), died ([0-9]+), timed out ([0-9]+), mean score ([0-9]+), kills/episode ([0-9.]+)|$r $ck seed$seed: cleared \1 levels \2 died \3 timeout \4 kills \6|" >> runs/analysis/fixes-1018/heldout_round3.txt &
    done
  done
  wait
done
n=$(ls runs/analysis/fixes-1018/S*_{best,final}_seed{777,92731}.json 2>/dev/null | wc -l)
echo "held-out scoring done: $(date); $n of 32 per-level files present"
[[ $n -eq 32 ]] || { echo "validation incomplete; see runs/analysis/fixes-1018/eval_errors_round3.log"; exit 1; }
