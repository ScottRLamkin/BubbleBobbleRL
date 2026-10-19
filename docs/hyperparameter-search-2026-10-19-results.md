# Hyperparameter search results — October 19, 2026

Campaign `hparam-1019-v1`, run to the frozen protocol in
[the design](hyperparameter-search-2026-10-19.md) (Codex) by
`scripts/run_hyperparameter_search.py`, 09:49–12:39 PDT. All artifacts are under
`runs/hparam-1019/`. The independent auditor (`scripts/audit_hparam_campaign.py`)
re-checked every file and recomputed every decision, and found no problems.

## Verdict

Configuration **ff12** passed the protocol's acceptance rule against anchor_G (recipe G). It is
the new engineering baseline for the game version the campaign ran (see
[Applicability](#applicability)).

Final bank: fresh seeds 61001 and 61002, opened only after the winner and six checkpoint hashes
were frozen. Clears are level completions per 990 episodes, averaged over the two seeds.

| Training seed | ff12 | anchor_G | Paired gain |
|---|---|---|---|
| 4201 | 354.5 | 129.5 | +225.0 |
| 4202 | 285.0 | 164.5 | +120.5 |
| 4203 | 325.5 | 142.0 | +183.5 |
| **Mean** | **321.7** | **145.3** | **+176.3** (range +120.5 to +225.0) |

The rule required a mean gain of at least 30 and no negative pair. It is an operational
acceptance rule, not a calibrated significance test.

How the two recipes' policies differ on the final bank. Each value is a training seed's mean over
the two final seeds, per 990 episodes; ranges run over the three training seeds. (Correction: an
earlier version labelled these as two-seed means but showed the extremes of the six individual
evaluations.)

| | ff12 (3 policies) | anchor_G (3 policies) |
|---|---|---|
| Clears | 285.0–354.5 | 129.5–164.5 |
| Deaths | 620.0–691.0 | 489.0–552.0 |
| Timeouts | 14.0–25.0 | 296.0–336.5 |
| Kills per episode | 2.88–3.36 | 2.18–2.29 |
| Levels cleared at least once (of 99) | 58.5–63.5 | 27.5–33.5 |

ff12's policies almost never run out the clock: an episode ends in a clear or a death. This is
observed behaviour on this game version, not a demonstration of navigation competence.

## The winning configuration

ff12 is a corner of the fractional factorial: learning rate 1e-3, entropy coefficient 3e-4,
discount 0.9990 (a 1,024-step horizon), rollouts of 512 steps across 16 environments (8,192
samples per update), 2 epochs, clip 0.1. In one hour it made about 4,800 updates against recipe
G's 16,400, on about 39 million steps against 33.6 million. Every other hyperparameter is
recipe G's. The complete experiment is
[`configs/hparam-1019_ff12_confirm.json`](../configs/hparam-1019_ff12_confirm.json), identical
to the recorded configuration of the seed-4201 confirmation run.

## How it was chosen

- **Screen**: 26 configurations, 15 minutes each, training seed 4100, tuning seeds 51001 and
  51002. Ranked by mean clears, then kills. Top two after anchor_G: ff12 (200.0) and interior06
  (160.5); anchor_G scored 82.0. The full table, with steps, updates and every outcome count, is
  in `runs/hparam-1019/audit.md`; per-level outcomes are in `runs/hparam-1019/per_level.csv`.
- **Confirmation**: one hour each, training seeds 4201–4203, tuning seeds. ff12 averaged 314.7
  and interior06 260.3, so ff12 won. anchor_G's own confirmation runs averaged 138.8 on the same
  seeds.
- **Exploratory factorial contrasts** (16 screen corners; mean clears at the high level minus
  the low level). The design is resolution IV, so each main effect is aliased with three-factor
  interactions. The contrasts come from one training seed at 15 minutes: they are not causal
  estimates and not recommendations.

| Factor | Low | High | Contrast |
|---|---|---|---|
| lr | 1e-5 | 1e-3 | +21.9 |
| ent_coef | 3e-4 | 0.05 | −53.8 |
| discount horizon | 32 | 1,024 | +0.8 |
| rollout length | 64 | 512 | +18.9 |
| epochs | 2 | 8 | −11.2 |
| clip | 0.1 | 0.3 | −12.7 |

## Cost

| Item | Core-hours |
|---|---|
| Reserved and charged before dispatch (47 jobs, plus preflight) | 17.70 |
| Measured job time (training, evaluation, validation) | 16.01 |
| Pre-launch dry run (mostly measured; interrupted attempts estimated) | about 0.14 |
| Cap | 18 |

Wall time was 2 h 50 min on six single-thread jobs (local Apple M4 Pro). No job failed and none
was refused for budget or cutoff.

## Applicability

1. **Game version.** The campaign ran snapshot `42ed83d`. Fidelity fixes made later the same
   day are not in it:
   - the bubble-contact rule;
   - bubble-to-bubble separation, push probe and deferred pop;
   - 26-pixel shots;
   - the explosion box;
   - walker turn order;
   - the shooter band;
   - Invader order;
   - Banebou landing;
   - Hullaballoon probes;
   - the stone break;
   - the beer bounce;
   - and above all the **hurry-up and the baron**, which in the original put time pressure inside
     every episode on every level.

   See `docs/search-correctness-audit-2026-10-19.md`. Every arm saw the same old game, so the
   comparison is internally consistent. Whether ff12 beats recipe G on the corrected game, with
   the baron chasing the player, is not established; that needs new training on the current game.
2. **Screen design.** The screen used one training seed and 15 minutes, which can favour fast
   learners; the 26 points cover the stated bounds sparsely. ff12 sits at a corner of the bounds,
   so better settings may lie outside them. Failing to beat a configuration here is not evidence
   that the configuration is bad in general.
3. **Implicit hyperparameters.** The manifest did not state 17 hyperparameters, which took the
   trainer's built-in values then: Adam epsilon and betas, gradient clip, advantage normalisation,
   init gains, score scale, exploration band, hard-sampling settings, grace, max_minutes,
   eval_episodes and fresh_optimizer. Their values are recorded in every run's `config.json` and
   in the configuration files above. Since today the trainer has no defaults (see
   [the hyperparameter census](hyperparameters.md)).
4. **Seed provenance.** Evaluation files do not record their seed; it rests on the runner's file
   names.
5. **Supervision.** A systemic failure would not have stopped the runner automatically; the
   procedure was supervision by hand, and no failure occurred.
