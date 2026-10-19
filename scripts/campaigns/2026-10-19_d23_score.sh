#!/bin/zsh
# D2.3 scoring: every numbered snapshot of both arms on three fresh diagnostic
# seeds (1009-1011), 990 episodes each; per-snapshot held-out clears to
# runs/analysis/diag-1019/d23_snapshots.txt and per-level JSON to
# runs/analysis/diag-1019/d23/. Per-evaluation exit checks.
# Training was stopped by the user at ~13M steps, so each arm has 12
# snapshots (1M..12M) instead of the pre-registered 15; 72 evaluations
# instead of 90. The snapshots were trained with the pre-RNG-fix code
# (revision cbb1b09); scoring runs post-fix.
set -e
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1
OUT=runs/analysis/diag-1019/d23_snapshots.txt; : > $OUT
mkdir -p runs/analysis/diag-1019/d23
fail=0
for arm in L_high L_low; do
  for ck in runs/D23_$arm/ckpt_*.pt; do
    PIDS=()
    for seed in 1009 1010 1011; do
      ( uv run python scripts/evaluate.py $ck --seed $seed --control-obs \
          --per-level-out runs/analysis/diag-1019/d23/${arm}_$(basename $ck .pt)_seed$seed.json 2>>runs/analysis/diag-1019/d23_eval_errors.log \
        | sed -E "s|^.*cleared ([0-9]+)/990 .*kills/episode ([0-9.]+)|$arm $(basename $ck .pt) seed$seed cleared \1 kills \2|" >> $OUT ) &
      PIDS+=($!)
    done
    for p in $PIDS; do wait $p || fail=$((fail+1)); done
  done
done
echo "D2.3 scoring done: $(date); evaluator failures: $fail; rows: $(wc -l < $OUT)"
[[ $fail -eq 0 ]] || exit 1
