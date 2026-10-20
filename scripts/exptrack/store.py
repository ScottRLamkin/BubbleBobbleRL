"""Experiment store API: registration, provenance, lifecycle and reconstruction.

Registration is idempotent: registering the same thing twice returns the
existing record; registering a different thing under an existing identity
raises ConflictError. Configuration records are immutable (enforced by
triggers); changes are new revisions or new runs, and lifecycle is recorded as
append-only events.
"""

from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path

from . import schema
from .db import REPO, canonical, now, sha256_file, sha256_text, stable_id, transaction, value_type


class ConflictError(ValueError):
    """An identity is already registered with different content."""


# ------------------------------------------------------------------ game versions

def game_source_identity(src_dir) -> tuple[str, dict]:
    """sha256 over the game package: every file under src_dir (sorted relative
    path + content hash), excluding caches and Finder metadata."""
    src_dir = Path(src_dir)
    files = {}
    for p in sorted(src_dir.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.name != ".DS_Store" and p.suffix != ".pyc":
            files[str(p.relative_to(src_dir))] = sha256_file(p)
    return sha256_text(canonical(files)), files


def register_game_version(con, name: str, src_dir, commit: str | None, description: str) -> str:
    digest, files = game_source_identity(src_dir)
    gid = "game-" + digest[:12]
    with transaction(con):
        row = con.execute("SELECT * FROM game_versions WHERE source_hash = ? OR name = ?", (digest, name)).fetchone()
        if row:
            if row["source_hash"] != digest:
                raise ConflictError(f"game version name {name!r} is registered with different source")
            return row["id"]
        con.execute("INSERT INTO game_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (gid, name, digest, commit, canonical(files), description, now()))
        _event(con, "game_version_registered", {"game_version_id": gid, "name": name, "commit": commit})
    return gid


# ------------------------------------------------------------------- experiments

def register_experiment(con, name: str, question: str, origin: str = "registered") -> str:
    eid = stable_id("exp", name)
    with transaction(con):
        row = con.execute("SELECT * FROM experiments WHERE id = ?", (eid,)).fetchone()
        if row:
            if row["question"] != question:
                raise ConflictError(f"experiment {name!r} is registered with a different question")
            return eid
        con.execute("INSERT INTO experiments VALUES (?, ?, ?, ?, ?)", (eid, name, question, origin, now()))
        _event(con, "experiment_registered", {"name": name, "origin": origin}, experiment_id=eid)
    return eid


def register_revision(con, experiment_id: str, cfg: dict, game_version_id: str, change_note: str,
                      parent_revision_id: str | None = None) -> str:
    """An immutable experiment revision with every experiment hyperparameter.
    Returns the existing revision if this exact configuration is registered."""
    schema.validate_experiment(cfg)
    game = con.execute("SELECT * FROM game_versions WHERE id = ?", (game_version_id,)).fetchone()
    if game is None:
        raise ValueError(f"unknown game version {game_version_id}")
    if cfg["game.source_hash"] != game["source_hash"] or cfg["game.name"] != game["name"]:
        raise ValueError("game.name/game.source_hash do not match the registered game version")
    text = canonical(cfg)
    digest = sha256_text(text)
    with transaction(con):
        row = con.execute("SELECT id FROM experiment_revisions WHERE experiment_id = ? AND config_sha256 = ?",
                          (experiment_id, digest)).fetchone()
        if row:
            return row["id"]
        n = con.execute("SELECT COALESCE(MAX(revision), 0) + 1 FROM experiment_revisions WHERE experiment_id = ?",
                        (experiment_id,)).fetchone()[0]
        if n > 1 and parent_revision_id is None:
            parent_revision_id = con.execute("SELECT id FROM experiment_revisions WHERE experiment_id = ? AND "
                                             "revision = ?", (experiment_id, n - 1)).fetchone()["id"]
        rid = stable_id("rev", experiment_id, digest)
        con.execute("INSERT INTO experiment_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (rid, experiment_id, n, parent_revision_id, game_version_id, text, digest, change_note, now()))
        for key, val, unit in _experiment_rows(cfg):
            con.execute("INSERT INTO experiment_params VALUES (?, ?, ?, ?, ?)",
                        (rid, key, canonical(val), value_type(val), unit))
        _event(con, "revision_registered", {"revision": n, "config_sha256": digest, "note": change_note},
               experiment_id=experiment_id, revision_id=rid)
    return rid


def _experiment_rows(cfg: dict):
    """Each experiment key as one typed row, plus queryable expansions of the
    shared training configuration and each arm's overrides."""
    for k, (_, unit, _) in schema.EXPERIMENT_SCHEMA.items():
        yield k, cfg[k], unit
    for tk, v in cfg["shared.training"].items():
        ns, unit = schema.RUN_KEYS[tk]
        yield f"shared.{ns}", v, unit
    for arm, ov in cfg["design.arms"].items():
        for tk, v in ov.items():
            ns, unit = schema.RUN_KEYS[tk]
            yield f"design.arm.{arm}.{ns}", v, unit


# --------------------------------------------------------------------------- runs

def effective_run_config(cfg: dict, arm: str, seed: int, run_overrides: dict | None = None,
                         phase: str | None = None) -> tuple[dict, dict, dict]:
    """(effective trainer config, explicit overrides, provenance per trainer key).
    shared.training <- arm overrides <- the phase's per-run budget <- run
    overrides <- training seed."""
    run_overrides = dict(run_overrides or {})
    phase = phase or cfg["design.phases"][0]
    if arm not in cfg["design.arms"]:
        raise ValueError(f"unknown arm {arm!r}")
    if phase not in cfg["design.phases"]:
        raise ValueError(f"unknown phase {phase!r}")
    if seed not in cfg["seeds.training"][phase]:
        raise ValueError(f"seed {seed} is not allocated to phase {phase!r}")
    arm_ov = cfg["design.arms"][arm]
    bad = [k for k in run_overrides if k not in schema.TRAINER_KEYS]
    if bad:
        raise ValueError(f"unknown trainer keys in run overrides: {bad}")
    budget = {"wall_minutes": float(cfg["budget.per_run_wall_minutes"][phase])}
    eff = {**cfg["shared.training"], **arm_ov, **budget, **run_overrides, "seed": seed}
    eff = schema.validate_trainer_config(eff)
    prov = {}
    for k in eff:
        if k == "seed" or k in run_overrides:
            prov[k] = "run.override"
        elif k in budget:
            prov[k] = "experiment.budget"
        elif k in arm_ov:
            prov[k] = "experiment.arm"
        else:
            prov[k] = "experiment.shared"
    return eff, {**arm_ov, **budget, **run_overrides, "seed": seed}, prov


@lru_cache(maxsize=64)
def _network_facts(obs: str, control_obs: bool, nearest_first: bool, arch: str, hidden: int, layers: int, act: str):
    """Input size and actual parameter count, from the real Agent class."""
    import sys

    sys.path.insert(0, str(REPO / "scripts"))
    sys.path.insert(0, str(REPO / "src"))
    import torch

    from bubblebobblerl import BubbleBobbleEnv
    from train_ppo import Agent

    env = BubbleBobbleEnv(obs_type=obs, control_obs=control_obs, nearest_first=nearest_first)
    with torch.random.fork_rng(devices=[]):
        agent = Agent(env.observation_space, env.action_space.n, arch, hidden, layers, act)
    return int(env.observation_space.shape[0]) if len(env.observation_space.shape) == 1 else list(
        env.observation_space.shape), sum(p.numel() for p in agent.parameters())


def derived_run_params(eff: dict) -> dict:
    n_in, n_params = _network_facts(eff["obs"], eff["control_obs"], eff["nearest_first"], eff["arch"],
                                    eff["hidden"], eff["layers"], eff["act"])
    return {
        "network.input_size": (n_in, "inputs"),
        "network.parameter_count": (n_params, "parameters"),
        "task.max_episode_seconds": (eff["max_episode_frames"] / 60.0, "simulated seconds at 60 frames/s"),
        "checkpoint.policy": ("endpoint model.pt" if eff["eval_every"] == 0 else
                              "best.pt by the periodic standard test, model.pt at the end", None),
    }


def run_key_for(arm: str, seed: int, run_overrides: dict | None, phase: str) -> str:
    key = f"phase={phase}/arm={arm}/seed={seed}"
    if run_overrides:
        key += "/overrides=" + sha256_text(canonical(run_overrides))[:10]
    return key


def register_run(con, revision_id: str, arm: str, seed: int, run_overrides: dict | None = None,
                 origin: str = "registered", effective_override: dict | None = None,
                 run_key: str | None = None, phase: str | None = None) -> str:
    """Register one run of a revision with its complete effective configuration.
    `effective_override` (historical imports only) supplies the configuration a
    past run actually used, recorded as provenance 'historical'."""
    rev = con.execute("SELECT * FROM experiment_revisions WHERE id = ?", (revision_id,)).fetchone()
    if rev is None:
        raise ValueError(f"unknown revision {revision_id}")
    cfg = json.loads(rev["config_json"])
    phase = phase or cfg["design.phases"][0]
    if effective_override is not None:
        eff = schema.validate_trainer_config(dict(effective_override))
        overrides = dict(run_overrides or {})
        prov = {k: "historical" for k in eff}
    else:
        eff, overrides, prov = effective_run_config(cfg, arm, seed, run_overrides, phase)
    run_key = run_key or run_key_for(arm, seed, run_overrides, phase)
    text = canonical(eff)
    digest = sha256_text(text)
    rid = stable_id("run", revision_id, run_key)
    derived = derived_run_params(eff)
    game = con.execute("SELECT name, source_hash FROM game_versions WHERE id = ?", (rev["game_version_id"],)).fetchone()
    with transaction(con):
        row = con.execute("SELECT * FROM runs WHERE id = ?", (rid,)).fetchone()
        if row:
            if row["config_sha256"] != digest:
                raise ConflictError(f"run {run_key!r} is registered with a different configuration")
            return rid
        con.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (rid, revision_id, run_key, arm, text, digest, canonical(overrides), origin, now()))
        for tk, v in eff.items():
            ns, unit = schema.RUN_KEYS[tk]
            active, gated_by = schema.gate(tk, eff)
            con.execute("INSERT INTO run_params VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (rid, ns, tk, canonical(v), value_type(v), unit, int(active), gated_by if not active else None,
                         prov[tk]))
        for ns, (v, unit) in derived.items():
            con.execute("INSERT INTO run_params VALUES (?, ?, NULL, ?, ?, ?, 1, NULL, 'derived')",
                        (rid, ns, canonical(v), value_type(v), unit))
        for ns, v in (("game.name", game["name"]), ("game.source_hash", game["source_hash"]), ("design.phase", phase),
                      ("design.arm", arm)):
            con.execute("INSERT INTO run_params VALUES (?, ?, NULL, ?, 'str', NULL, 1, NULL, 'experiment.revision')",
                        (rid, ns, canonical(v)))
        _event(con, "run_registered", {"run_key": run_key, "config_sha256": digest, "origin": origin},
               revision_id=revision_id, run_id=rid)
    return rid


def reconstruct_run_config(con, run_id: str) -> dict:
    """The complete trainer configuration rebuilt from the parameter rows alone,
    checked against the stored snapshot and its hash."""
    rows = con.execute("SELECT trainer_key, value_json FROM run_params WHERE run_id = ? AND trainer_key IS NOT NULL",
                       (run_id,)).fetchall()
    cfg = {r["trainer_key"]: json.loads(r["value_json"]) for r in rows}
    run = con.execute("SELECT config_json, config_sha256 FROM runs WHERE id = ?", (run_id,)).fetchone()
    if canonical(cfg) != run["config_json"] or sha256_text(canonical(cfg)) != run["config_sha256"]:
        raise RuntimeError(f"run {run_id}: parameter rows disagree with the stored configuration")
    schema.validate_trainer_config(cfg)
    return cfg


def experiment_config(con, revision_id: str) -> dict:
    row = con.execute("SELECT config_json, config_sha256 FROM experiment_revisions WHERE id = ?", (revision_id,)).fetchone()
    if sha256_text(row["config_json"]) != row["config_sha256"]:
        raise RuntimeError(f"revision {revision_id}: stored configuration does not match its hash")
    return json.loads(row["config_json"])


# ------------------------------------------------------- attempts, events, records

def create_attempt(con, run_id: str, run_dir: str | None, tracking_uri: str | None, mlflow_experiment_id: str | None,
                   mlflow_run_id: str | None) -> str:
    with transaction(con):
        n = con.execute("SELECT COALESCE(MAX(attempt), 0) + 1 FROM run_attempts WHERE run_id = ?", (run_id,)).fetchone()[0]
        aid = f"{run_id}-a{n}"
        con.execute("INSERT INTO run_attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (aid, run_id, n, run_dir, tracking_uri, mlflow_experiment_id, mlflow_run_id, now()))
        _event(con, "attempt_created", {"attempt": n, "run_dir": run_dir, "mlflow_run_id": mlflow_run_id},
               run_id=run_id, attempt_id=aid)
    return aid


def find_attempt(con, run_id: str, attempt: int = 1):
    return con.execute("SELECT * FROM run_attempts WHERE run_id = ? AND attempt = ?", (run_id, attempt)).fetchone()


def add_event(con, event: str, detail: dict | None = None, **ids) -> None:
    with transaction(con):
        _event(con, event, detail or {}, **ids)


def _event(con, event: str, detail: dict, experiment_id=None, revision_id=None, run_id=None, attempt_id=None,
           evaluation_id=None) -> None:
    con.execute("INSERT INTO events (ts, experiment_id, revision_id, run_id, attempt_id, evaluation_id, event, "
                "detail_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (now(), experiment_id, revision_id, run_id, attempt_id, evaluation_id, event, canonical(detail)))


def run_state(con, run_id: str) -> str:
    row = con.execute("SELECT event FROM events WHERE run_id = ? AND event IN ('run_registered', 'dispatched', "
                      "'training_started', 'training_finished', 'evaluated', 'finished', 'failed', 'not_run') "
                      "ORDER BY id DESC LIMIT 1", (run_id,)).fetchone()
    return row["event"] if row else "unknown"


def register_evaluation(con, run_id: str, attempt_id: str | None, game_version_id: str, checkpoint_path: str,
                        checkpoint_sha256: str, protocol: dict, role: str, metric_definition: str, metric_version: str,
                        results: dict, raw_path: str | None, origin: str = "registered") -> str:
    """A repeatable evaluation record. A different protocol on the same
    checkpoint is a new record; existing records are never rewritten."""
    ptext = canonical(protocol)
    psha = sha256_text(ptext)
    eid = stable_id("eval", run_id, checkpoint_sha256, psha)
    raw_sha = sha256_file(raw_path) if raw_path and Path(raw_path).exists() else None
    with transaction(con):
        row = con.execute("SELECT * FROM evaluations WHERE id = ?", (eid,)).fetchone()
        if row:
            if row["results_json"] != canonical(results):
                raise ConflictError(f"evaluation {eid} already recorded with different results")
            return eid
        con.execute("INSERT INTO evaluations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (eid, run_id, attempt_id, game_version_id, checkpoint_path, checkpoint_sha256, ptext, psha, role,
                     metric_definition, metric_version, canonical(results), raw_path, raw_sha, origin, now()))
        for k, v in protocol.items():
            con.execute("INSERT INTO evaluation_params VALUES (?, ?, ?, ?, ?)",
                        (eid, k, canonical(v), value_type(v), None))
        _event(con, "evaluated", {"role": role, "protocol_sha256": psha, "results": results}, run_id=run_id,
               attempt_id=attempt_id, evaluation_id=eid)
    return eid


def add_artifact(con, kind: str, path: str, sha256: str | None = None, note: str = "", experiment_id=None,
                 run_id=None, attempt_id=None, evaluation_id=None) -> None:
    with transaction(con):
        con.execute("INSERT OR IGNORE INTO artifacts (experiment_id, run_id, attempt_id, evaluation_id, kind, path, "
                    "sha256, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (experiment_id, run_id, attempt_id, evaluation_id, kind, str(path), sha256, note, now()))


def query_params(con, level: str, key: str) -> list[sqlite3.Row]:
    """Rows of one namespaced parameter across all runs ('run') or revisions ('experiment')."""
    if level == "run":
        return con.execute("SELECT r.run_key, r.arm, p.* FROM run_params p JOIN runs r ON r.id = p.run_id "
                           "WHERE p.key = ? ORDER BY r.run_key", (key,)).fetchall()
    return con.execute("SELECT e.name, v.revision, p.* FROM experiment_params p JOIN experiment_revisions v ON "
                       "v.id = p.revision_id JOIN experiments e ON e.id = v.experiment_id WHERE p.key = ? "
                       "ORDER BY e.name, v.revision", (key,)).fetchall()
