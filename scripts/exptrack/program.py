"""A registered multi-batch search program: one frozen snapshot, several
search-only batches run in a fixed order, then one joint ranking.

    python scripts/run_hyperparameter_search.py snapshot --root runs/<program> --manifest scripts/campaigns/<program>.json
    PYTHONPATH=runs/<program>/snapshot/src:runs/<program>/snapshot/scripts .venv/bin/python -m exptrack \\
        program register|preflight|run --root runs/<program> --db experiments.sqlite3

The program manifest names the frozen design (path and sha256), the batches in
order (each a complete search_batch experiment manifest inside the same
snapshot), the joint ranking rule and the budget. Each batch gets its own root
<program>/<batch id>/ whose `snapshot` is a symlink to the program snapshot and
whose snapshot.json names that batch's manifest, so the ordinary campaign
runner (scripts/exptrack/campaign.py, search_batch mode) runs it: training and
development evaluation only, no selection, no final bank.

`register` registers every batch (all configurations and runs) before anything
trains, plus a program event linking the design hash to each batch's
experiment and revision. `run` holds an exclusive program lock, runs the
batches in order (a finished batch is skipped, so a restart resumes without
duplicates), checks the program and extension budgets before each batch, and
ranks jointly only when every job of every batch is done.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

from . import db, store
from .campaign import Campaign, iso, write_json_atomic


class Program:
    def __init__(self, root, db_path, require_snapshot_code: bool = True):
        self.root = Path(root).resolve()
        self.snap = self.root / "snapshot"
        self.db_path = Path(db_path).resolve()
        self.require = require_snapshot_code
        if require_snapshot_code and not Path(__file__).resolve().is_relative_to(self.snap.resolve()):
            raise SystemExit(f"run me from the program snapshot ({self.snap})")
        self.info = json.loads((self.root / "snapshot.json").read_text())
        changed = [r for r, h in self.info["files"].items() if db.sha256_file(self.snap / r) != h]
        if changed:
            raise SystemExit(f"program snapshot changed since it was frozen: {changed[:5]}")
        mpath = self.snap / self.info["manifest"]
        if db.sha256_file(mpath) != self.info["manifest_sha256"]:
            raise SystemExit("program manifest hash differs from snapshot.json")
        self.manifest = json.loads(mpath.read_text())
        dpath = self.snap / self.manifest["design_path"]
        if db.sha256_file(dpath) != self.manifest["design_sha256"]:
            raise SystemExit("design file hash differs from the program manifest")
        self.design = json.loads(dpath.read_text())
        self.con = db.connect(self.db_path)

    # -------------------------------------------------------------- batches
    def batch_root(self, batch: dict) -> Path:
        """<program>/<batch id> with `snapshot` -> ../snapshot and a snapshot.json naming the batch manifest."""
        broot = self.root / batch["id"]
        broot.mkdir(exist_ok=True)
        link = broot / "snapshot"
        if not link.exists():
            link.symlink_to(Path("..") / "snapshot")
        if link.resolve() != self.snap.resolve():
            raise SystemExit(f"{link} does not point at the program snapshot")
        info = {**self.info, "campaign": batch["id"], "manifest": batch["manifest"],
                "manifest_sha256": db.sha256_file(self.snap / batch["manifest"]), "program": self.manifest["program_id"],
                "program_manifest": self.info["manifest"], "program_manifest_sha256": self.info["manifest_sha256"]}
        sj = broot / "snapshot.json"
        if sj.exists():
            if json.loads(sj.read_text()) != info:
                raise SystemExit(f"{sj} differs from the program snapshot record")
        else:
            write_json_atomic(sj, info)
        return broot

    def campaign(self, batch: dict) -> Campaign:
        return Campaign(self.batch_root(batch), self.db_path, require_snapshot_code=self.require)

    def batch_done(self, batch: dict) -> bool:
        return (self.root / batch["id"] / "batch_results.json").exists()

    # --------------------------------------------------------- registration
    def register(self) -> dict:
        ids = {}
        for b in self.manifest["batches"]:
            r = self.campaign(b).register()
            ids[b["id"]] = {"experiment_id": r["experiment_id"], "revision_id": r["revision_id"],
                            "runs": len(r["runs"])}
        detail = {"program_id": self.manifest["program_id"], "design_sha256": self.manifest["design_sha256"],
                  "program_manifest_sha256": self.info["manifest_sha256"], "snapshot_commit": self.info["commit"],
                  "batches": ids, "ranking": self.manifest["ranking"], "confirmation": self.manifest["confirmation"],
                  "budget": self.manifest["budget"]}
        if not self.con.execute("SELECT 1 FROM events WHERE event = 'program_registered' AND detail_json LIKE ?",
                                (f'%"program_manifest_sha256":"{self.info["manifest_sha256"]}"%',)).fetchone():
            store.add_event(self.con, "program_registered", detail)
            path = self.snap / self.manifest["design_path"]
            store.add_artifact(self.con, "program_design", path, self.manifest["design_sha256"],
                               note=f"{self.manifest['program_id']} frozen design")
        return detail

    def preflight(self) -> dict:
        reports = {}
        for b in self.manifest["batches"]:
            r = self.campaign(b).preflight()
            reports[b["id"]] = {"ok": r["ok"], "core_minutes": r["preflight_core_minutes"],
                                "arms": {a: {k: v[k] for k in ("ok", "parameter_count", "seconds_per_update")}
                                         for a, v in r["arms"].items()}}
        out = {"ok": all(r["ok"] for r in reports.values()), "batches": reports, "written": iso()}
        write_json_atomic(self.root / "preflight.json", out)
        return out

    # ------------------------------------------------------------- budget
    def batch_spent(self, batch: dict) -> float:
        sp = self.root / batch["id"] / "status.json"
        if not sp.exists():
            return 0.0
        return sum(p.get("elapsed_seconds", 0.0) for p in json.loads(sp.read_text())["parts"].values()) / 3600

    def program_spent(self) -> float:
        return sum(self.batch_spent(b) for b in self.manifest["batches"])

    def check_budget(self, batch: dict) -> str | None:
        """Committed program cost: a finished batch counts what it spent; an
        unfinished one counts the larger of its cap and what it has spent (its
        cap already includes its own preflight); plus the confirmation cap. It
        must fit the program cap and, with earlier use, the extension allowance.
        (Before 2026-10-20 06:58 this added spent preflight time on top of the
        full caps and refused batch 1 by 0.02 core-hours.)"""
        bud = self.manifest["budget"]
        need = bud["confirmation_cap_core_hours"]
        for b in self.manifest["batches"]:
            spent = self.batch_spent(b)
            need += spent if self.batch_done(b) else max(bud["batch_cap_core_hours"], spent)
        if need > bud["program_cap_core_hours"] + 1e-9:
            return f"program cap: {need:.2f} > {bud['program_cap_core_hours']}"
        if need + bud["extension_used_before_program_core_hours"] > bud["extension_core_hours"] + 1e-9:
            return f"extension allowance: {need + bud['extension_used_before_program_core_hours']:.2f} > " \
                   f"{bud['extension_core_hours']}"
        return None

    # ---------------------------------------------------------------- run
    def run(self) -> None:
        lock = open(self.root / "program.lock", "a+")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another program runner holds program.lock")
        lock.seek(0)
        lock.truncate()
        lock.write(f"{os.getpid()} {iso()}\n")
        lock.flush()
        self.register()
        log = self.root / "program.log"
        for b in self.manifest["batches"]:
            if self.batch_done(b):
                continue
            reason = self.check_budget(b)
            if reason:
                self._log(log, f"batch {b['id']} not started: {reason}")
                store.add_event(self.con, "program_stopped", {"batch": b["id"], "reason": reason})
                return
            self._log(log, f"batch {b['id']} start (program spent {self.program_spent():.2f} core-hours)")
            self.campaign(b).run()
            if not self.batch_done(b):
                self._log(log, f"batch {b['id']} incomplete; program stopped before ranking")
                store.add_event(self.con, "program_stopped", {"batch": b["id"], "reason": "batch incomplete"})
                return
            self._log(log, f"batch {b['id']} complete (program spent {self.program_spent():.2f} core-hours)")
        self.rank()

    @staticmethod
    def _log(path: Path, msg: str) -> None:
        line = f"{iso()} {msg}"
        print(line, flush=True)
        with open(path, "a") as f:
            f.write(line + "\n")

    def rank(self) -> dict:
        """Joint ranking over every arm of every batch, by the registered rule:
        absolute completed fraction (all seeds and development banks pooled),
        then the minimum training-seed fraction, then arm id."""
        path = self.root / "ranking.json"
        if path.exists():
            return json.loads(path.read_text())
        arms = {}
        for b in self.manifest["batches"]:
            res = json.loads((self.root / b["id"] / "batch_results.json").read_text())
            for a, v in res["arms"].items():
                arms[a] = {**v, "batch": b["id"]}
        expected = [a["id"] for a in self.design["design"]["arms"]]
        if sorted(arms) != sorted(expected):
            raise SystemExit(f"ranking needs every designed arm; have {sorted(arms)}")
        order = sorted(arms, key=lambda a: (-arms[a]["fraction"], -arms[a]["min_seed_fraction"], a))
        ref = self.manifest["ranking"]["reference"]
        selected = next(a for a in order if a != ref)
        out = {"program_id": self.manifest["program_id"], "design_sha256": self.manifest["design_sha256"],
               "rule": self.manifest["ranking"], "order": order, "selected": selected, "reference": ref,
               "selected_overrides": arms[selected]["overrides"],
               "arms": {a: {k: arms[a][k] for k in ("batch", "overrides", "cleared", "episodes", "fraction",
                                                     "min_seed_fraction", "runs")} for a in order},
               "frozen": iso()}
        write_json_atomic(path, out)
        store.add_artifact(self.con, "program_ranking", path, db.sha256_file(path))
        store.add_event(self.con, "program_ranking_frozen", {"selected": selected, "order": order,
                                                             "design_sha256": self.manifest["design_sha256"]})
        self._log(self.root / "program.log", f"ranking frozen: selected {selected}; order {order}")
        return out
