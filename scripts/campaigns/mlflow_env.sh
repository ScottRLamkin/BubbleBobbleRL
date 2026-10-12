# Source this before launching several runs at once. Several processes
# logging straight into the SQLite file collide, so runs log through a
# server: the `mlflow ui` on port 5000 if you have one open, otherwise a
# server this starts on port 5002 and stops when the script exits.
export MLFLOW_DISABLE_AGENT_HINT=1 MLFLOW_DISABLE_TELEMETRY=true
if curl -sf http://127.0.0.1:5000/health > /dev/null; then
  export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
else
  uv run mlflow server --backend-store-uri sqlite:///mlflow.db --default-artifact-root ./mlruns \
      --host 127.0.0.1 --port 5002 --workers 1 > runs/mlflow_server_5002.log 2>&1 &
  MLFLOW_SERVER_PID=$!
  until curl -sf http://127.0.0.1:5002/health > /dev/null; do sleep 1; done
  export MLFLOW_TRACKING_URI=http://127.0.0.1:5002
  trap 'kill $MLFLOW_SERVER_PID' EXIT
fi
