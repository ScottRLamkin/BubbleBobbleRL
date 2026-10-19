# Search correctness audit — October 19, 2026

Low-compute audit run alongside campaign `hparam-1019-v1`
([protocol](hyperparameter-search-2026-10-19.md)), requested by the user through
Codex (CODEX-20261019T095352-0700). The campaign runs a frozen snapshot of commit
`42ed83d`; nothing here changes it. "Snapshot" says whether a finding applies to
the code the campaign is running.

Test-execution budget for this audit: 120 single-thread seconds, inside the
campaign's 18 core-hour cap. Spent so far: see the ledger at the end.

## Findings

| # | Invariant | Code | Expected behaviour (independent source) | Reproduction / test | Result | Snapshot | Disposition |
|---|---|---|---|---|---|---|---|
| 1 | A checkpoint runs only on the observation it was trained on | `train_ppo.Agent.load`, every caller | Network input = trained observation | X7 (ego) evaluated as state ran silently, 0/20 vs 10/20; `test_checkpoint_refuses_a_different_observation` | Defect, fixed `0046fb4` | In snapshot | Preflight re-checked refusal |
| 2 | A falling player moves sideways on odd frames only | `game._step_player` | Z80 `HandlePlayer2` → `PlayerMoveCounter` (bub_ai.z80) | 8 falling frames gave 8 px, original 4; `test_falling_player_walks_on_odd_frames_only` | Defect, fixed `11a9ae5` | In snapshot | Ran in frozen preflight |
| 3 | Bubble contact: push only when 4+ px ahead of Bub's facing, with recoil; otherwise break at the next 4-frame tick | `game._bubble_player_interaction`, `_step_bubbles`, `_step_player` | Z80 `BubbleHitPlayer`, `PlayerFlags`, `DoBubbleFlags` | Behind/ahead/above/too-close cases; `test_bubble_contact_follows_bubblehitplayer` | Defect, fixed `4ecefb6` | **Not in snapshot** (campaign uses the old rule, identically in every arm) | Fix prepared for later runs, not deployed |
| 4 | Bubble creation respects the original's sprite limit | `game._blow_bubbles` | Z80 `CreateSprite` fails when 63 slots are used | Peak concurrent sprites in sampled play: 25 and 46 (two policies, 15 levels) | Deviation exists, did not bind in the sample | In snapshot | Left alone; recorded |
| 5 | Clock expiry is a truncation, with no second time limit | `env.step`, registration, `make_env` | Gymnasium termination vs truncation | Read: expiry sets `truncated`; no `TimeLimit` wrapper | Clean | In snapshot | — |
| 6 | Runner accounts for all job compute | `run_hyperparameter_search.py` | Manifest: reservations include everything | Codex: the model validator runs outside reservations. Dry-run audit: 77 s of non-train, non-eval time over 47 jobs (about 2 s per training job) | Gap confirmed; small | In snapshot | Ledger adds measured overhead; runner not changed |
| 7 | Evaluation artifacts verified exactly | runner `check_eval` | 99 exact level keys; every outcome total reconciled | Codex: keys and death/timeout totals unchecked. New `scripts/audit_hparam_campaign.py`; `tests/test_audit_hparam.py` injects a wrong level key and an inconsistent death count | Runner gap; auditor catches both | Auditor is live-repo, read-only | Run auditor at each phase |
| 8 | Final-bank checkpoints unchanged through evaluation | runner final jobs | Hash before and after | Runner checks before only. Auditor re-hashes frozen checkpoints and rejects final files older than `frozen.json`; tested with a tampered model and a backdated file | Runner gap; auditor covers it | Auditor | Run auditor after the final bank |
| 9 | Selection, eligibility and winner follow the manifest | runner `advance_phases` | Manifest ranking rules | Auditor recomputes them; tested with an incomplete confirmation (candidate ineligible, recorded winner flagged) and duplicate records | Matches on the dry run (0 problems) | Auditor | Run auditor at each phase |
| 10 | Seed banks are separated | runner job table | Manifest seed banks | Auditor checks training seeds, tuning/final evaluation seeds and leaked final-seed files; tested with a leaked `eval_61001.json` | Clean on the dry run | Auditor | — |
| 11 | Evaluation seed provenance | `evaluate.py` output | A result should name its seed and model | The JSON records neither; provenance rests on the runner's file name `eval_<seed>.json` | Limitation | In snapshot | Recorded; not fixable without changing frozen code |
| 12 | A systemic failure stops the campaign | runner `execute` | Manifest: fail closed on systemic errors | Every exception becomes one failed job; selection proceeds from the survivors | Gap | In snapshot | Manual procedure below |
| 13 | Restart never duplicates a job | runner restart | One process per job | Dry run: lock and live-child refusal work. Codex: the validator's child PID is not published, so one transition is unguarded | Gap in one transition | In snapshot | Do not restart; procedure below |

## Failure response for the live runner

The monitor in Fable's session streams every `done`, `FAILED`, `not run`,
selection, freeze and final line from `runs/hparam-1019/events.log`, and fires
if runner PID 33901 exits.

1. **Classify each FAILED line.** It is *numerical* if it is a nonfinite update
   (`FloatingPointError`) at one configuration. It is *systemic* if it is a
   schema failure, a hash mismatch, an import or file error, a hard timeout of
   an evaluation, or the same error at two or more different configurations.
2. **Numerical:** leave the campaign running; the job stays failed and is
   excluded from ranking, as the manifest requires. Report it in the log.
3. **Systemic:** kill the runner (`kill 33901`) so nothing new is dispatched.
   Let running jobs finish unless they are themselves invalid. Do not edit
   `status.json`. Run the auditor. Post the exact affected jobs to the log and
   to the user, and ask for direction before any restart or replacement.
4. **Runner exits unexpectedly:** before any restart, list children with
   `pgrep -fl runs/hparam-1019/snapshot`. A restart is refused while a recorded
   job PID lives, but the validator's PID is not recorded, so check by hand.
   Interrupted attempts keep their reservations in the ledger.
5. **Auditor runs** after the screen, after confirmation, and after the final
   bank (`uv run python scripts/audit_hparam_campaign.py runs/hparam-1019 --write`).
   It never opens a final-bank file before `frozen.json` exists.

## Ledger (single-thread seconds)

| Item | Seconds | Basis |
|---|---|---|
| Campaign reservations, 47 jobs | 63,705 | Charged before dispatch |
| Real preflight | 5.4 | Measured |
| Pre-launch dry run, including interrupted attempts | about 508 | Measured, interrupted attempts from their loop times plus startup |
| Validator and runner overhead | about 2 per training job (77 in the dry run) | Measured on the dry run; to be replaced by the real figure |
| This audit's test execution | about 15 of 120 | pytest during the bubble fix (about 12), auditor tests 1.8, dry-run audit 0.8 |
| Total | about 64,234 of 64,800 | |
