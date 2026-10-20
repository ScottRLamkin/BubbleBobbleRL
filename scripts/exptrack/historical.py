"""Import the October 19 campaigns (hparam-1019-v1, hparam-1019-v2,
paired-1019-v3) into the experiment store, idempotently, from their own records.

- Game versions are hashed from each campaign's frozen snapshot.
- The experiment revision is built from the frozen manifest. Each run's
  configuration is the one the run actually recorded (config.json; v1's
  pre-2026-10-19 file is mapped with hyperparams.from_legacy_run). Arm
  overrides are the differences from the reference arm's recorded
  configuration, and every run is stored with provenance "historical".
- Evaluations come from the raw evaluation files (exact schema checked), with
  the protocol the manifest specified and the role they served.
- These campaigns ran with --no-mlflow, so no learning curves exist. Each
  training run gets a clearly labelled MLflow import run (origin
  historical_import, source start/end timestamps) holding only recorded
  end-of-run facts: training steps/updates/seconds and evaluation results.
  Nothing is interpolated or invented.
- Checkpoints, raw evaluations, configurations, reports and versioned
  galleries (matched by checkpoint hash) are recorded as artifacts.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from . import db, schema, store
from .mlflow_sink import client_for, ensure_experiment, find_run_by_tag, log_params, preflight

GAME_NAMES = {"hparam-1019-v1": "42ed83d-before-fidelity-fixes",
              "hparam-1019-v2": "d8619ba-baron-timers-reversed",
              "paired-1019-v3": "2aa2548-baron-timer"}
NOTE = ("Historical import (created {today}): this campaign trained with --no-mlflow, so no learning curves "
        "were recorded and none are shown. Metrics here are end-of-run facts copied from the campaign's own "
        "records (train_summary.json, raw evaluation files), timestamped at their source times.")


def ms(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso).timestamp() * 1000)


def actual_config(path: Path) -> dict:
    from hyperparams import NAMES, from_legacy_run, validate

    raw = json.loads(path.read_text())
    if all(n in raw for n in NAMES):
        return validate({n: raw[n] for n in NAMES})
    return from_legacy_run(raw)


def eval_results(raw_path: Path, episodes_per_level: int) -> dict:
    from audit_hparam_campaign import check_eval_file

    summary, problems = check_eval_file(raw_path, episodes_per_level)
    if problems:
        raise ValueError(f"{raw_path}: {problems[:3]}")
    raw = json.loads(raw_path.read_text())
    return {"cleared": summary["cleared"], "died": summary["died"], "timeout": summary["timeout"],
            "episodes": raw["episodes"], "levels_cleared": raw["levels_cleared"],
            "kills_per_episode": raw["kills_per_episode"], "mean_score": raw["mean_score"],
            "per_level_clears": {str(lv): v["clear"] for lv, v in summary["per_level"].items()}}


def _arms(configs: dict[str, dict], reference: str) -> tuple[dict, dict]:
    """(shared.training, arm -> overrides) from each arm's recorded
    configuration; seed and wall_minutes come from the phase, not the arm."""
    shared = configs[reference]
    arms = {}
    for arm, cfg in configs.items():
        arms[arm] = {k: v for k, v in cfg.items() if k not in ("seed", "wall_minutes") and shared[k] != v}
    return shared, arms


# ------------------------------------------------------------- campaigns

def _search_campaign(root: Path) -> dict:
    """hparam-1019-v1/v2: screen at 15 min, confirmation at 60, final bank."""
    status = json.loads((root / "status.json").read_text())
    info = json.loads((root / "snapshot.json").read_text())
    mrel = info.get("manifest", "scripts/campaigns/hyperparameter_search_1019.json")
    m = json.loads((root / "snapshot" / mrel).read_text())
    if db.sha256_file(root / "snapshot" / mrel) != status["manifest_sha256"]:
        raise ValueError(f"{root}: manifest hash differs from status.json")
    trains = {k: j for k, j in status["jobs"].items() if j["kind"] == "train"}
    configs, runs = {}, []
    for jid, j in trains.items():
        cfg = actual_config(Path(j["dir"]) / "config.json")
        if j["config"] in configs:
            a = {k: v for k, v in configs[j["config"]].items() if k not in ("seed", "wall_minutes")}
            b = {k: v for k, v in cfg.items() if k not in ("seed", "wall_minutes")}
            if a != b:
                raise ValueError(f"{jid}: runs of configuration {j['config']} recorded different settings")
        else:
            configs[j["config"]] = cfg
        role_seeds = j["eval_seeds"]
        runs.append({"job": jid, "phase": j["phase"], "arm": j["config"], "seed": j["seed"], "dir": Path(j["dir"]),
                     "config": cfg, "model_sha256": j["model_sha256"], "started": j["started"], "ended": j["ended"],
                     "summary": j["train_summary"], "elapsed_seconds": j["elapsed_seconds"],
                     "evaluations": [("screen" if j["phase"] == "screen" else "tuning", s,
                                      Path(j["dir"]) / f"eval_{s}.json", j["ended"]) for s in role_seeds]})
    for jid, j in status["jobs"].items():
        if j["kind"] == "eval":
            host = next(r for r in runs if r["phase"] == "confirmation" and r["arm"] == j["config"]
                        and r["seed"] == j["seed"])
            if host["model_sha256"] != j["model_sha256"]:
                raise ValueError(f"{jid}: evaluated checkpoint differs from its training run")
            host["evaluations"].append(("final", j["eval_seed"], Path(j["dir"]) / f"eval_{j['eval_seed']}.json",
                                        j["ended"]))
    shared, arms = _arms(configs, "anchor_G")
    ev, b, scr, conf, fin = m["evaluation"], m["budget"], m["screen"], m["confirmation_training"], m["final_test"]
    exp = {
        "experiment.question": ("Which PPO settings (learning rate, entropy coefficient, discount horizon, rollout "
                                "length, epochs, clip) beat recipe G (anchor_G) at a fixed CPU budget? Screen, "
                                "confirm the top two at one hour, final-test the winner "
                                f"(protocol {m['protocol']})."),
        "game.name": GAME_NAMES[m["campaign_id"]],
        "game.source_hash": store.game_source_identity(root / "snapshot" / "src" / "bubblebobblerl")[0],
        "game.source_commit": info["commit"],
        "reference.name": "recipe G (anchor_G)",
        "reference.config_sha256": db.sha256_text(db.canonical(shared)),
        "design.type": "fractional_factorial_screen",
        "design.arms": arms,
        "design.factors": {"type": m["design"]["type"], "factors": m["design"]["factors"],
                           **{k: m["design"][k] for k in ("generators", "defining_relation") if k in m["design"]}},
        "design.reference_arm": "anchor_G",
        "design.phases": ["screen", "confirmation"],
        "shared.training": shared,
        "seeds.training": {"screen": [scr["training_seed"]], "confirmation": conf["training_seeds"]},
        "seeds.allocation": "screen: every configuration on one training seed; confirmation: "
                            f"{conf['configurations']} on each confirmation seed",
        "evaluation.levels": ev["levels"],
        "evaluation.episodes_per_level": ev["episodes_per_level"],
        "evaluation.seed_banks": {"screen": scr["evaluation_seeds"], "tuning": conf["evaluation_seeds"],
                                  "final": fin["evaluation_seeds"]},
        "evaluation.phase_roles": {"screen": ["screen"], "confirmation": ["tuning", "final"]},
        "evaluation.lives": 1 if ev["one_life"] else -1,
        "evaluation.max_steps": ev["max_steps"],
        "evaluation.frame_skip": ev["frame_skip"],
        "evaluation.cap_frames": ev["max_steps"] * ev["frame_skip"],
        "evaluation.action_selection": "sampled" if ev["sampled_actions"] else "greedy",
        "evaluation.completion_definition": ev["outcome"],
        "evaluation.metric": fin["metric"],
        "evaluation.metric_version": "clear-v2-2026-10-19 (level_complete event)",
        "evaluation.aggregation": "mean over training seeds and evaluation seeds; paired gain per training seed",
        "evaluation.checkpoint": scr["checkpoint"] + " (final saved weights)",
        "search.procedure": m["design"]["type"],
        "search.order": scr["order"],
        "budget.hardware": b["hardware"],
        "budget.per_run_wall_minutes": {"screen": float(scr["minutes_per_policy"]),
                                        "confirmation": float(conf["minutes_per_policy"])},
        "budget.aggregate_core_hours": float(b["aggregate_allocated_core_hours"]),
        "budget.includes_evaluation": True,
        "budget.max_concurrent_jobs": b["max_concurrent_jobs"],
        "budget.threads_per_job": b["threads_per_job"],
        "budget.per_evaluation_hard_seconds": float(b["per_evaluation_hard_seconds"]),
        "budget.save_grace_seconds": float(b["per_training_save_grace_seconds"]),
        "budget.hard_cutoff": b["hard_cutoff"],
        "stopping.rule": "fixed wall time per policy (screen 15 min, confirmation 60 min); final saved weights only",
        "ranking.metric": scr["selection"],
        "ranking.tiebreak": ["mean kills", "configuration id"],
        "selection.rule": conf["selection"] + " Final: " + fin["failure_action"],
        "acceptance.mean_paired_gain_min": float(fin["practical_improvement"]["mean_paired_gain_min"]),
        "acceptance.each_paired_gain_min": float(fin["practical_improvement"]["each_paired_gain_min"]),
        "tracking.mlflow_uri": None, "tracking.mlflow_experiment": None, "tracking.required": False,
    }
    return {"campaign": m["campaign_id"], "experiment": exp, "runs": runs, "root": root, "info": info,
            "artifacts": [p for p in (root / "report.md", root / "audit.md", root / "status.json",
                                      root / "snapshot.json", root / "frozen.json", root / "per_level.csv")
                          if p.exists()]}


def _paired_campaign(root: Path) -> dict:
    status = json.loads((root / "status.json").read_text())
    info = json.loads((root / "snapshot.json").read_text())
    m = json.loads((root / "snapshot" / info["manifest"]).read_text())
    configs, runs = {}, []
    for jid, j in status["jobs"].items():
        d = root / jid
        cfg = actual_config(d / "config.json")
        configs.setdefault(j["arm"], cfg)
        runs.append({"job": jid, "phase": "main", "arm": j["arm"], "seed": j["seed"], "dir": d, "config": cfg,
                     "model_sha256": j["model_sha256"], "started": j["started"], "ended": j["ended"],
                     "summary": json.loads((d / "train_summary.json").read_text()),
                     "elapsed_seconds": j["elapsed_seconds"],
                     "evaluations": [("paired_test", int(s), d / f"eval_{s}.json", j["ended"])
                                     for s in m["evaluation"]["seeds"]]})
    shared, arms = _arms(configs, m["reference_arm"])
    ev, b, acc = m["evaluation"], m["budget"], m["acceptance"]
    exp = {
        "experiment.question": m["question"],
        "game.name": GAME_NAMES[m["campaign_id"]],
        "game.source_hash": store.game_source_identity(root / "snapshot" / "src" / "bubblebobblerl")[0],
        "game.source_commit": info["commit"],
        "reference.name": f"recipe G ({m['reference_arm']})",
        "reference.config_sha256": db.sha256_text(db.canonical(shared)),
        "design.type": "paired_arms",
        "design.arms": arms,
        "design.factors": {"recipe": list(m["arms"])},
        "design.reference_arm": m["reference_arm"],
        "design.phases": ["main"],
        "shared.training": shared,
        "seeds.training": {"main": m["training_seeds"]},
        "seeds.allocation": "matched: both arms on each training seed",
        "evaluation.levels": ev["levels"],
        "evaluation.episodes_per_level": ev["episodes_per_level"],
        "evaluation.seed_banks": {"paired_test": ev["seeds"]},
        "evaluation.phase_roles": {"main": ["paired_test"]},
        "evaluation.lives": 1,
        "evaluation.max_steps": ev["max_steps"],
        "evaluation.frame_skip": ev["frame_skip"],
        "evaluation.cap_frames": ev["max_steps"] * ev["frame_skip"],
        "evaluation.action_selection": "sampled",
        "evaluation.completion_definition": "level_complete event (evaluate.classify_outcome 'clear')",
        "evaluation.metric": "completed clears per 990 episodes",
        "evaluation.metric_version": "clear-v2-2026-10-19 (level_complete event)",
        "evaluation.aggregation": "paired gain per training seed, averaged over evaluation seeds",
        "evaluation.checkpoint": "endpoint model.pt",
        "search.procedure": "fixed two-arm paired comparison",
        "search.order": list(m["arms"]),
        "budget.hardware": b["hardware"],
        "budget.per_run_wall_minutes": {"main": float(m["overrides"]["wall_minutes"])},
        "budget.aggregate_core_hours": float(b["aggregate_allocated_core_hours"]),
        "budget.includes_evaluation": True,
        "budget.max_concurrent_jobs": b["max_concurrent_jobs"],
        "budget.threads_per_job": b["threads_per_job"],
        "budget.per_evaluation_hard_seconds": float(b["per_evaluation_hard_seconds"]),
        "budget.save_grace_seconds": float(b["save_grace_seconds"]),
        "budget.hard_cutoff": b["hard_cutoff"],
        "stopping.rule": m["stopping"],
        "ranking.metric": "none (two predeclared arms)",
        "ranking.tiebreak": [],
        "selection.rule": "none: ff12 versus the reference, acceptance rule only",
        "acceptance.mean_paired_gain_min": float(acc["mean_paired_gain_min"]),
        "acceptance.each_paired_gain_min": float(acc["each_paired_gain_min"]),
        "tracking.mlflow_uri": None, "tracking.mlflow_experiment": None, "tracking.required": False,
    }
    return {"campaign": m["campaign_id"], "experiment": exp, "runs": runs, "root": root, "info": info,
            "artifacts": [p for p in (root / "results.json", root / "status.json", root / "snapshot.json",
                                      root.parents[1] / "docs" / "paired-1019-v3-results.md") if p.exists()]}


# ---------------------------------------------------------------- import

def import_campaign(con, root, mlflow_uri: str, exports=None) -> dict:
    root = Path(root).resolve()
    snap_scripts = root / "snapshot" / "scripts"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    plan = _paired_campaign(root) if (root / "results.json").exists() and not (root / "frozen.json").exists() \
        else _search_campaign(root)
    exp = schema.validate_experiment(plan["experiment"])
    gid = store.register_game_version(con, exp["game.name"], root / "snapshot" / "src" / "bubblebobblerl",
                                      exp["game.source_commit"], f"game package of the {plan['campaign']} snapshot")
    game_hash = con.execute("SELECT source_hash FROM game_versions WHERE id = ?", (gid,)).fetchone()[0]
    if game_hash != exp["game.source_hash"]:
        raise ValueError("game hash mismatch")
    if con.execute("SELECT name FROM game_versions WHERE id = ?", (gid,)).fetchone()[0] != exp["game.name"]:
        exp["game.name"] = con.execute("SELECT name FROM game_versions WHERE id = ?", (gid,)).fetchone()[0]
    eid = store.register_experiment(con, plan["campaign"], exp["experiment.question"], origin="historical_import")
    rid = store.register_revision(con, eid, exp, gid, "historical import from the frozen manifest and the "
                                                      "runs' recorded configurations")
    preflight(mlflow_uri)
    client = client_for(mlflow_uri)
    ml_exp = ensure_experiment(client, f"{plan['campaign']} (historical import)")
    today = dt.date.today().isoformat()
    evaluator_sha = db.sha256_file(snap_scripts / "evaluate.py")
    galleries = {}
    for ident in Path(exports or (db.REPO / "exports")).glob("*/identity.json"):
        try:
            galleries.setdefault(json.loads(ident.read_text()).get("checkpoint_sha256"), []).append(ident.parent)
        except (ValueError, OSError):
            continue
    counts = {"runs": 0, "evaluations": 0, "mlflow_created": 0, "galleries": 0}
    for r in plan["runs"]:
        run_id = store.register_run(con, rid, r["arm"], r["seed"], origin="historical_import",
                                    effective_override=r["config"], phase=r["phase"])
        counts["runs"] += 1
        model = r["dir"] / "model.pt"
        if db.sha256_file(model) != r["model_sha256"]:
            raise ValueError(f"{model} no longer matches the campaign's recorded hash")
        found = find_run_by_tag(client, ml_exp, "exptrack.run_id", run_id)
        if found is None:
            run_key = con.execute("SELECT run_key FROM runs WHERE id = ?", (run_id,)).fetchone()[0]
            tags = {"origin": "historical_import", "mlflow.note.content": NOTE.format(today=today),
                    "learning_curves": "not recorded (trained with --no-mlflow)",
                    "exptrack.experiment_id": eid, "exptrack.revision_id": rid, "exptrack.run_id": run_id,
                    "exptrack.run_key": run_key, "exptrack.attempt": "1", "exptrack.attempt_id": f"{run_id}-a1",
                    "campaign": plan["campaign"], "phase": r["phase"], "arm": r["arm"],
                    "training_seed": str(r["seed"]), "game_version": exp["game.name"],
                    "game_source_hash": exp["game.source_hash"], "snapshot_commit": plan["info"]["commit"],
                    "source_run_dir": str(r["dir"])}
            ml = client.create_run(ml_exp, start_time=ms(r["started"]), tags=tags,
                                   run_name=f"{r['job'].replace('/', '_')} (import)")
            params = {row["key"]: json.loads(row["value_json"]) for row in con.execute(
                "SELECT key, value_json FROM run_params WHERE run_id = ?", (run_id,))}
            log_params(client, ml.info.run_id, params)
            ml_id = ml.info.run_id
            counts["mlflow_created"] += 1
        else:
            ml_id = found.info.run_id
        if store.find_attempt(con, run_id, 1) is None:
            store.create_attempt(con, run_id, str(r["dir"]), mlflow_uri, ml_exp, ml_id)
        attempt_id = f"{run_id}-a1"
        from mlflow.entities import Metric

        s = r["summary"]
        metrics = [Metric(k, float(v), ms(r["ended"]), int(s["steps"]))
                   for k, v in (("train_steps", s["steps"]), ("train_updates", s["updates"]),
                                ("train_seconds", s["seconds"]), ("allocated_seconds", r["elapsed_seconds"]))]
        for role, seed, raw, ended in r["evaluations"]:
            res = eval_results(raw, exp["evaluation.episodes_per_level"])
            proto = {"role": role, "seed": seed, "levels": exp["evaluation.levels"],
                     "episodes_per_level": exp["evaluation.episodes_per_level"], "lives": exp["evaluation.lives"],
                     "max_steps": exp["evaluation.max_steps"], "frame_skip": exp["evaluation.frame_skip"],
                     "cap_frames": exp["evaluation.cap_frames"],
                     "action_selection": exp["evaluation.action_selection"],
                     "completion_definition": exp["evaluation.completion_definition"], "obs": r["config"]["obs"],
                     "control_obs": r["config"]["control_obs"], "nearest_first": r["config"]["nearest_first"],
                     "game_source_hash": exp["game.source_hash"], "evaluator_sha256": evaluator_sha}
            ev_id = store.register_evaluation(con, run_id, attempt_id, gid, str(model), r["model_sha256"], proto, role,
                                              exp["evaluation.metric"], exp["evaluation.metric_version"], res,
                                              str(raw), origin="historical_import")
            store.add_artifact(con, "evaluation_raw", raw, db.sha256_file(raw), run_id=run_id, attempt_id=attempt_id,
                               evaluation_id=ev_id)
            counts["evaluations"] += 1
            metrics += [Metric(f"eval_{role}_s{seed}_{k}", float(res[k]), ms(ended), int(s["steps"]))
                        for k in ("cleared", "died", "timeout", "levels_cleared", "kills_per_episode")]
        client.log_batch(ml_id, metrics=metrics)  # identical resends are ignored by the store
        if client.get_run(ml_id).info.status != "FINISHED":
            client.set_terminated(ml_id, "FINISHED", end_time=ms(r["ended"]))
        for kind, name in (("checkpoint", "model.pt"), ("optimizer", "optimizer.pt"), ("trainer_config", "config.json"),
                           ("architecture", "arch.json"), ("train_summary", "train_summary.json")):
            if (r["dir"] / name).exists():
                store.add_artifact(con, kind, r["dir"] / name, db.sha256_file(r["dir"] / name), run_id=run_id,
                                   attempt_id=attempt_id)
        for g in galleries.get(r["model_sha256"], []):
            store.add_artifact(con, "gameplay_gallery", g, db.sha256_file(g / "identity.json"),
                               note="versioned gallery (identity.json hash)", run_id=run_id, attempt_id=attempt_id)
            counts["galleries"] += 1
    for p in plan["artifacts"]:
        store.add_artifact(con, "campaign_record", p, db.sha256_file(p), experiment_id=eid)
    store.add_event(con, "historical_import", {"root": str(root), **counts}, experiment_id=eid, revision_id=rid)
    return {"experiment_id": eid, "revision_id": rid, "game_version_id": gid, "mlflow_experiment_id": ml_exp,
            **counts}
