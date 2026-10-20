"""Test-session MLflow store.

MLflow tracking is mandatory in the trainer, so tests log to a throwaway SQLite
tracking store created for the session, never to the project's service on :5000
or its mlflow.db. Subprocesses inherit the environment variable.
"""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def mlflow_test_store(tmp_path_factory):
    path = tmp_path_factory.mktemp("mlflow") / "mlflow.db"
    old = os.environ.get("MLFLOW_TRACKING_URI")
    os.environ["MLFLOW_TRACKING_URI"] = f"sqlite:///{path}"
    yield os.environ["MLFLOW_TRACKING_URI"]
    if old is None:
        os.environ.pop("MLFLOW_TRACKING_URI", None)
    else:
        os.environ["MLFLOW_TRACKING_URI"] = old
