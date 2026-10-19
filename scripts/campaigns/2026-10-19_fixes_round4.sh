#!/bin/zsh
# Round 4 (proposed at the 02:00 gate): confirm the movement-penalty effect on
# independent lineages, test learning-rate decay against checkpoint
# degradation, and replicate D to isolate the ego effect. 60 min, one core
# each, standard test every 1M steps, best.pt kept; validation on 777/92731.
#  T1 S2 (G s103 lineage) +60 min, lr 1e-4                       seed 120 } seed-matched pair
#  T2 S2 +60 min, lr 1e-4, stationary penalty 0.02               seed 120 }
#  T3 S3 (G s102 lineage) +60 min, lr 1e-4                       seed 121 } seed-matched pair
#  T4 S3 +60 min, lr 1e-4, stationary penalty 0.02               seed 121 }
#  T5 S2 +60 min, lr 1e-4 annealed to 0 (--anneal-lr)            seed 120   vs T1: decay against wandering
#  T6 D (kill/clear objective, state obs) seed 102                            } D replication
#  T7 D seed 103                                                              } to isolate ego (G - D)
#  T8 S7 +60 min, lr 5e-5, stationary 0.02                        seed 122   does the best lineage keep going at a lower rate
set -e
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
source scripts/campaigns/mlflow_env.sh
COMMON=(--levels 1-99 --time-penalty 0.01 --stationary-penalty 0.005 --stationary-window 120 --stationary-band 32
        --death-penalty 5 --timeout-penalty 4 --total-steps 800000000 --max-minutes 60
        --eval-every 1000000 --log-every 20 --no-tensorboard --quiet --experiment fixes-1018)
G=(--control-obs --max-episode-frames 3600 --no-score-reward --kill-bonus 2 --obs ego)
D=(--control-obs --max-episode-frames 3600 --no-score-reward --kill-bonus 2)
PIDS=(); NAMES=()
run() { local name=$1; shift; uv run python scripts/train_ppo.py "$@" --run-name $name > runs/$name.log 2>&1 & PIDS+=($!); NAMES+=($name); }

run T1_S2_cont            "${COMMON[@]}" "${G[@]}" --seed 120 --init-model runs/S2_G103_cont/best.pt --lr 1e-4
run T2_S2_cont_still02    "${COMMON[@]}" "${G[@]}" --seed 120 --init-model runs/S2_G103_cont/best.pt --lr 1e-4 --stationary-penalty 0.02
run T3_S3_cont            "${COMMON[@]}" "${G[@]}" --seed 121 --init-model runs/S3_G102_cont/best.pt --lr 1e-4
run T4_S3_cont_still02    "${COMMON[@]}" "${G[@]}" --seed 121 --init-model runs/S3_G102_cont/best.pt --lr 1e-4 --stationary-penalty 0.02
run T5_S2_cont_anneal     "${COMMON[@]}" "${G[@]}" --seed 120 --init-model runs/S2_G103_cont/best.pt --lr 1e-4 --anneal-lr --total-steps 30000000
run T6_D_s102             "${COMMON[@]}" "${D[@]}" --seed 102
run T7_D_s103             "${COMMON[@]}" "${D[@]}" --seed 103
run T8_S7_cont_lr5e-5     "${COMMON[@]}" "${G[@]}" --seed 122 --init-model runs/S7_R5_cont_still02/best.pt --lr 5e-5 --stationary-penalty 0.02
fail=0
for i in {1..${#PIDS}}; do wait ${PIDS[$i]} || { echo "FAILED: ${NAMES[$i]} (see runs/${NAMES[$i]}.log)"; fail=1; }; done
echo "arms done: $(date) (failures: $fail)"
[[ $fail -eq 0 ]] || { echo "aborting before validation: a training arm failed"; exit 1; }
setopt pipefail
for r in T1_S2_cont T2_S2_cont_still02 T3_S3_cont T4_S3_cont_still02 T5_S2_cont_anneal T6_D_s102 T7_D_s103 T8_S7_cont_lr5e-5; do
  flags=(--control-obs --obs ego); [[ $r == T[67]* ]] && flags=(--control-obs)
  for ck in best final; do
    f=runs/$r/best.pt; [[ $ck == final ]] && f=runs/$r/model.pt
    for seed in 777 92731; do
      uv run python scripts/evaluate.py $f --seed $seed "${flags[@]}" --per-level-out runs/analysis/fixes-1018/${r}_${ck}_seed${seed}.json 2>> runs/analysis/fixes-1018/eval_errors_round4.log \
        | sed -E "s|^.*cleared ([0-9]+)/990 episodes \(([0-9]+) levels\), died ([0-9]+), timed out ([0-9]+), mean score ([0-9]+), kills/episode ([0-9.]+)|$r $ck seed$seed: cleared \1 levels \2 died \3 timeout \4 kills \6|" >> runs/analysis/fixes-1018/heldout_round4.txt &
    done
  done
  wait
done
n=$(ls runs/analysis/fixes-1018/T*_best_seed777.json runs/analysis/fixes-1018/T*_best_seed92731.json runs/analysis/fixes-1018/T*_final_seed777.json runs/analysis/fixes-1018/T*_final_seed92731.json 2>/dev/null | wc -l)
echo "held-out scoring done: $(date); $n of 32 per-level files present"
[[ $n -eq 32 ]] || { echo "validation incomplete; see runs/analysis/fixes-1018/eval_errors_round4.log"; exit 1; }
