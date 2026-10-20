"""MLflow for learning metrics. Tracking is mandatory and cannot be turned off.

There is no switch to disable MLflow anywhere in the training path. Every
failure to reach the configured service is a hard error:

- before training: the service must answer a preflight, and the run must be
  created (or the dispatcher-created run found) and linked, or nothing starts;
- during training: each metric upload is retried for about half a minute
  (RETRY_SECONDS) and then raises TrackingUnavailable, which stops training;
- at the end: the run is only reported finished when every metric event has
  been uploaded and the run has been marked terminated.

Every metric event is first appended to a local JSONL outbox (flushed and
fsynced) and then uploaded with MlflowClient.log_batch. A watermark file records
the last uploaded sequence number and only advances after a successful upload.
This is crash consistency, not an outage mode: after a hard failure the events
recorded up to the failure are still on disk and `exptrack sync` replays them
to the SAME run. Timestamps are fixed when an event is created, so a replay
after an ambiguous failure resends identical (key, value, timestamp, step) rows,
which MLflow's store ignores instead of duplicating.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")

MAX_BATCH = 500  # MLflow accepts up to 1000 metrics per log_batch call
RETRY_SECONDS = (1, 2, 4, 8, 15)  # waits between upload attempts before a hard failure (~30 s)
DEFAULT_SERVICE = "http://127.0.0.1:5000"  # the project's `mlflow ui` (backed by mlflow.db)


class TrackingUnavailable(RuntimeError):
    """The configured MLflow service cannot be reached for a required step."""


def resolve_uri(explicit: str | None = None) -> str:
    """The tracking service: an explicit URI, else $MLFLOW_TRACKING_URI, else the
    local service on :5000. There is no fallback when that service is down;
    preflight() then fails."""
    return explicit or os.environ.get("MLFLOW_TRACKING_URI") or DEFAULT_SERVICE


def client_for(tracking_uri: str):
    from mlflow.tracking import MlflowClient

    return MlflowClient(tracking_uri=tracking_uri)


def preflight(tracking_uri: str, timeout: float = 3.0) -> None:
    """Raise TrackingUnavailable unless the service answers (http) or the store
    opens (sqlite/file)."""
    if tracking_uri.startswith(("http://", "https://")):
        import urllib.request

        try:
            with urllib.request.urlopen(tracking_uri.rstrip("/") + "/health", timeout=timeout) as r:
                if r.status != 200:
                    raise TrackingUnavailable(f"{tracking_uri}/health returned {r.status}")
        except TrackingUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TrackingUnavailable(f"MLflow service {tracking_uri} is not reachable: {exc}") from exc
    else:
        try:
            client_for(tracking_uri).search_experiments(max_results=1)
        except Exception as exc:  # noqa: BLE001
            raise TrackingUnavailable(f"MLflow store {tracking_uri} cannot be opened: {exc}") from exc


def ensure_experiment(client, name: str) -> str:
    """Experiment id for `name`, creating it if needed (tolerates a concurrent create)."""
    for _ in range(5):
        exp = client.get_experiment_by_name(name)
        if exp is not None:
            return exp.experiment_id
        try:
            return client.create_experiment(name)
        except Exception:  # noqa: BLE001  another process created it first
            time.sleep(0.2)
    raise TrackingUnavailable(f"could not create or find MLflow experiment {name!r}")


def find_run_by_tag(client, experiment_id: str, key: str, value: str):
    runs = client.search_runs([experiment_id], filter_string=f"tags.`{key}` = '{value}'", max_results=2)
    if len(runs) > 1:
        raise RuntimeError(f"more than one MLflow run has {key}={value}")
    return runs[0] if runs else None


class MetricOutbox:
    """Append-only JSONL of metric events plus an atomically replaced watermark."""

    def __init__(self, path):
        self.path = Path(path)
        self.mark_path = self.path.with_suffix(self.path.suffix + ".sent")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._next = self._count()

    def _count(self) -> int:
        n = 0
        with open(self.path) as f:
            for line in f:
                if line.strip():
                    n = json.loads(line)["seq"]
        return n

    def append(self, events: list[dict]) -> None:
        with open(self.path, "a") as f:
            for e in events:
                self._next += 1
                f.write(json.dumps({**e, "seq": self._next}) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def sent(self) -> int:
        return int(self.mark_path.read_text()) if self.mark_path.exists() else 0

    def mark_sent(self, seq: int) -> None:
        tmp = self.mark_path.with_name(self.mark_path.name + ".tmp")
        tmp.write_text(str(seq))
        os.replace(tmp, self.mark_path)

    def pending(self) -> list[dict]:
        done = self.sent()
        out = []
        with open(self.path) as f:
            for line in f:
                if line.strip():
                    e = json.loads(line)
                    if e["seq"] > done:
                        out.append(e)
        return out


class TrackedRun:
    """Metric logging for one existing MLflow run through a durable outbox."""

    def __init__(self, tracking_uri: str, run_id: str, outbox_path, client=None, sleep=time.sleep):
        self.tracking_uri = tracking_uri
        self.run_id = run_id
        self.outbox = MetricOutbox(outbox_path)
        self.client = client or client_for(tracking_uri)
        self.last_error: str | None = None
        self._sleep = sleep

    @staticmethod
    def create(tracking_uri: str, experiment: str, run_name: str, tags: dict, params: dict, outbox_path,
               client=None) -> "TrackedRun":
        """Create and link a new run; raises TrackingUnavailable if that fails."""
        preflight(tracking_uri)
        client = client or client_for(tracking_uri)
        try:
            exp_id = ensure_experiment(client, experiment)
            run = client.create_run(exp_id, run_name=run_name, tags={k: str(v) for k, v in tags.items()})
            log_params(client, run.info.run_id, params)
        except TrackingUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TrackingUnavailable(f"could not create the MLflow run: {exc}") from exc
        return TrackedRun(tracking_uri, run.info.run_id, outbox_path, client=client)

    @staticmethod
    def attach(tracking_uri: str, run_id: str, outbox_path, client=None) -> "TrackedRun":
        """Link to a run the dispatcher created; raises TrackingUnavailable unless
        the service answers and the run exists and is still open."""
        preflight(tracking_uri)
        client = client or client_for(tracking_uri)
        try:
            run = client.get_run(run_id)
        except Exception as exc:  # noqa: BLE001
            raise TrackingUnavailable(f"MLflow run {run_id} not found at {tracking_uri}: {exc}") from exc
        if run.info.status != "RUNNING":
            raise TrackingUnavailable(f"MLflow run {run_id} is {run.info.status}, not RUNNING")
        return TrackedRun(tracking_uri, run_id, outbox_path, client=client)

    def log_metrics(self, metrics: dict, step: int) -> None:
        ts = int(time.time() * 1000)
        events = [{"key": k.replace("/", "_"), "value": float(v), "step": int(step), "timestamp": ts}
                  for k, v in metrics.items() if v == v]  # NaN cannot be stored; it is not a measurement
        self.outbox.append(events)
        self.flush()

    def _upload(self) -> None:
        from mlflow.entities import Metric

        pending = self.outbox.pending()
        for i in range(0, len(pending), MAX_BATCH):
            chunk = pending[i:i + MAX_BATCH]
            self.client.log_batch(self.run_id, metrics=[
                Metric(e["key"], e["value"], e["timestamp"], e["step"]) for e in chunk])
            self.outbox.mark_sent(chunk[-1]["seq"])

    def flush(self) -> None:
        """Upload every pending event, retrying for RETRY_SECONDS; raises
        TrackingUnavailable if the service stays unreachable."""
        for wait in (0, *RETRY_SECONDS):
            if wait:
                self._sleep(wait)
            try:
                self._upload()
                self.last_error = None
                return
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{type(exc).__name__}: {exc}"
        raise TrackingUnavailable(
            f"MLflow at {self.tracking_uri} rejected or did not answer metric uploads for run {self.run_id} "
            f"for {sum(RETRY_SECONDS)} s ({self.last_error}); {len(self.outbox.pending())} events are kept in "
            f"{self.outbox.path} for `exptrack sync`")

    def status(self) -> dict:
        return {"run_id": self.run_id, "tracking_uri": self.tracking_uri, "pending": len(self.outbox.pending()),
                "sent_seq": self.outbox.sent(), "last_error": self.last_error}

    def finish(self, status: str = "FINISHED") -> dict:
        """Upload everything, then mark the run terminated; raises
        TrackingUnavailable if either step fails."""
        self.flush()
        try:
            self.client.set_terminated(self.run_id, status)
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"set_terminated: {exc}"
            raise TrackingUnavailable(f"could not mark MLflow run {self.run_id} {status}: {exc}") from exc
        return {**self.status(), "terminated": status}

    def abort(self) -> dict:
        """After a failure: one attempt to upload what is pending and mark the run
        FAILED. Never raises (the original error is what matters); the result
        says what was achieved."""
        state = {"terminated": None}
        try:
            self._upload()
            self.client.set_terminated(self.run_id, "FAILED")
            state["terminated"] = "FAILED"
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"{type(exc).__name__}: {exc}"
        return {**self.status(), **state}


def log_params(client, run_id: str, params: dict) -> None:
    """Mirror parameters (MLflow takes at most 100 per batch; values are strings)."""
    from mlflow.entities import Param

    items = [Param(k, json.dumps(v) if not isinstance(v, str) else v) for k, v in sorted(params.items())]
    for i in range(0, len(items), 100):
        client.log_batch(run_id, params=items[i:i + 100])


def replay(tracking_uri: str, run_id: str, outbox_path, client=None) -> int:
    """Upload whatever an outbox still holds to its run (after a hard failure);
    returns the number of events sent. Raises TrackingUnavailable on failure."""
    preflight(tracking_uri)
    run = TrackedRun(tracking_uri, run_id, outbox_path, client=client)
    n = len(run.outbox.pending())
    if n:
        run.flush()
    return n
