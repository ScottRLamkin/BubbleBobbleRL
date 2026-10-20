"""Experiment tracking command line.

    PYTHONPATH=scripts .venv/bin/python -m exptrack init
    PYTHONPATH=scripts .venv/bin/python -m exptrack show [--experiment NAME] [--run RUN_ID]
    PYTHONPATH=scripts .venv/bin/python -m exptrack params run network.mlp.hidden
    PYTHONPATH=scripts .venv/bin/python -m exptrack sync RUN_DIR
    PYTHONPATH=scripts .venv/bin/python -m exptrack import-historical runs/hparam-1019 runs/hparam-1019-v2 ...
    PYTHONPATH=<root>/snapshot/src:<root>/snapshot/scripts .venv/bin/python -m exptrack \\
        campaign preflight|run --root runs/<id> --db experiments.sqlite3

`--db` defaults to experiments.sqlite3 at the repository root, except for
campaign commands, which run from a frozen snapshot and must name it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import db, store


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="exptrack", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init", help="create or migrate the store")
    s.add_argument("--db", default=str(db.DEFAULT_DB))
    s = sub.add_parser("show", help="experiments, revisions and runs")
    s.add_argument("--db", default=str(db.DEFAULT_DB))
    s.add_argument("--experiment")
    s.add_argument("--run")
    s = sub.add_parser("params", help="one namespaced parameter across runs or revisions")
    s.add_argument("level", choices=["run", "experiment"])
    s.add_argument("key")
    s.add_argument("--db", default=str(db.DEFAULT_DB))
    s = sub.add_parser("sync", help="replay a run directory's metric outbox to its MLflow run")
    s.add_argument("run_dir")
    s.add_argument("--db", default=str(db.DEFAULT_DB))
    s = sub.add_parser("import-historical", help="import completed campaigns from their own records")
    s.add_argument("roots", nargs="+")
    s.add_argument("--db", default=str(db.DEFAULT_DB))
    s.add_argument("--mlflow-uri", default=None, help="default: $MLFLOW_TRACKING_URI, else the service on :5000")
    s = sub.add_parser("program", help="registered multi-batch search program (run from its snapshot)")
    s.add_argument("action", choices=["register", "preflight", "run", "rank"])
    s.add_argument("--root", required=True)
    s.add_argument("--db", required=True)
    s = sub.add_parser("campaign", help="registered campaign (run from its snapshot)")
    s.add_argument("action", choices=["register", "preflight", "run"])
    s.add_argument("--root", required=True)
    s.add_argument("--db", required=True)
    a = p.parse_args(argv)

    if a.cmd == "init":
        con = db.connect(a.db)
        print(f"{a.db}: migrations {[r['name'] for r in con.execute('SELECT name FROM schema_migrations')]}")
    elif a.cmd == "show":
        show(db.connect(a.db), a.experiment, a.run)
    elif a.cmd == "params":
        for r in store.query_params(db.connect(a.db), a.level, a.key):
            d = dict(r)
            print(json.dumps({k: d[k] for k in d if k not in ("revision_id",)}))
    elif a.cmd == "sync":
        from .mlflow_sink import replay

        con = db.connect(a.db)
        d = Path(a.run_dir).resolve()
        row = con.execute("SELECT * FROM run_attempts WHERE run_dir = ?", (str(d),)).fetchone()
        if row is None:
            raise SystemExit(f"no attempt is registered for {d}")
        n = replay(row["mlflow_tracking_uri"], row["mlflow_run_id"], d / "mlflow_outbox.jsonl")
        store.add_event(con, "metrics_replayed", {"events": n}, run_id=row["run_id"], attempt_id=row["id"])
        print(f"replayed {n} metric events to {row['mlflow_run_id']}")
    elif a.cmd == "import-historical":
        from .historical import import_campaign
        from .mlflow_sink import resolve_uri

        con = db.connect(a.db)
        for root in a.roots:
            print(root, json.dumps(import_campaign(con, root, resolve_uri(a.mlflow_uri))))
    elif a.cmd == "program":
        from .program import Program

        pr = Program(a.root, a.db)
        if a.action == "register":
            print(json.dumps(pr.register(), indent=1))
        elif a.action == "preflight":
            r = pr.preflight()
            print(json.dumps(r, indent=1))
            if not r["ok"]:
                raise SystemExit("preflight failed")
        elif a.action == "rank":
            print(json.dumps({k: v for k, v in pr.rank().items() if k != "arms"}, indent=1))
        else:
            pr.run()
    elif a.cmd == "campaign":
        from .campaign import Campaign

        c = Campaign(a.root, a.db)
        if a.action == "register":
            print(json.dumps(c.register(), indent=1))
        elif a.action == "preflight":
            r = c.preflight()
            print(json.dumps(r, indent=1))
            if not r["ok"]:
                raise SystemExit("preflight failed")
        else:
            c.run()


def show(con, experiment: str | None, run_id: str | None) -> None:
    if run_id:
        run = con.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        print(json.dumps({k: run[k] for k in run.keys() if k != "config_json"}, indent=1))
        for r in con.execute("SELECT key, value_json, unit, active, gated_by, source FROM run_params WHERE run_id = ? "
                             "ORDER BY key", (run_id,)):
            gate = "" if r["active"] else f"  (inactive: {r['gated_by']})"
            print(f"  {r['key']:38} {r['value_json']:>24}  [{r['source']}]{gate}")
        for r in con.execute("SELECT * FROM run_attempts WHERE run_id = ?", (run_id,)):
            print(f"  attempt {r['attempt']}: {r['run_dir']} mlflow {r['mlflow_run_id']}")
        for r in con.execute("SELECT id, role, results_json FROM evaluations WHERE run_id = ?", (run_id,)):
            res = json.loads(r["results_json"])
            print(f"  evaluation {r['id']} {r['role']}: cleared {res['cleared']}/{res['episodes']}")
        return
    q = "SELECT * FROM experiments" + (" WHERE name = ?" if experiment else "") + " ORDER BY created_at"
    for e in con.execute(q, (experiment,) if experiment else ()):
        print(f"{e['name']} [{e['id']}] ({e['origin']}): {e['question']}")
        for v in con.execute("SELECT * FROM experiment_revisions WHERE experiment_id = ? ORDER BY revision", (e["id"],)):
            n = con.execute("SELECT COUNT(*) FROM runs WHERE revision_id = ?", (v["id"],)).fetchone()[0]
            print(f"  revision {v['revision']} [{v['id']}] {n} runs; {v['change_note']}")
            if experiment:
                for r in con.execute("SELECT id, run_key FROM runs WHERE revision_id = ? ORDER BY run_key", (v["id"],)):
                    print(f"    {r['run_key']:44} {r['id']}  {store.run_state(con, r['id'])}")


if __name__ == "__main__":
    main()
