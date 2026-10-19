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
| 3 | Bubble contact: push only when 4+ px ahead of Bub's facing, with recoil; otherwise break at the next 4-frame tick | `game._bubble_player_interaction`, `_step_bubbles`, `_step_player` | Z80 `BubbleHitPlayer`, `PlayerFlags`, `DoBubbleFlags` | Behind/ahead/above/too-close cases; `test_bubble_contact_follows_bubblehitplayer`; captured-enemy cases `test_captured_enemy_bubble_contact_kills_or_pushes_by_facing` | Source discrepancy, shown in scripted cases; replacement in `4ecefb6`. Not verified end to end against the running original game, and not accepted by the user in play | **Not in snapshot.** The campaign's code is unchanged, but its results apply to the old rule; see the decision note | Fix prepared for later runs, not deployed |
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
| 14 | Rollout storage is aligned: done flags mark fake autoreset steps, rewards and observations line up | `train_ppo.train` rollout loop, `gae_with_autoreset` | Episode structure under NEXT_STEP autoreset (40-frame clock: 10 real steps, then one fake step) | `test_trainer_rollout_storage_is_aligned_end_to_end` captures what `train()` stores. A mutant that flags the terminal step itself fails it | Clean for the truncation case (40-frame clock, grace on, two rollouts) and the death case (`test_trainer_rollout_storage_is_aligned_for_death_terminations`: no grace, 100-step clock, at least one death ending; live trainer `2b2878a3eb59`). Not verified: bootstrap or level-pool terminal paths | Rollout path shared with the snapshot. The first passing run executed trainer `1be6902b7348`, byte-identical to the snapshot. The second run executed `2b2878a3eb59`, whose only diff is the explained-variance logging (`50660c7`). env.py identical. Both runs used the live game.py, whose contact rule differs; the test's assertions concern storage, not game outcomes. Correction: an earlier version claimed whole-file identity after `50660c7`, which was false | — |
| 15 | Fake transitions are masked out of every loss and statistic | `train_ppo` update | Only real steps carry signal | Read: policy, value and entropy losses, advantage normalization, KL and clip fraction use real indices. Explained variance used every step | Logging defect only | Logging only; campaign logs nothing | Fixed in the live repo `50660c7` with a hand-computed test; not deployed |
| 16 | A truncation bootstrap uses the episode's final observation | `train_ppo` (`--bootstrap-truncation`) | Gymnasium 1.x NEXT_STEP returns the final observation at truncation | Read: `V(final obs)` is added to that step's reward, and the step is then terminal | Clean by reading; not tested | Not used by the campaign | — |
| 17 | The ratio uses the log-probability of the action actually taken | `Agent.action_value`, update | PPO definition | Read: action and log-probability come from one call and are stored together; flattening order is shared | Clean by reading | In snapshot | — |
| 18 | The manifest's reward and control settings reach every training env | `train_ppo.make_env` (23 positional arguments) | Manifest `fixed_parameters` | `test_manifest_reward_switches_reach_every_training_env` intercepts the 16 envs `train()` builds | Clean | In snapshot | — |
| 19 | Reward components have their intended size | `env.step` | Manifest values | `test_manifest_reward_components_have_their_intended_size`: time plus timeout on a one-step clock, death on contact, no score reward. Kill, capture and clear sizes not exercised by a scripted transition | Clean for the cases tested | In snapshot | — |
| 20 | Training and evaluation share control and horizon conventions | `train_ppo`, `evaluate.evaluate` | One task definition | `test_training_and_evaluation_envs_share_control_and_horizon` | Clean | In snapshot | — |
| 21 | Hidden state that changes what an action does is observable | `env._obs` | Training review: expose hidden button and jump state | Read: the player features include facing, jump mode and the shot cooldown (`shoot_cooldown / 14`); control state adds the previous jump and shoot buttons, the jump counter and time left. Still hidden: the one-frame pending-death flag (both versions); in the live contact implementation only, the pending recoil and pending break flags, which do not exist in the snapshot | Clean. Correction: an earlier version of this row said the cooldown was unobservable, which was wrong | In snapshot | — |
| 22 | Collision boxes: capture 7 px, contact death 5 px, death applied next frame | `game._enemy_hazards`, `_touch_player`, `_step_player` | Z80 `MonsterHitPrebubble` → `CheckHitTarget` (7), `MonsterHitPlayer` → `CheckHitBub4` (5), death flag consumed in `PlayerFlags2` | Read side by side | Clean | In snapshot | — |
| 23 | Jump starts need a fresh press; a bubble bounce needs jump held | `game._player_gravity`, `_fall` | Z80 `NoGrav`/`JumpTest`, `DownGrav` | Read side by side | Clean | In snapshot | — |
| 24 | A clear is completed 256 frames after the last kill | `game._enemy_died`, `clear_countdown` | Z80 `NoMoreEnemies` resets the 16-bit timer; `CheckEnd` advances when its high byte reaches 1 | Read side by side; countdown tests already exist | Clean. Minor deviation: the port explodes leftover empty bubbles at the last kill, where the original leaves them or turns them into fruit, which affects score only | In snapshot | — |
| 25 | Evaluation episodes are seeded distinctly, and the tuning and final banks cannot overlap | `evaluate._evaluate` | Seed = bank x 100,003 + level x 101 + episode | Arithmetic: the level and episode terms are at most 9,907, below 100,003, so no two (bank, level, episode) triples share a seed | Clean | In snapshot | — |
| 26 | The ego window reads off-screen columns as wall and wraps rows | `env._local_window` | Docstring and the encoding comment: 0 = wall | Read: the window starts at zeros, off-screen columns stay 0 (wall), and rows wrap modulo the grid | Clean | In snapshot | — |
| 27 | Floating bubbles push each other apart | `game._step_bubbles` | Z80 `BubbleHitBubble`: within 7 px in both axes and at least 4 px apart on an axis, flag a one-pixel move apart on it; `DoBubbleFlags` applies it next tick | `test_overlapping_bubbles_drift_apart_and_stacked_ones_stay`: 5 px apart becomes 7, 2 px apart stays stacked | Mechanic missing from the port, and not listed among its omissions | **Not in snapshot** | Fixed in the live repo `e717d9b`; not deployed |
| 28 | Horizontal bubble moves probe the right tile | `game._step_bubbles` | Z80 `_MoveRight`/`_MoveLeft`: x+8 / x-1 at y+7 | Read: the port probed y+4 | Deviation | **Not in snapshot** | Fixed with row 27 |
| 29 | A timed-out bubble pops at the next tick | `game._step_bubbles` | Z80 `HandleBubble`: counter at 0 sets bits 5 and 7; `DoBubbleFlags` pops next tick | `test_timed_out_bubble_pops_at_the_next_tick` | Deviation of one tick (4 frames) | **Not in snapshot** | Fixed with row 27 |
| 30 | Bubbles float with the air current of their centre tile | `game._float_bubble` | Z80 `MoveBubble` → `GetAir` (tile at x+4, y+4): 2 left, 3 right, 4 down, otherwise up | Read side by side | Clean | In snapshot | — |
| 31 | A shot flies 26 px before it becomes a bubble | `game._step_prebubbles` | Z80 `PrebubbleCounter`: on the 27th frame the sprite becomes a Bubble and the handler returns before the move | `test_a_shot_flies_26_pixels_before_it_becomes_a_bubble`; `test_game` had pinned the port's 27 px and is updated | Deviation of one pixel. Capture timing was already right | **Not in snapshot** | Fixed in the live repo `2ee51f7`; not deployed |
| 32 | Enemies drop in and activate on the original's schedule | `game._step_falling_in`, enemy spawns | Z80 `HandleFallingEnemy`: first call sets the counter to -y; then down 1 px on even frames and the counter decrements every 4th frame; activate at 0 | Read side by side. The port presets the counter (y_pix). The original's initialising call falls on timer 1, an odd frame where neither version acts, because both reset the timer to 0 at level start | Clean | In snapshot | — |
| 33 | Explosions chain over the original's box; a killed enemy flies the way Bub faced at the break | `game._start_break`, `_step_breaking` | Z80 `CheckExplosionHitBubble`: other - this in [-10, 9] on both axes, raw y; `ExplodeBubble` stores the player's facing at the break | `test_explosion_chain_box_is_minus_10_to_plus_9` (one neighbour at a time) | Deviation at the +10 edge and with vertical wrapping; facing read 16 frames late (affects only where fruit lands) | **Not in snapshot** | Fixed in the live repo; not deployed |
| 34 | Walkers: after a hop or fall decision, the shoot test and jump check still run | `game._buster_walk` | Z80 `BustWalk`, `StonerWalk`, `HidegonsuWalk`: `DumbWalk`/`SmartWalk` then `StonerShoot1`/`StandardJumpCode`; the jump search stops below y 0 | `test_walker_jump_check_can_override_a_hop` on a synthetic ledge; campaign revision keeps the hop | Deviation (the port returned early) | **Not in snapshot** | Fixed in the live repo; not deployed |
| 35 | Shooters fire when the player is in the original's vertical band | `game._shooter_aim` | Z80 `TestHAligned`: e.y - p.y + 15 in [0, 32), the player 16 px above to 15 px below | `test_shooter_alignment_band_is_16_above_to_15_below`; campaign revision has the band mirrored | Deviation of one pixel at each edge | **Not in snapshot** | Fixed in the live repo; not deployed |
| 36 | Walker look-around, hop phases, jump-up and the standing test | `game._look_around`, `_buster_ai`, `standing` | Z80 `BustLookAround`, `BustJump*`, `BustJumpUp`, `CheckBelow` | Read side by side | Clean | In snapshot | — |
| 37 | Shooter aim and shot timing | `SHOOTER_TIMING`, `game._shooter_shoot` | Z80 `StonerShoot1`/`StonerShoot` (aim 11, 16-frame shot, fires at 8), `HidegonsuShoot1`/`HidegonsuShoot` (17, 8, 4) | Read side by side | Clean | In snapshot | — |

## Decision note: the bubble-contact mismatch and what the campaign can answer

**Which outcomes differ.** The same scripted contacts, with an enemy captured
inside the bubble, run against the frozen snapshot's game and against the
corrected game (`contact_compare.py` in the session scratchpad; under one
second of compute):

| Contact, Bub on the floor, bubble 5 px away | Snapshot `42ed83d` (campaign) | Corrected `4ecefb6` |
|---|---|---|
| Behind Bub, same level | pushed along, no kill | explodes, enemy killed |
| Ahead of Bub, same level | pushed along, no recoil | pushed one pixel, Bub recoils |
| Ahead of and above Bub | explodes, enemy killed | pushed, Bub recoils, no kill |
| Behind and above Bub | explodes, enemy killed | explodes, enemy killed |
| Within 4 px horizontally, facing it | explodes, enemy killed | explodes, enemy killed |
| Bub on top of the bubble | ridden (bounce) | ridden (bounce) |

Smaller differences: the corrected game explodes a bubble up to three frames
later (at the next 4-frame tick), and a bubble whose death counter reads 0 is
not pushed on that tick. Rows 27-29, found later, add three more bubble
mechanics the snapshot lacks: bubbles pushing each other apart, the wall probe
row for horizontal bubble moves, and the one-tick delay of a timed-out pop.
They also change where captured enemies float and which explosions chain, so
the applicability limit above covers them too. Kill and pop scoring and explosion chains are
unchanged. The original four regression cases used empty bubbles; the
captured-enemy cases above are now covered by a regression test.

**What the current protocol can still answer.** Every arm, the anchors
included, trains and is evaluated on the snapshot's rule, so the comparison
between configurations is internally consistent, and the screen, confirmation
and final-bank verdicts are valid statements about that game. They do not
establish that the selected configuration is better, or the acceptance verdict
the same, on the corrected game: the rule changes which contacts kill, so
which policies benefit may change. Transferring the result needs a
corrected-game confirmation (fresh training of the winner and anchor_G on the
corrected game with fresh seeds). That is new training and is not authorized;
it is a question for the user after this campaign. The final report must name
snapshot `42ed83d` and this known mechanic defect prominently.

## Playing the two game versions side by side

Two read-only copies of the game source are extracted under `runs/play/`, so
playing either one never touches the working tree or the campaign snapshot.
Run from the repo root:

| Revision | What it is | Command |
|---|---|---|
| `42ed83d` | The campaign's game: falling fix (row 2) only | `PYTHONPATH=runs/play/42ed83d/src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m bubblebobblerl.play --level 1` |
| `2ee51f7` | Adds contact rule and recoil (row 3), bubble flag byte with separation, probe row and deferred pop (rows 27-29), and 26 px shots (row 31) | `PYTHONPATH=runs/play/2ee51f7/src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m bubblebobblerl.play --level 1` |

`uv run bubblebobblerl-play` plays whatever the working tree holds, which
changes as fixes land.

## Failure response for the live runner

This is supervision, not prevention: the runner itself does not stop on a
systemic failure, and between a FAILED line and a human-run kill it may
dispatch more jobs.


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
| Pre-launch dry run, including interrupted attempts | about 508 | Mixed: 447.5 measured for completed attempts and 5.4 for the dry preflight; about 55 estimated for the interrupted attempts from their loop times plus startup |
| Validator and runner overhead, production | about 77 forecast (2.2 per training job x 35) | Measured 6.5 s over the first three production jobs; outside reservations, so added here. Forecast, not a 60 s worst-case reservation |
| This audit's test execution | about 51 of 120 | pytest during the bubble fix (about 12), auditor tests 1.8, dry-run audit 0.8, rollout test 2.3, mutant 1.2, explained variance 1.8, reward and convention tests 2.2, plus reruns |
| Total | about 64,322 of 64,800 (about 478 s reserve) | Reservations + preflight + dry run + forecast overhead + this audit |
