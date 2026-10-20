"""Experiment tracking: mandatory MLflow, the durable metric outbox, and the
SQLite experiment store (scripts/exptrack)."""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

BASE = str(REPO / "configs" / "hparam-1019_anchor_G_screen.json")
TINY = ["--config", BASE, "--obs", "state", "--levels", "1", "--total-steps", "64", "--num-envs", "2",
        "--rollout-len", "16", "--eval-every", "0", "--wall-minutes", "0", "--log-every", "1",
        "--no-tensorboard", "--quiet"]


# ----------------------------------------------------------- mandatory MLflow

def test_mlflow_cannot_be_turned_off(tmp_path):
    from train_ppo import parse_args

    with pytest.raises(SystemExit):
        parse_args(TINY + ["--no-mlflow", "--run-dir", str(tmp_path)])
    cfg = json.loads(Path(BASE).read_text())
    cfg["no_mlflow"] = True
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(cfg))
    with pytest.raises(SystemExit):
        parse_args(["--config", str(bad), "--run-dir", str(tmp_path)])


def test_unreachable_service_fails_before_training(tmp_path):
    from exptrack.mlflow_sink import TrackingUnavailable
    from train_ppo import parse_args, train

    with pytest.raises(TrackingUnavailable):
        train(parse_args(TINY + ["--mlflow-tracking-uri", "http://127.0.0.1:1", "--run-dir", str(tmp_path)]))
    assert not (tmp_path / "model.pt").exists() and not (tmp_path / "config.json").exists()


def test_default_uri_has_no_silent_fallback(monkeypatch):
    import train_ppo
    from exptrack import mlflow_sink

    monkeypatch.delenv("MLFLOW_TRACKING_URI")
    assert train_ppo.mlflow_tracking_uri() == "http://127.0.0.1:5000"
    assert mlflow_sink.resolve_uri() == "http://127.0.0.1:5000"


def test_training_logs_losses_and_finishes_the_run(tmp_path):
    from exptrack.mlflow_sink import client_for
    from train_ppo import mlflow_tracking_uri, parse_args, train

    train(parse_args(TINY + ["--run-dir", str(tmp_path), "--mlflow-tag", "purpose=test"]))
    run_id = (tmp_path / "mlflow_run_id.txt").read_text()
    client = client_for(mlflow_tracking_uri())
    run = client.get_run(run_id)
    assert run.info.status == "FINISHED" and run.data.tags["purpose"] == "test"
    for key in ("losses_policy_loss", "losses_value_loss", "losses_entropy", "losses_approx_kl"):
        assert key in run.data.metrics, (key, sorted(run.data.metrics))
    assert run.data.params["gamma"] == json.dumps(json.loads(Path(BASE).read_text())["gamma"])
    status = json.loads((tmp_path / "mlflow_status.json").read_text())
    assert status["pending"] == 0 and status["terminated"] == "FINISHED"


def test_outage_during_training_is_a_hard_failure_and_replays_without_duplicates(tmp_path, monkeypatch):
    from exptrack import mlflow_sink
    from exptrack.mlflow_sink import TrackedRun, TrackingUnavailable, client_for, replay
    from train_ppo import mlflow_tracking_uri, parse_args, train

    monkeypatch.setattr(mlflow_sink, "RETRY_SECONDS", (0, 0, 0))
    real_upload = TrackedRun._upload
    calls = {"n": 0}

    def flaky(self):  # the service answers the first upload, then goes away
        calls["n"] += 1
        if calls["n"] > 1:
            raise ConnectionError("service down")
        real_upload(self)

    monkeypatch.setattr(TrackedRun, "_upload", flaky)
    with pytest.raises(TrackingUnavailable):
        train(parse_args(TINY + ["--total-steps", "256", "--run-dir", str(tmp_path)]))
    run_id = (tmp_path / "mlflow_run_id.txt").read_text()
    outbox = tmp_path / "mlflow_outbox.jsonl"
    status = json.loads((tmp_path / "mlflow_status.json").read_text())
    assert status["pending"] > 0 and status["terminated"] is None
    client = client_for(mlflow_tracking_uri())
    before = len(client.get_metric_history(run_id, "losses_policy_loss"))
    assert client.get_run(run_id).info.status == "RUNNING"

    monkeypatch.setattr(TrackedRun, "_upload", real_upload)
    sent = replay(mlflow_tracking_uri(), run_id, outbox)
    assert sent == status["pending"]
    after = len(client.get_metric_history(run_id, "losses_policy_loss"))
    assert after > before
    events = [json.loads(line) for line in outbox.read_text().splitlines()]
    assert after == sum(e["key"] == "losses_policy_loss" for e in events)
    # An ambiguous failure can resend everything; the store keeps one copy of each.
    (tmp_path / "mlflow_outbox.jsonl.sent").write_text("0")
    replay(mlflow_tracking_uri(), run_id, outbox)
    assert len(client.get_metric_history(run_id, "losses_policy_loss")) == after


def test_attach_requires_an_open_run(tmp_path):
    from exptrack.mlflow_sink import TrackedRun, TrackingUnavailable, client_for, ensure_experiment
    from train_ppo import mlflow_tracking_uri

    uri = mlflow_tracking_uri()
    client = client_for(uri)
    run = client.create_run(ensure_experiment(client, "attach-test"))
    t = TrackedRun.attach(uri, run.info.run_id, tmp_path / "o.jsonl")
    t.log_metrics({"x": 1.0}, step=0)
    t.finish()
    with pytest.raises(TrackingUnavailable):
        TrackedRun.attach(uri, run.info.run_id, tmp_path / "o.jsonl")
    with pytest.raises(TrackingUnavailable):
        TrackedRun.attach(uri, "0" * 32, tmp_path / "o.jsonl")


# ------------------------------------------------------- campaign plumbing

def _fake_snapshot(root: Path, manifest: dict) -> None:
    """A snapshot directory like run_hyperparameter_search.py's (copied source,
    snapshot.json with file hashes), for a tiny campaign."""
    import shutil

    from exptrack.db import sha256_file

    snap = root / "snapshot"
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
    shutil.copytree(REPO / "src", snap / "src", ignore=ignore)
    shutil.copytree(REPO / "scripts", snap / "scripts", ignore=ignore)
    (snap / "scripts" / "campaigns" / "tiny.json").write_text(json.dumps(manifest, indent=1))
    files = {str(p.relative_to(snap)): sha256_file(p) for p in sorted(snap.rglob("*")) if p.is_file()}
    (root / "snapshot.json").write_text(json.dumps({
        "campaign": manifest["campaign_id"], "manifest": "scripts/campaigns/tiny.json", "commit": "test",
        "interpreter": sys.executable, "manifest_sha256": files["scripts/campaigns/tiny.json"], "files": files}))


def _tiny_manifest(name: str, uri: str, lives: int = 1, wide: int = 64) -> dict:
    m = json.loads((REPO / "scripts" / "campaigns" / "capacity_1020.json").read_text())
    e = m["experiment"]
    e["shared.training"].update(num_envs=2, rollout_len=16, hidden=32, levels="1-3")
    e.update({
        "design.arms": {"ref": {}, "wide": {"hidden": wide}},
        "design.reference_arm": "ref", "search.order": ["ref", "wide"],
        "seeds.training": {"main": [11]}, "budget.per_run_wall_minutes": {"main": 0.05},
        "evaluation.episodes_per_level": 1, "evaluation.max_steps": 20, "evaluation.cap_frames": 80,
        "evaluation.seed_banks": {"development": [5], "final": [6]}, "evaluation.lives": lives,
        "budget.max_concurrent_jobs": 1, "budget.aggregate_core_hours": 1.0, "budget.hard_cutoff": None,
        "tracking.mlflow_uri": uri, "tracking.mlflow_experiment": name,
        "reference.retained_recipe_entering": None, "reference.original_comparator": None,
        "search.consumed_banks": None,
    })
    from exptrack.db import canonical, sha256_text
    from hyperparams import validate

    e["reference.config_sha256"] = sha256_text(canonical(validate(dict(e["shared.training"]))))
    m["campaign_id"] = name
    return m


def test_tracked_campaign_end_to_end(tmp_path):
    """Registration, MLflow links, training, development evaluation, frozen
    selection, final evaluation and results, with real subprocesses."""
    from exptrack import db, store
    from exptrack.campaign import Campaign
    from exptrack.mlflow_sink import client_for
    from train_ppo import mlflow_tracking_uri

    uri = mlflow_tracking_uri()
    root = tmp_path / "tiny"
    _fake_snapshot(root, _tiny_manifest("tiny-campaign", uri))
    dbp = tmp_path / "exp.sqlite3"
    c = Campaign(root, dbp, require_snapshot_code=False)
    pre = c.preflight()
    assert pre["ok"], pre
    Campaign(root, dbp, require_snapshot_code=False).run()

    con = db.connect(dbp)
    status = json.loads((root / "status.json").read_text())
    assert all(j["state"] == "done" for j in status["jobs"].values()), status["jobs"]
    results = json.loads((root / "results.json").read_text())
    assert results["selected_arm"] == "wide" and set(results["paired_gain_per_training_seed"]) == {"11"}
    sel = json.loads((root / "selection.json").read_text())
    client = client_for(uri)
    for jid, j in status["jobs"].items():
        run = con.execute("SELECT * FROM runs WHERE id = ?", (j["run_id"],)).fetchone()
        cfg = store.reconstruct_run_config(con, j["run_id"])
        trained = json.loads((Path(j["dir"]) / "config.json").read_text())
        assert all(trained[k] == v for k, v in cfg.items())
        att = store.find_attempt(con, j["run_id"], 1)
        ml = client.get_run(att["mlflow_run_id"])  # reciprocal links
        assert ml.data.tags["exptrack.run_id"] == run["id"] and ml.data.tags["exptrack.attempt_id"] == att["id"]
        assert ml.info.status == "FINISHED" and "losses_policy_loss" in ml.data.metrics
        assert "eval_development_s5_cleared" in ml.data.metrics
        assert ml.data.params["network.mlp.hidden"] == str(cfg["hidden"])
        roles = {r["role"] for r in con.execute("SELECT role FROM evaluations WHERE run_id = ?", (j["run_id"],))}
        assert roles == {"development", "final"}  # two arms: the selected one and the reference both get final
        assert j["model_sha256"] == sel["checkpoints"][j["arm"]]["11"]
    events = [r["event"] for r in con.execute("SELECT event FROM events")]
    for e in ("revision_registered", "run_registered", "attempt_created", "training_started", "training_finished",
              "evaluated", "selection_frozen", "campaign_results"):
        assert e in events, e
    from exptrack.report import numbers

    text = numbers(root, dbp)
    assert "Development bank" in text and "Final bank 6 (wide vs ref)" in text and "acceptance" in text
    assert "wide (selected)" in text and "ref (reference)" in text
    # Rerunning is idempotent: nothing new is trained or evaluated.
    n_eval = con.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
    Campaign(root, dbp, require_snapshot_code=False).run()
    assert con.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0] == n_eval
    assert con.execute("SELECT COUNT(*) FROM run_attempts").fetchone()[0] == 2

    # A new revision: an experiment-level evaluation setting and a run-level
    # architecture setting change; the old revision and its results remain and
    # the new values reach the evaluator and the trainer.
    root2 = tmp_path / "tiny2"
    _fake_snapshot(root2, _tiny_manifest("tiny-campaign", uri, lives=2, wide=48))
    c2 = Campaign(root2, dbp, require_snapshot_code=False)
    pre2 = c2.preflight()
    assert pre2["ok"], pre2
    revs = con.execute("SELECT revision, id FROM experiment_revisions ORDER BY revision").fetchall()
    assert [r["revision"] for r in revs] == [1, 2]
    assert json.loads((root2 / "preflight_smoke" / "wide" / "arch.json").read_text())["hidden"] == 48
    assert json.loads((root2 / "preflight_smoke" / "wide" / "eval_smoke.json").read_text())["protocol"]["lives"] == 2
    lives = {r["revision"]: json.loads(r["value_json"]) for r in store.query_params(con, "experiment", "evaluation.lives")}
    assert lives == {1: 1, 2: 2}
    hidden = {r["run_id"]: json.loads(r["value_json"])
              for r in store.query_params(con, "run", "network.mlp.hidden")}
    assert sorted(hidden.values()) == [32, 32, 48, 64]
    assert con.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0] == n_eval  # old results untouched


@pytest.mark.skipif(not (REPO / "runs" / "paired-1019-v3" / "status.json").exists(),
                    reason="needs the paired-1019-v3 campaign records")
def test_historical_import_is_idempotent_and_invents_no_curves(tmp_path):
    from exptrack import db
    from exptrack.historical import import_campaign
    from exptrack.mlflow_sink import client_for
    from train_ppo import mlflow_tracking_uri

    con = db.connect(tmp_path / "h.sqlite3")
    uri = mlflow_tracking_uri()
    first = import_campaign(con, REPO / "runs" / "paired-1019-v3", uri)
    assert (first["runs"], first["evaluations"], first["mlflow_created"]) == (6, 12, 6)
    again = import_campaign(con, REPO / "runs" / "paired-1019-v3", uri)
    assert again["mlflow_created"] == 0 and again["experiment_id"] == first["experiment_id"]
    assert con.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0] == 12
    status = json.loads((REPO / "runs" / "paired-1019-v3" / "status.json").read_text())
    recorded = {(j["model_sha256"], int(s)): r["cleared"] for j in status["jobs"].values()
                for s, r in j["results"].items()}
    for e in con.execute("SELECT checkpoint_sha256, protocol_json, results_json, origin FROM evaluations"):
        assert e["origin"] == "historical_import"
        assert recorded[(e["checkpoint_sha256"], json.loads(e["protocol_json"])["seed"])] == \
            json.loads(e["results_json"])["cleared"]
    client = client_for(uri)
    runs = client.search_runs([first["mlflow_experiment_id"]], max_results=100)
    assert len(runs) == 6
    for r in runs:
        assert r.data.tags["origin"] == "historical_import"
        assert "not recorded" in r.data.tags["learning_curves"]
        assert not any(k.startswith("losses_") or k.startswith("charts_") for k in r.data.metrics)
        for k in r.data.metrics:  # single end-of-run values, no curves
            assert len(client.get_metric_history(r.info.run_id, k)) == 1


# ------------------------------------------------------------- store rules

def _registered(tmp_path):
    from exptrack import db, store

    con = db.connect(tmp_path / "s.sqlite3")
    m = _tiny_manifest("store-test", "sqlite:///unused.db")
    e = m["experiment"]
    gid = store.register_game_version(con, e["game.name"], REPO / "src" / "bubblebobblerl", e["game.source_commit"],
                                      "test")
    eid = store.register_experiment(con, "store-test", e["experiment.question"])
    rid = store.register_revision(con, eid, e, gid, "test")
    return con, e, gid, eid, rid


def _register_worker(args):
    path, rid, arm, seed = args
    import sys as _sys

    _sys.path.insert(0, str(REPO / "scripts"))
    from exptrack import db, store

    return store.register_run(db.connect(path), rid, arm, seed, phase="main")


def test_concurrent_registration_is_idempotent(tmp_path):
    import multiprocessing as mp

    con, e, gid, eid, rid = _registered(tmp_path)
    jobs = [(str(tmp_path / "s.sqlite3"), rid, arm, 11) for arm in ("ref", "wide") for _ in range(4)]
    with mp.get_context("spawn").Pool(4) as pool:
        ids = pool.map(_register_worker, jobs)
    assert len(set(ids)) == 2
    assert con.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM events WHERE event = 'run_registered'").fetchone()[0] == 2


def test_conflicting_registration_is_rejected_and_records_are_immutable(tmp_path):
    import sqlite3

    from exptrack import store

    con, e, gid, eid, rid = _registered(tmp_path)
    run = store.register_run(con, rid, "ref", 11, phase="main")
    assert store.register_run(con, rid, "ref", 11, phase="main") == run  # same thing again: same id
    store.register_run(con, rid, "wide", 11, phase="main")
    with pytest.raises(store.ConflictError):  # same identity, different configuration
        store.register_run(con, rid, "ref", 11, phase="main", run_key="phase=main/arm=wide/seed=11")
    with pytest.raises(store.ConflictError):
        store.register_experiment(con, "store-test", "a different question")
    assert store.register_revision(con, eid, e, gid, "again") == rid
    for sql in ("UPDATE runs SET arm = 'x'", "DELETE FROM runs", "UPDATE run_params SET value_json = '1'",
                "UPDATE experiment_revisions SET change_note = 'x'", "DELETE FROM events",
                "UPDATE experiment_params SET value_json = '1'"):
        with pytest.raises(sqlite3.DatabaseError):
            con.execute(sql)


def test_every_parameter_is_recorded_with_gates_and_provenance(tmp_path):
    from exptrack import schema, store

    con, e, gid, eid, rid = _registered(tmp_path)
    run = store.register_run(con, rid, "wide", 11, phase="main")
    rows = {r["key"]: r for r in con.execute("SELECT * FROM run_params WHERE run_id = ?", (run,))}
    assert {r["trainer_key"] for r in rows.values() if r["trainer_key"]} == set(schema.TRAINER_KEYS)
    for k in ("network.input_size", "network.parameter_count", "game.source_hash", "design.arm"):
        assert k in rows
    assert rows["network.mlp.hidden"]["source"] == "experiment.arm"
    assert rows["budget.wall_minutes"]["source"] == "experiment.budget"
    assert rows["init.seed"]["source"] == "run.override"
    assert rows["return.gamma"]["source"] == "experiment.shared"
    # ff12 has score_reward false: the score scale is kept but inactive, governed by score_reward
    assert rows["reward.score_scale"]["active"] == 0 and rows["reward.score_scale"]["gated_by"] == "reward.score_reward"
    assert rows["reward.clear_bonus"]["active"] == 1
    exp_rows = {r["key"] for r in con.execute("SELECT key FROM experiment_params WHERE revision_id = ?", (rid,))}
    assert set(schema.EXPERIMENT_SCHEMA) <= exp_rows
    assert "design.arm.wide.network.mlp.hidden" in exp_rows and "shared.reward.death_penalty" in exp_rows
    assert store.reconstruct_run_config(con, run)["hidden"] == 64


@pytest.mark.parametrize("hidden,layers,params", [(256, 2, 181514), (512, 2, 494090), (512, 3, 756746),
                                                   (1024, 2, 1512458)])
def test_larger_mlps_build_count_and_round_trip(tmp_path, hidden, layers, params):
    import torch

    from bubblebobblerl import BubbleBobbleEnv
    from train_ppo import Agent

    env = BubbleBobbleEnv(obs_type="ego", control_obs=True)
    a = Agent(env.observation_space, env.action_space.n, "mlp", hidden, layers, "tanh")
    assert sum(p.numel() for p in a.parameters()) == params
    path = tmp_path / "model.pt"
    torch.save(a.state_dict(), path)
    (tmp_path / "arch.json").write_text(json.dumps({"arch": "mlp", "hidden": hidden, "layers": layers, "act": "tanh",
                                                    "obs": "ego", "control_obs": True, "nearest_first": False}))
    b = Agent.load(str(path), env.observation_space, env.action_space.n, env=env)
    for (ka, va), (kb, vb) in zip(a.state_dict().items(), b.state_dict().items()):
        assert ka == kb and torch.equal(va, vb)
    x = torch.as_tensor(env.reset(seed=1, options={"level": 1})[0]).unsqueeze(0)
    assert torch.equal(a.actor(a._encode(a.obs_in(x))), b.actor(b._encode(b.obs_in(x))))


def test_budget_counts_each_reservation_once(tmp_path):
    """A job that finished training but is still evaluating counts only its
    unspent reservation (its training time is already in spent())."""
    from exptrack.campaign import Campaign

    root = tmp_path / "b"
    m = _tiny_manifest("budget-test", "sqlite:///unused.db")
    m["experiment"]["seeds.training"] = {"main": [11, 12]}
    _fake_snapshot(root, m)
    c = Campaign(root, tmp_path / "b.sqlite3", require_snapshot_code=False)
    train = c.train_reservation("main")  # 3 s + 15 s grace + 90 s per development seed
    c.status = {"jobs": {}, "parts": {"preflight": {"elapsed_seconds": 10.0}}, "final_state": "pending"}
    for i, (arm, seed) in enumerate([("ref", 11), ("wide", 11), ("ref", 12), ("wide", 12)]):
        c.status["jobs"][f"{arm}_s{seed}"] = {"state": "queued", "attempts": 0, "run_id": f"r{i}"}
    full = 10.0 + 4 * train + c.final_reservation()
    assert c.committed() == pytest.approx(full)
    j = c.status["jobs"]["ref_s11"]
    j.update(state="evaluating", attempt_id="r0-a1")
    c.status["parts"]["r0-a1/train"] = {"elapsed_seconds": 3.5}
    assert c.committed() == pytest.approx(full)  # 3.5 s moved from reservation to spent, not added twice
    j["state"] = "done"
    c.status["parts"]["r0-a1/eval/development/5"] = {"elapsed_seconds": 2.0}
    assert c.committed() == pytest.approx(full - train + 5.5)
    j2 = c.status["jobs"]["wide_s11"]
    j2.update(state="not_run")
    assert c.committed() == pytest.approx(full - 2 * train + 5.5)


# ------------------------------------------------ runner failure paths (mocked)

def _campaign_with_status(tmp_path, name="fp-test"):
    """A registered tiny campaign whose two runs each have attempt 1, and a
    status with both jobs (ids: c.ids['ref'], c.ids['wide'])."""
    from exptrack import store
    from exptrack.campaign import Campaign

    root = tmp_path / name
    _fake_snapshot(root, _tiny_manifest(name, "sqlite:///unused.db"))
    c = Campaign(root, tmp_path / f"{name}.sqlite3", require_snapshot_code=False)
    ids = c.register()
    c.ids = {}
    c.status = {"jobs": {}, "parts": {}, "final_state": "pending", "game_version_id": ids["game_version_id"]}
    for arm in ("ref", "wide"):
        run_id = ids["runs"][f"{arm}_s11"]
        store.create_attempt(c.con(), run_id, str(root / f"{arm}_s11"), "sqlite:///unused.db", "0", "m" + arm)
        c.ids[arm] = (run_id, f"{run_id}-a1")
        c.status["jobs"][f"{arm}_s11"] = {"phase": "main", "arm": arm, "seed": 11, "state": "done", "attempts": 1,
                                          "run_id": run_id, "attempt_id": f"{run_id}-a1"}
    return c, root


def test_restart_refuses_to_redispatch_a_live_orphan(tmp_path):
    import subprocess

    from exptrack.campaign import process_start

    c, root = _campaign_with_status(tmp_path)
    d = root / "ref_s11"
    d.mkdir()
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", str(d)])
    try:
        j = c.status["jobs"]["ref_s11"]
        j.update(state="running", dir=str(d), child={"pid": sleeper.pid, "start": process_start(sleeper.pid),
                                                      "kind": "train", "since": 0.0})
        before = c.committed()
        c.reconcile("ref_s11", j)
        assert j["state"] == "orphaned" and sleeper.pid in [int(x) for x in j["error"].split("[")[1].split("]")[0]
                                                            .split(",")]
        assert c.committed() == pytest.approx(before)  # full reservation still committed
        c.train_job("main", "ref", 11)  # does nothing: no second trainer for the same attempt
        assert j["state"] == "orphaned" and j["attempts"] == 1
        # Fallback identity: no recorded child, but a live process names the run directory.
        j2 = c.status["jobs"]["wide_s11"]
        j2.update(state="running", dir=str(d))
        c.reconcile("wide_s11", j2)
        assert j2["state"] == "orphaned"
    finally:
        sleeper.kill()
        sleeper.wait()


def test_restart_charges_a_dead_child_and_resumes_evaluation(tmp_path):
    import time

    from exptrack.db import sha256_file

    c, root = _campaign_with_status(tmp_path)
    d = root / "ref_s11"
    d.mkdir()
    (d / "model.pt").write_bytes(b"weights")
    gone = {"pid": 999999, "start": "Mon Jan  1 00:00:00 2001", "kind": "train", "since": time.time() - 100}
    j = c.status["jobs"]["ref_s11"]
    j.update(state="running", dir=str(d), child=dict(gone))
    c.reconcile("ref_s11", j)
    assert j["state"] == "queued" and j["retryable"] and "child" not in j
    charged = [p for k, p in c.status["parts"].items() if k.startswith(c.ids["ref"][1] + "/train/interrupted")]
    assert len(charged) == 1 and 99 <= charged[0]["elapsed_seconds"] <= 110
    j3 = c.status["jobs"]["wide_s11"]
    j3.update(state="evaluating", dir=str(d), model_sha256=sha256_file(d / "model.pt"), child={**gone, "kind": "eval"})
    c.reconcile("wide_s11", j3)
    assert j3["state"] == "evaluating" and j3["resume_evaluation"]  # endpoint verified: evaluate, do not retrain
    assert any(k.startswith(c.ids["wide"][1] + "/eval/interrupted") for k in c.status["parts"])


def test_evaluation_retry_is_budgeted_and_keeps_each_try(tmp_path):
    c, root = _campaign_with_status(tmp_path)
    d = root / "ref_s11"
    d.mkdir()
    j = c.status["jobs"]["ref_s11"]
    j.update(state="evaluating", dir=str(d), mlflow_run_id="m", model_sha256="x", steps=1)
    calls = []

    def fake(run_id, attempt_id, ml_run, model, sha, eff, role, seed, out, step, try_n=1, job=None):
        calls.append((out.name, try_n))
        return None if try_n == 1 else {"cleared": 1}

    c.evaluate = fake
    assert c.evaluate_with_retry(j, "final", 6, {}, d / "eval_final_6.json") == {"cleared": 1}
    assert calls == [("eval_final_6.json", 1), ("eval_final_6.try2.json", 2)]
    calls.clear()
    c.cap_seconds = 0.0  # no budget left: the retry is refused, not run
    assert c.evaluate_with_retry(j, "final", 6, {}, d / "eval_final_6.json") is None
    assert calls == [("eval_final_6.json", 1)]


def test_preflight_is_bounded_by_the_remaining_allowance(tmp_path, monkeypatch):
    from exptrack import campaign
    from exptrack.campaign import Campaign, SystemicError
    from train_ppo import mlflow_tracking_uri

    root = tmp_path / "pf"
    _fake_snapshot(root, _tiny_manifest("pf-test", mlflow_tracking_uri()))
    monkeypatch.setattr(campaign, "PREFLIGHT_RESERVE_SECONDS", 0.5)
    c = Campaign(root, tmp_path / "pf.sqlite3", require_snapshot_code=False)
    with pytest.raises(SystemicError):
        c.preflight()
    parts = json.loads((root / "status.json").read_text())["parts"]
    cost = [p["elapsed_seconds"] for k, p in parts.items() if k.startswith("preflight/")]
    assert len(cost) == 1 and 0.4 <= cost[0] <= 5  # recorded although the subprocess was cut off


def test_live_final_bank_evaluator_blocks_final_dispatch(tmp_path):
    """A done job whose final-bank evaluator from a previous runner is still
    alive: no second evaluator, no retraining, until it is gone."""
    import subprocess

    from exptrack.campaign import process_start

    c, root = _campaign_with_status(tmp_path)
    ids = c.register()
    c.status.update(experiment_id=ids["experiment_id"], revision_id=ids["revision_id"])
    for arm in ("ref", "wide"):
        j = c.status["jobs"][f"{arm}_s11"]
        d = root / f"{arm}_s11"
        d.mkdir(exist_ok=True)
        j.update(dir=str(d), model_sha256=f"sha-{arm}", steps=1, mlflow_run_id="m", development={"5": 1})
    (root / "selection.json").write_text(json.dumps({
        "selected_arm": "wide", "reference_arm": "ref", "checkpoints": {"wide": {"11": "sha-wide"},
                                                                         "ref": {"11": "sha-ref"}},
        "development": {}, "frozen": "t"}))
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)",
                                str(root / "wide_s11" / "eval_final_6.json")])
    calls = []
    c.evaluate_with_retry = lambda j, role, seed, eff, out: calls.append((j["arm"], role)) or None
    try:
        jw = c.status["jobs"]["wide_s11"]
        jw["child"] = {"pid": sleeper.pid, "start": process_start(sleeper.pid), "kind": "eval", "since": 0.0}
        c.reconcile_all()
        assert jw["state"] == "done" and jw["orphan_child"]["pids"] == [sleeper.pid]
        c.select_and_finalize()
        assert calls == [] and c.status["final_state"] == "pending"  # blocked: nothing dispatched
    finally:
        sleeper.kill()
        sleeper.wait()
    with pytest.raises(Exception):  # unblocked now: dispatch proceeds (the stub's None result is refused)
        c.select_and_finalize()
    assert calls and "orphan_child" not in jw and jw["state"] == "done"
    assert any("/eval/interrupted" in k for k in c.status["parts"])  # the dead evaluator's time is charged


def test_concurrent_retries_cannot_share_one_allowance(tmp_path):
    import threading
    import time

    c, root = _campaign_with_status(tmp_path)
    barrier = threading.Barrier(2)
    second_tries = []

    def fake(run_id, attempt_id, ml_run, model, sha, eff, role, seed, out, step, try_n=1, job=None):
        if try_n == 1:
            barrier.wait()  # both first tries fail together, so both retries race
            return None
        second_tries.append(seed)
        time.sleep(0.3)  # hold the reservation while the other retry checks
        return {"cleared": 1}

    c.evaluate = fake
    for arm in ("ref", "wide"):
        c.status["jobs"][f"{arm}_s11"].update(dir=str(root), mlflow_run_id="m", model_sha256="x", steps=1)
    c.cap_seconds = c.committed() + c.eval_hard + 1.0  # room for exactly one extra evaluation
    results = {}
    threads = [threading.Thread(target=lambda a=a, s=s: results.__setitem__(a, c.evaluate_with_retry(
        c.status["jobs"][f"{a}_s11"], "final", s, {}, root / f"eval_{a}.json"))) for a, s in (("ref", 6), ("wide", 7))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(second_tries) == 1 and sorted(v is None for v in results.values()) == [False, True]
    assert c.status.get("retry_reservations", {}) == {}  # released after the try


def test_child_cost_survives_the_clear_boundary_exactly_once(tmp_path):
    import time

    from exptrack import store

    c, root = _campaign_with_status(tmp_path)
    j = c.status["jobs"]["ref_s11"]
    j.update(state="running", dir=str(root / "ref_s11"))
    (root / "ref_s11").mkdir()
    rc, secs = c.run_child(j, "train", [sys.executable, "-c", "pass"], root / "o.txt", root / "e.txt", 30,
                           f"{j['attempt_id']}/train")
    saved = json.loads((root / "status.json").read_text())
    assert rc == 0 and "child" not in saved["jobs"]["ref_s11"]  # cleared and charged in the same write
    assert saved["parts"][f"{j['attempt_id']}/train"]["elapsed_seconds"] == secs
    # Interrupted before that write: the child record survives, so the time is charged once on restart.
    jw = c.status["jobs"]["wide_s11"]
    jw.update(state="running", dir=str(root / "wide_s11"),
              child={"pid": 999999, "start": "gone", "kind": "train", "since": time.time() - 50})
    c.reconcile_all()
    c.reconcile_all()
    charged = [p for k, p in c.status["parts"].items() if k.startswith(jw["attempt_id"] + "/train/interrupted")]
    assert len(charged) == 1 and 49 <= charged[0]["elapsed_seconds"] <= 60
    # Neither record nor cost survived for a launched attempt: refuse recovery, keep the reservation.
    j.update(state="running")
    c.status["parts"].pop(f"{j['attempt_id']}/train")
    store.add_event(c.con(), "training_started", {}, run_id=j["run_id"], attempt_id=j["attempt_id"])
    before = c.committed()
    c.reconcile_all()
    assert j["state"] == "needs_review" and c.committed() >= before
    c.train_job("main", "ref", 11)
    assert j["state"] == "needs_review" and j["attempts"] == 1


def test_run_directory_matching_is_whole_path(tmp_path):
    import subprocess

    from exptrack.campaign import live_processes_mentioning

    a, b = tmp_path / "ref_s11", tmp_path / "ref_s11_a2"
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", str(b / "model.pt")])
    try:
        assert p.pid in live_processes_mentioning(b)
        assert p.pid not in live_processes_mentioning(a)
    finally:
        p.kill()
        p.wait()
