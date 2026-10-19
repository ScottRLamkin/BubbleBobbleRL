#!/bin/zsh
# Round 4, as concurred at the 02:00 gate (CODEX-20261019T020200-0700): six
# arms, 60 min wall each on one core, standard test every 1M steps, best.pt
# kept; validation on 777/92731. Manifest: runs/analysis/fixes-1018/round4_manifest.md.
#  T1 S2 (G s103 lineage) +60 min, lr 1e-4                       seed 120 } seed-matched movement contrast
#  T2 S2 +60 min, lr 1e-4, stationary penalty 0.02               seed 120 }
#  T3 S3 (G s102 lineage) +60 min, lr 1e-4                       seed 121 } second independent lineage
#  T4 S3 +60 min, lr 1e-4, stationary penalty 0.02               seed 121 }
#  T6 D (kill/clear objective, state obs) seed 102                            } D replication, paired with G seeds 102/103
#  T7 D seed 103                                                              } to isolate the ego effect
# (T5 learning-rate decay and T8 deferred per the gate.)
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
run T6_D_s102             "${COMMON[@]}" "${D[@]}" --seed 102
run T7_D_s103             "${COMMON[@]}" "${D[@]}" --seed 103
fail=0
for i in {1..${#PIDS}}; do wait ${PIDS[$i]} || { echo "FAILED: ${NAMES[$i]} (see runs/${NAMES[$i]}.log)"; fail=1; }; done
echo "arms done: $(date) (failures: $fail)"
[[ $fail -eq 0 ]] || { echo "aborting before validation: a training arm failed"; exit 1; }
setopt pipefail
START_TS=$(date +%s); evalfail=0
: > runs/analysis/fixes-1018/heldout_round4.txt
EPIDS=(); EFILES=()
for r in T1_S2_cont T2_S2_cont_still02 T3_S3_cont T4_S3_cont_still02 T6_D_s102 T7_D_s103; do
  flags=(--control-obs --obs ego); [[ $r == T[67]* ]] && flags=(--control-obs)
  for ck in best final; do
    f=runs/$r/best.pt; [[ $ck == final ]] && f=runs/$r/model.pt
    for seed in 777 92731; do
      out=runs/analysis/fixes-1018/${r}_${ck}_seed${seed}.json
      ( uv run python scripts/evaluate.py $f --seed $seed "${flags[@]}" --per-level-out $out 2>> runs/analysis/fixes-1018/eval_errors_round4.log \
        | sed -E "s|^.*cleared ([0-9]+)/990 episodes \(([0-9]+) levels\), died ([0-9]+), timed out ([0-9]+), mean score ([0-9]+), kills/episode ([0-9.]+)|$r $ck seed$seed: cleared \1 levels \2 died \3 timeout \4 kills \6|" >> runs/analysis/fixes-1018/heldout_round4.txt ) &
      EPIDS+=($!); EFILES+=($out)
    done
  done
  # per-evaluation exit status, not a bare wait
  for i in {1..${#EPIDS}}; do wait ${EPIDS[$i]} || { echo "EVAL FAILED: ${EFILES[$i]}"; evalfail=$((evalfail+1)); }; done
  EPIDS=(); EFILES=()
done
# expected-artifact manifest: every file must exist, be newer than this validation's start, and hold 99 levels x 10 outcomes
missing=0
for r in T1_S2_cont T2_S2_cont_still02 T3_S3_cont T4_S3_cont_still02 T6_D_s102 T7_D_s103; do for ck in best final; do for seed in 777 92731; do
  f=runs/analysis/fixes-1018/${r}_${ck}_seed${seed}.json
  if [[ ! -s $f ]] || (( $(stat -f %m $f) < START_TS )) || ! uv run python -c "import json,sys; d=json.load(open('$f'))['per_level']; assert len(d)==99 and all(len(v)==10 for v in d.values())" 2>/dev/null; then
    echo "MISSING/STALE/MALFORMED: $f"; missing=$((missing+1)); fi
done; done; done
echo "held-out scoring done: $(date); $missing of 24 expected artifacts missing; $evalfail evaluator failures"
[[ $missing -eq 0 && $evalfail -eq 0 ]] || exit 1
