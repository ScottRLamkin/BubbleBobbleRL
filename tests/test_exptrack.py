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
