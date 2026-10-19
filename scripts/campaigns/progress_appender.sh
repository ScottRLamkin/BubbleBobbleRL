#!/bin/zsh
# Appends an automated status entry to the Fable-Codex progress log every 30
# minutes while the given runs exist: latest standard-test line per run and
# best so far. Usage: progress_appender.sh <log> <run-name>...
LOG=$1; shift
cd "$(dirname "$0")/../.."
while true; do
  sleep 1800
  {
    echo
    echo "### FABLE-$(date +%Y%m%dT%H%M%S%z) | $(date '+%Y-%m-%d %H:%M:%S %Z') | Fable (automated status)"
    echo "Checkout / revision: $(pwd) @ $(git rev-parse --short HEAD)"
    echo "Runs (latest periodic test on the run's own level pool x 10 episodes, seed 4242; denominators shown; best.pt = best such test so far; selection scores, not held-out):"
    alive=0
    for r in "$@"; do
      last=$(grep 'eval @' runs/$r.log 2>/dev/null | tail -1 | sed -E 's/ +eval @ +([0-9]+): cleared ([0-9]+\/[0-9]+) .*levels cleared ([0-9]+\/[0-9]+).*/step \1: \2, \3 levels/')
      denom=$(grep 'eval @' runs/$r.log 2>/dev/null | tail -1 | awk '{print $5}' | sed 's|^[0-9]*/||')
      best=$(grep 'eval @' runs/$r.log 2>/dev/null | awk '{print $5}' | sed 's|/[0-9]*||' | sort -n | tail -1)
      best="${best:-?}/${denom:-?}"
      line=$(grep '^step' runs/$r.log 2>/dev/null | tail -1 | sed -E 's/ +sps.*//')
      echo "- $r: ${last:-no evaluation yet}; best $best; train: ${line:-starting}"
      pgrep -f "run-name $r" > /dev/null && alive=$((alive+1))
    done
    echo "Processes alive: $alive of $#. Memory watchdog: $(tail -1 runs/memwatch.log 2>/dev/null || echo quiet)."
    echo "Verdict: automated status; see the next manual entry for interpretation."
  } >> "$LOG"
  [[ $alive -eq 0 ]] && exit 0
done
