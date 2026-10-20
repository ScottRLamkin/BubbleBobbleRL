"""Numbers section of a tracked campaign's results report.

    PYTHONPATH=scripts .venv/bin/python -m exptrack.report runs/capacity-1020 > /tmp/numbers.md

Everything comes from the campaign's results.json, selection.json and
status.json, the SQLite store (identities, parameter counts) and MLflow
(learning diagnostics averaged over the last 10% of each run's logged steps).
Interpretation is written by hand around it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import db

DIAG = ("losses_entropy", "losses_approx_kl", "losses_clipfrac", "losses_explained_variance", "charts_sps",
        "charts_train_clear_rate", "charts_train_death_rate", "charts_episodic_return")


def tail_mean(client, run_id: str, key: str, frac: float = 0.1) -> float | None:
    h = client.get_metric_history(run_id, key)
    if not h:
        return None
    h.sort(key=lambda m: m.step)
    cut = h[-1].step - frac * (h[-1].step - h[0].step)
    vals = [m.value for m in h if m.step >= cut]
    return sum(vals) / len(vals)


def numbers(root: Path, db_path=None) -> str:
    os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")
    from .mlflow_sink import client_for

    res = json.loads((root / "results.json").read_text())
    sel = json.loads((root / "selection.json").read_text())
    status = json.loads((root / "status.json").read_text())
    con = db.connect(db_path or status["db"])
    client = client_for(status["mlflow_tracking_uri"])
    ref, chosen = res["reference_arm"], res["selected_arm"]
    out = [f"## Numbers ({res['campaign']})", "",
           f"SQLite: experiment `{res['experiment_id']}`, revision `{res['revision_id']}`; "
           f"MLflow: {status['mlflow_tracking_uri']} experiment `{res['campaign']}`.", ""]
    # development bank, every arm and seed
    out += ["### Development bank (selection)", "",
            "| arm | parameters | mean clears / 990 | mean levels cleared | per run (seed: dev seeds) |",
            "|---|---|---|---|---|"]
    by_arm: dict[str, list] = {}
    for jid, j in status["jobs"].items():
        by_arm.setdefault(j["arm"], []).append(j)
    for arm in sel["ranking"] + [ref]:
        t = sel["development"][arm]
        runs = "; ".join(f"{j['seed']}: {', '.join(str(v) for v in j['development'].values())}"
                         for j in sorted(by_arm[arm], key=lambda j: j["seed"]))
        mark = " (selected)" if arm == chosen else " (reference)" if arm == ref else ""
        out.append(f"| {arm}{mark} | {t['parameter_count']:,} | {t['mean_cleared']:.1f} | "
                   f"{t['mean_levels_cleared']:.1f} | {runs} |")
    out += ["", f"Ranking (rule: {sel['rule']}): {' > '.join(sel['ranking'])}. Frozen {sel['frozen']}.", ""]
    # final bank
    fs = res["final_bank"]
    out += [f"### Final bank {'/'.join(map(str, fs))} ({chosen} vs {ref})", "",
            "| training seed | " + " | ".join(f"{chosen} e{s}" for s in fs) + " | "
            + " | ".join(f"{ref} e{s}" for s in fs) + " | paired gain |", "|---" * (2 + 2 * len(fs)) + "|"]
    for seed, gain in res["paired_gain_per_training_seed"].items():
        a = [res["final"][f"{chosen}_s{seed}_e{s}"]["cleared"] for s in fs]
        b = [res["final"][f"{ref}_s{seed}_e{s}"]["cleared"] for s in fs]
        out.append(f"| {seed} | " + " | ".join(map(str, a)) + " | " + " | ".join(map(str, b)) + f" | {gain:+.1f} |")
    acc = res["acceptance"]
    out += ["", f"Mean paired gain **{res['mean_paired_gain']:+.1f}** clears per 990; acceptance "
                f"(mean >= {acc['mean_paired_gain_min']}, every pair >= {acc['each_paired_gain_min']}): "
                f"**{'met' if acc['met'] else 'not met'}**.", ""]
    n = res["per_level_clears"]["episodes_per_level_pooled"]
    out += [f"Per level, pooled over {len(res['paired_gain_per_training_seed'])} training seeds x {len(fs)} "
            f"final seeds ({n} episodes per level): "
            f"{chosen} gains on {len(res['levels_gained'])} levels and loses on {len(res['levels_regressed'])}; "
            f"levels with at least 50% observed completion: {chosen} {res['levels_at_least_half'][chosen]}, "
            f"{ref} {res['levels_at_least_half'][ref]}.", ""]
    pl_a, pl_b = res["per_level_clears"][chosen], res["per_level_clears"][ref]
    diffs = sorted(((pl_a[lv] - pl_b[lv], int(lv)) for lv in pl_a), reverse=True)
    out += ["Largest per-level differences (clears out of " + str(n) + "): gains "
            + ", ".join(f"L{lv} {d:+d}" for d, lv in diffs[:8] if d > 0) + "; losses "
            + ", ".join(f"L{lv} {d:+d}" for d, lv in sorted(diffs)[:8] if d < 0) + ".", ""]
    # training and diagnostics
    out += ["### Training (60-minute endpoints) and learning diagnostics", "",
            "Diagnostics are MLflow means over the last 10% of each run's logged steps (training-time "
            "signals, not evaluation).", "",
            "| run | steps | updates | entropy | approx KL | clip frac | expl. var. | steps/s | train clear rate | MLflow |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for arm in [ref] + sel["ranking"]:
        for j in sorted(by_arm[arm], key=lambda j: j["seed"]):
            d = {k: tail_mean(client, j["mlflow_run_id"], k) for k in DIAG}
            f = lambda v, p=3: "" if v is None else f"{v:.{p}f}"  # noqa: E731
            out.append(f"| {arm} s{j['seed']} | {j['steps']:,} | {j['updates']:,} | {f(d['losses_entropy'])} | "
                       f"{f(d['losses_approx_kl'], 4)} | {f(d['losses_clipfrac'])} | "
                       f"{f(d['losses_explained_variance'])} | {f(d['charts_sps'], 0)} | "
                       f"{f(d['charts_train_clear_rate'])} | `{j['mlflow_run_id'][:8]}` |")
    out += ["", f"Allocated: {res['allocated_core_hours']:.2f} single-thread core-hours of {res['cap_core_hours']} "
                "(training, evaluation and preflight; elapsed time per job, not measured whole-machine CPU; "
                "MLflow service overhead not included).", ""]
    return "\n".join(out)


if __name__ == "__main__":
    print(numbers(Path(sys.argv[1]).resolve(), sys.argv[2] if len(sys.argv) > 2 else None))
