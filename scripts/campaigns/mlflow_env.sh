# Source this before launching several runs at once. Several processes
# logging straight into the SQLite file collide, so campaigns log through a
# server of their own on port 5002 (your `mlflow ui` on 5000 stays a reader
# of the same mlflow.db). Also starts a memory watchdog that stops training
# processes before the machine swaps itself to death.
export MLFLOW_DISABLE_AGENT_HINT=1 MLFLOW_DISABLE_TELEMETRY=true
uv run mlflow server --backend-store-uri sqlite:///mlflow.db --default-artifact-root ./mlruns \
    --host 127.0.0.1 --port 5002 --workers 1 > runs/mlflow_server_5002.log 2>&1 &
MLFLOW_SERVER_PID=$!
disown $MLFLOW_SERVER_PID 2>/dev/null  # so a campaign's `wait` only waits for its training jobs
until curl -sf http://127.0.0.1:5002/health > /dev/null; do sleep 1; done
export MLFLOW_TRACKING_URI=http://127.0.0.1:5002
zsh scripts/campaigns/memwatch.sh > runs/memwatch.log 2>&1 &
MEMWATCH_PID=$!
disown $MEMWATCH_PID 2>/dev/null
trap 'kill $MLFLOW_SERVER_PID $MEMWATCH_PID 2>/dev/null' EXIT
