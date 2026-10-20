# Hyperparameter search card — October 20, 2026

**Status: user-authorized for implementation/execution through 20:00; see the exact [daytime protocol](daytime-search-2026-10-20.md). Registration and launch remain pending.** Current values below were read from SQLite run `run-8c860496ea1531e0`, revision `rev-8d049ce428f6940c`. The current run has two layers; the user-directed next-run architecture has four. Historical and running configurations are preserved.

## Decisions and method

- **User-locked:** MLP 512 units × 4 hidden layers; game `2aa2548-baron-timer`, source hash `67eaeefeb54af78652aa90ca7fe41046c987a69b5604512411b984cc786107af`. Changing either requires the user. Activation and initialization are not locked.
- **Search this block:** learning rate, entropy coefficient, PPO clip and epochs. Bounds are proposed engineering ranges, not proven optimal bounds.
- **Temporary control:** every other parameter keeps its explicitly listed value for this comparison only. It remains eligible; no claim that it is optimal or irrelevant.
- **Replicate:** seeds are experimental repeats, not values to optimize.
- **Method:** 12 configurations: the inherited recipe rebuilt as 512×4, plus 11 predeclared space-filling configurations. Stratify LR and entropy logarithmically, clip linearly, and balance the discrete epoch choices. Three fresh matched training seeds for every configuration, identical predeclared development banks, full 60-minute endpoints. Freeze all rows before the first batch; no pruning or early stopping based on performance. This is joint exploration, not identification of isolated causal effects.
- **Cost:** 36 training core-hours in three batches of 12 jobs; each batch capped at 15 allocated single-thread core-hours including preflight/evaluation/retries/reporting (45 total). At most six concurrent single-thread jobs. Freeze one selected configuration then compare it with the 512×4 reference on three NEW matched training seeds and unopened evaluation banks, capped at eight further core-hours (53 total planning ceiling). Reserve actual evaluation allowances before dispatch.
- **Selection:** absolute level-clear fraction on the declared development bank, all seed-level totals and per-level failures visible. No discarded failed seeds or performance retries. Fresh confirmation reports absolute outcomes; the old +30 replacement threshold is not a competence target.
- **Time:** the user has extended execution through 20:00 today; the daytime protocol supersedes the earlier 08:00 cutoff.
- **Simplification rationale:** first examine optimization on the newly fixed network, while preserving the task/reward/observation definition. Next blocks can test credit assignment (gamma, lambda, rollout), reward weights/gates, and exposure. Their priority should follow observed failures and trajectories. No permanent lock is implied.
- **Dependencies:** frame skip changes the time units of discount and episode caps; batch size is num_envs × rollout_len and minibatches must divide it. Score/pop gates and other conditional rewards retain inactive values. Screen observations currently select a different encoder, so they require compatibility work or user approval if they would replace the locked MLP. Bootstrap mode must agree with the declared finite-horizon or continuing task, not be toggled without changing that definition. LR/curriculum/grace schedules currently use total_steps; a duration-based schedule needs explicit implementation before testing under a wall-time budget.

## Complete run-parameter inventory

“Not searched” means temporary control in this block, not fixed by the user. Proposed ranges for later blocks remain unset rather than pretending they have been designed.

| SQLite parameter | Type | Current stored value | Next-block status/value or range | Method / reason |
|---|---|---|---|---|
| `exposure.levels` | discrete categorical | `"1-99"` | temporary_control: "1-99" | Hold exposure/task constant in optimization block; design exposure/credit-assignment block separately. |
| `exposure.level_sampling` | discrete categorical | `"uniform"` | temporary_control: "uniform" | Hold exposure/task constant in optimization block; design exposure/credit-assignment block separately. |
| `exposure.hard_sampling_weight` | continuous | `9.0` | temporary_control: 9.0 | Hold exposure/task constant in optimization block; design exposure/credit-assignment block separately. |
| `exposure.hard_sampling_window` | discrete integer | `20` | temporary_control: 20 | Hold exposure/task constant in optimization block; design exposure/credit-assignment block separately. |
| `exposure.curriculum` | continuous | `0.0` | temporary_control: 0.0 | Hold exposure/task constant in optimization block; design exposure/credit-assignment block separately. |
| `task.max_episode_frames` | discrete integer | `3600` | temporary_control: 3600 | Hold exposure/task constant in optimization block; design exposure/credit-assignment block separately. |
| `task.frame_skip` | discrete integer | `4` | temporary_control: 4 | Hold exposure/task constant in optimization block; design exposure/credit-assignment block separately. |
| `task.lives` | discrete integer | `1` | temporary_control: 1 | Hold exposure/task constant in optimization block; design exposure/credit-assignment block separately. |
| `exposure.random_start` | discrete categorical | `false` | temporary_control: false | Hold exposure/task constant in optimization block; design exposure/credit-assignment block separately. |
| `exposure.grace_frames` | discrete integer | `0` | temporary_control: 0 | Hold exposure/task constant in optimization block; design exposure/credit-assignment block separately. |
| `exposure.grace_anneal` | continuous | `0.0` | temporary_control: 0.0 | Hold exposure/task constant in optimization block; design exposure/credit-assignment block separately. |
| `reward.score_reward` | discrete categorical | `false` | temporary_control: false | Hold all components and gates at inherited values to isolate optimization; reward block remains eligible. |
| `reward.score_scale` | continuous | `0.01` | temporary_control: 0.01 | Hold all components and gates at inherited values to isolate optimization; reward block remains eligible. |
| `reward.pop_reward` | discrete categorical | `true` | temporary_control: true | Hold all components and gates at inherited values to isolate optimization; reward block remains eligible. |
| `reward.clear_bonus` | continuous | `10.0` | temporary_control: 10.0 | Hold all components and gates at inherited values to isolate optimization; reward block remains eligible. |
| `reward.kill_bonus` | continuous | `2.0` | temporary_control: 2.0 | Hold all components and gates at inherited values to isolate optimization; reward block remains eligible. |
| `reward.capture_bonus` | continuous | `0.1` | temporary_control: 0.1 | Hold all components and gates at inherited values to isolate optimization; reward block remains eligible. |
| `reward.death_penalty` | continuous | `5.0` | temporary_control: 5.0 | Hold all components and gates at inherited values to isolate optimization; reward block remains eligible. |
| `reward.timeout_penalty` | continuous | `4.0` | temporary_control: 4.0 | Hold all components and gates at inherited values to isolate optimization; reward block remains eligible. |
| `reward.time_penalty` | continuous | `0.01` | temporary_control: 0.01 | Hold all components and gates at inherited values to isolate optimization; reward block remains eligible. |
| `reward.stationary_penalty` | continuous | `0.005` | temporary_control: 0.005 | Hold all components and gates at inherited values to isolate optimization; reward block remains eligible. |
| `reward.stationary_window` | discrete integer | `120` | temporary_control: 120 | Hold all components and gates at inherited values to isolate optimization; reward block remains eligible. |
| `reward.stationary_band` | discrete integer | `32` | temporary_control: 32 | Hold all components and gates at inherited values to isolate optimization; reward block remains eligible. |
| `reward.explore_bonus` | continuous | `0.0` | temporary_control: 0.0 | Hold all components and gates at inherited values to isolate optimization; reward block remains eligible. |
| `reward.explore_band` | discrete integer | `8` | temporary_control: 8 | Hold all components and gates at inherited values to isolate optimization; reward block remains eligible. |
| `observation.type` | discrete categorical | `"ego"` | temporary_control: "ego" | Hold encoding constant in optimization block; observation alternatives remain eligible within the locked MLP. |
| `observation.control_state` | discrete categorical | `true` | temporary_control: true | Hold encoding constant in optimization block; observation alternatives remain eligible within the locked MLP. |
| `observation.nearest_first` | discrete categorical | `false` | temporary_control: false | Hold encoding constant in optimization block; observation alternatives remain eligible within the locked MLP. |
| `return.gamma` | continuous | `0.9990234375` | temporary_control: 0.9990234375 | Hold credit assignment constant in optimization block; joint gamma/lambda/rollout block remains eligible. |
| `return.gae_lambda` | continuous | `0.95` | temporary_control: 0.95 | Hold credit assignment constant in optimization block; joint gamma/lambda/rollout block remains eligible. |
| `return.bootstrap_truncation` | discrete categorical | `false` | temporary_control: false | Hold credit assignment constant in optimization block; joint gamma/lambda/rollout block remains eligible. |
| `ppo.num_envs` | discrete integer | `16` | temporary_control: 16 | Hold other update/numerical controls to limit this block to four factors; eligible in later blocks. |
| `ppo.rollout_len` | discrete integer | `512` | temporary_control: 512 | Hold other update/numerical controls to limit this block to four factors; eligible in later blocks. |
| `ppo.epochs` | discrete integer | `2` | search_this_block: {2, 4, 8} | balanced discrete allocation |
| `ppo.minibatches` | discrete integer | `4` | temporary_control: 4 | Hold other update/numerical controls to limit this block to four factors; eligible in later blocks. |
| `ppo.clip` | continuous | `0.1` | search_this_block: 0.1–0.3 | linear scale |
| `ppo.ent_coef` | continuous | `0.0003000000000000001` | search_this_block: 0.0001–0.03 | log scale |
| `ppo.vf_coef` | continuous | `0.5` | temporary_control: 0.5 | Hold other update/numerical controls to limit this block to four factors; eligible in later blocks. |
| `ppo.norm_adv` | discrete categorical | `true` | temporary_control: true | Hold other update/numerical controls to limit this block to four factors; eligible in later blocks. |
| `ppo.max_grad_norm` | continuous | `0.5` | temporary_control: 0.5 | Hold other update/numerical controls to limit this block to four factors; eligible in later blocks. |
| `optimizer.lr` | continuous | `0.0003` | search_this_block: 0.00003–0.001 | log scale |
| `optimizer.anneal_lr` | discrete categorical | `false` | temporary_control: false | Hold other update/numerical controls to limit this block to four factors; eligible in later blocks. |
| `optimizer.adam_eps` | continuous | `1e-05` | temporary_control: 1e-05 | Hold other update/numerical controls to limit this block to four factors; eligible in later blocks. |
| `optimizer.adam_beta1` | continuous | `0.9` | temporary_control: 0.9 | Hold other update/numerical controls to limit this block to four factors; eligible in later blocks. |
| `optimizer.adam_beta2` | continuous | `0.999` | temporary_control: 0.999 | Hold other update/numerical controls to limit this block to four factors; eligible in later blocks. |
| `network.arch` | discrete categorical | `"mlp"` | user_locked: "mlp" | user approval required to change |
| `network.mlp.hidden` | discrete integer | `512` | user_locked: 512 | user approval required to change |
| `network.mlp.layers` | discrete integer | `2` | user_locked: 4 | user approval required to change |
| `network.mlp.act` | discrete categorical | `"tanh"` | temporary_control: "tanh" | Hold activation/initialization for this block; these are not user-locked. |
| `init.hidden_gain` | continuous | `1.4142135623730951` | temporary_control: 1.4142135623730951 | Hold activation/initialization for this block; these are not user-locked. |
| `init.actor_gain` | continuous | `0.01` | temporary_control: 0.01 | Hold activation/initialization for this block; these are not user-locked. |
| `init.critic_gain` | continuous | `1.0` | temporary_control: 1.0 | Hold activation/initialization for this block; these are not user-locked. |
| `init.seed` | discrete integer | `7701` | replicate: fresh matched bank; IDs pending | matched fresh seeds, frozen before launch |
| `init.checkpoint` | discrete categorical | `null` | temporary_control: null | Fresh starts and matched replicate seeds in this block; continuation is a separate question. |
| `init.fresh_optimizer` | discrete categorical | `false` | temporary_control: false | Fresh starts and matched replicate seeds in this block; continuation is a separate question. |
| `budget.total_steps` | discrete integer | `1000000000` | temporary_control: 1000000000 | Full 60-minute endpoints in this block; longer duration remains a separate eligible experiment. |
| `budget.max_minutes` | continuous | `0.0` | temporary_control: 0.0 | Full 60-minute endpoints in this block; longer duration remains a separate eligible experiment. |
| `budget.wall_minutes` | continuous | `60.0` | temporary_control: 60.0 | Full 60-minute endpoints in this block; longer duration remains a separate eligible experiment. |
| `checkpoint.eval_every` | discrete integer | `0` | temporary_control: 0 | Endpoint-only ranking avoids checkpoint-selection confounding in this block; trajectory evaluation needs separately budgeted design. |
| `checkpoint.eval_episodes` | discrete integer | `10` | temporary_control: 10 | Endpoint-only ranking avoids checkpoint-selection confounding in this block; trajectory evaluation needs separately budgeted design. |
| `checkpoint.futility_steps` | discrete integer | `0` | temporary_control: 0 | Endpoint-only ranking avoids checkpoint-selection confounding in this block; trajectory evaluation needs separately budgeted design. |
| `checkpoint.save_every` | discrete integer | `0` | temporary_control: 0 | Endpoint-only ranking avoids checkpoint-selection confounding in this block; trajectory evaluation needs separately budgeted design. |

## Experiment-level settings

These are also experimental choices. The table is the current SQLite protocol, temporarily retained for the optimization block except obsolete relative acceptance rules. Evaluation changes must be versioned and separately reported; they cannot silently make a policy look better. Search design, seeds, budgets and selection are explicit experiment-level hyperparameters. MLflow-on is an existing user tracking requirement, not another fixed learning hyperparameter.

| SQLite experiment parameter | Current stored value |
|---|---|
| `acceptance.each_paired_gain_min` | `0.0` |
| `acceptance.mean_paired_gain_min` | `30.0` |
| `budget.aggregate_core_hours` | `15.0` |
| `budget.hard_cutoff` | `"2026-10-20T08:00:00-07:00"` |
| `budget.hardware` | `"local Apple M4 Pro CPU, one thread per job"` |
| `budget.includes_evaluation` | `true` |
| `budget.max_concurrent_jobs` | `6` |
| `budget.per_evaluation_hard_seconds` | `90.0` |
| `budget.per_run_wall_minutes` | `{"main":60.0}` |
| `budget.save_grace_seconds` | `15.0` |
| `budget.threads_per_job` | `1` |
| `design.arms` | `{"mlp512x2_lr0.0003":{"hidden":512,"lr":0.0003},"reference_mlp256x2":{}}` |
| `design.factors` | `{"candidate_source":"lowlr-1020 selected arm (final mean paired gain +33.5, acceptance met)","held_fixed":"everything else","recipe":["reference_mlp256x2","mlp512x2_lr0.0003"]}` |
| `design.phases` | `["main"]` |
| `design.reference_arm` | `"reference_mlp256x2"` |
| `design.type` | `"paired_arms_with_selection"` |
| `evaluation.action_selection` | `"sampled"` |
| `evaluation.aggregation` | `"mean over training seeds and the bank's evaluation seeds; paired gain = arm minus reference for the same training seed, averaged over the bank's evaluation seeds"` |
| `evaluation.cap_frames` | `3600` |
| `evaluation.checkpoint` | `"endpoint model.pt (eval_every 0: no periodic test, no checkpoint selection)"` |
| `evaluation.completion_definition` | `"the game's level-complete event fired during the episode (evaluate.classify_outcome 'clear'); deaths or timeouts in the countdown after the last kill are not clears"` |
| `evaluation.episodes_per_level` | `10` |
| `evaluation.frame_skip` | `4` |
| `evaluation.levels` | `"1-99"` |
| `evaluation.lives` | `1` |
| `evaluation.max_steps` | `900` |
| `evaluation.metric` | `"completed clears per 990 episodes (99 levels x 10 episodes)"` |
| `evaluation.metric_version` | `"clear-v2-2026-10-19 (level_complete event)"` |
| `evaluation.phase_roles` | `{"main":["development","final"]}` |
| `evaluation.seed_banks` | `{"development":[87001,87002],"final":[97001,97002]}` |
| `experiment.question` | `"On three fresh training seeds, does mlp512x2_lr0.0003 beat ff12 MLP 256x2 by the registered rule?"` |
| `game.name` | `"2aa2548-baron-timer"` |
| `game.source_commit` | `"2aa25480f32c003bc4b2d64167eb241c7f55d677"` |
| `game.source_hash` | `"67eaeefeb54af78652aa90ca7fe41046c987a69b5604512411b984cc786107af"` |
| `ranking.metric` | `"single candidate (no ranking); development bank reported for comparison"` |
| `ranking.tiebreak` | `["mean levels cleared at least once on the development bank","smaller parameter count","arm id"]` |
| `reference.config_sha256` | `"a8aaebb870a21dfa81ee38b258f70a5d01cabeae5a4f63149f0869eb95adca71"` |
| `reference.name` | `"reference_mlp256x2 (ff12 256x2) as the ORIGINAL comparator; retained recipe entering this round: mlp512x2_lr0.0003 (lowlr-1020 accepted)"` |
| `reference.original_comparator` | `"reference_mlp256x2"` |
| `reference.retained_recipe_entering` | `"mlp512x2_lr0.0003"` |
| `search.consumed_banks` | `{"capacity-1020":[83001,83002,93001,93002],"entropy-1020":[85001,85002,95001,95002],"lowlr-1020":[86001,86002,96001,96002],"lr-1020":[84001,84002,94001,94002]}` |
| `search.order` | `["reference_mlp256x2","mlp512x2_lr0.0003"]` |
| `search.procedure` | `"single pre-registered fresh-seed replication of the strongest candidate (make_round5_1020.py, committed before lowlr-1020 outcomes)"` |
| `seeds.allocation` | `"matched: both arms on each of three fresh training seeds (one wave of six jobs)"` |
| `seeds.training` | `{"main":[7701,7702,7703]}` |
| `selection.rule` | `"no selection: mlp512x2_lr0.0003 is the only candidate; the final bank is opened after all six checkpoint hashes are frozen; the decision uses this round's fresh pairs only. Entering retained recipe mlp512x2_lr0.0003 (lowlr-1020 accepted): rule met supports it; rule failed is conflicting evidence requiring review, not a reset to ff12."` |
| `stopping.rule` | `"fixed 60-minute deadline-aware wall limit per job counted from launch (total_steps 1e9 never binds); no early or futility stopping; larger networks need not reach equal step counts"` |
| `tracking.mlflow_experiment` | `"replicate-final-1020"` |
| `tracking.mlflow_uri` | `"http://127.0.0.1:5000"` |
| `tracking.required` | `true` |

## SQLite reporting contract for Claude

Codex owns the factor choices, ranges, sampling and selection design. Claude implements the specified manifest and executes it; changes to search scope return to Codex. Preserve existing immutable revisions. Register new experiments with 512×4, and put a structured parameter-policy map in `design.factors` (status, domain type, range/choices, sampling scale, conditional gate and temporary-control rationale). Report experiment/revision IDs plus complete run config and MLflow links. Do not claim this proposed policy map is already stored in SQLite.
