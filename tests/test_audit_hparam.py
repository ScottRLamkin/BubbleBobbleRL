"""The campaign auditor against synthetic campaign records (no game episodes):
a clean campaign passes; each injected defect is reported."""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_hparam_campaign import audit  # noqa: E402
from train_ppo import parse_args  # noqa: E402

MANIFEST = json.loads((ROOT / "scripts/campaigns/hyperparameter_search_1019.json").read_text())


def _argv(cfg, seed, minutes, run_dir):
    """Independent of the runner: manifest values written as trainer flags."""
    argv = ["train_ppo.py"]
    for k, v in {**MANIFEST["fixed_parameters"], **cfg["parameters"]}.items():
        if v is None or v is False:
            continue
        argv += [f"--{k.replace('_', '-')}"] + ([] if v is True else [str(v)])
    return argv + ["--seed", str(seed), "--wall-minutes", str(minutes), "--run-dir", str(run_dir),
                   "--wall-start", "1.0"]


def _eval(clears, deaths_shift=0):
    per = {}
    left = clears
    for lv in range(1, 100):
        c = min(10, left)
        left -= c
        per[str(lv)] = ["clear"] * c + ["death"] * (10 - c)
    died = 990 - clears
    return {"episodes": 990, "cleared": clears, "died": died + deaths_shift, "timeout": 0,
            "levels_cleared": sum(1 for v in per.values() if "clear" in v), "all_killed": clears,
            "killed_all_then_died": 0, "killed_all_then_timeout": 0, "mean_score": 0.0,
            "kills_per_episode": 0.5 + clears / 990, "per_level": per, "seconds": 20.0}


def _write_train_job(root, jid, phase, cfg_id, seed, minutes, eval_seeds, clears):
    d = root / ("screen" if phase == "screen" else "conf") / jid.split("/", 1)[1]
    d.mkdir(parents=True)
    cfg = next(c for c in MANIFEST["configurations"] if c["id"] == cfg_id)
    (d / "argv.json").write_text(json.dumps(_argv(cfg, seed, minutes, d)))
    (d / "train_summary.json").write_text(json.dumps({"steps": 1000, "updates": 10, "seconds": 1.0}))
    (d / "model.pt").write_bytes(jid.encode())
    results = {}
    for s in eval_seeds:
        (d / f"eval_{s}.json").write_text(json.dumps(_eval(clears)))
        results[str(s)] = {"cleared": clears, "kills": (0.5 + clears / 990) * 990}
    return {"kind": "train", "phase": phase, "config": cfg_id, "seed": seed, "minutes": minutes,
            "eval_seeds": eval_seeds, "state": "done", "dir": str(d), "results": results,
            "model_sha256": hashlib.sha256(jid.encode()).hexdigest(), "reserved_seconds": 1.0,
            "elapsed_seconds": 61.0, "train_seconds": 20.0}


def build(root: Path) -> Path:
    m = MANIFEST
    jobs, order = {}, []
    tune = m["screen"]["evaluation_seeds"]
    for i, c in enumerate(m["screen"]["order"]):
        jid = f"screen/{c}"
        jobs[jid] = _write_train_job(root, jid, "screen", c, m["screen"]["training_seed"], 15, tune, 100 + i)
        order.append(jid)
    # Highest screen clears are the last two in the recorded order (neither is anchor_G).
    chosen = [m["screen"]["order"][-1], m["screen"]["order"][-2]]
    for c, base in ((chosen[0], 300), (chosen[1], 200), ("anchor_G", 150)):
        for s in m["confirmation_training"]["training_seeds"]:
            jid = f"conf/{c}_s{s}"
            jobs[jid] = _write_train_job(root, jid, "confirmation", c, s, 60, tune, base + s % 10)
            order.append(jid)
    winner = chosen[0]
    ckpts = {f"{c}_s{s}": {"model": jobs[f"conf/{c}_s{s}"]["dir"] + "/model.pt",
                           "sha256": jobs[f"conf/{c}_s{s}"]["model_sha256"]}
             for c in (winner, "anchor_G") for s in m["confirmation_training"]["training_seeds"]}
    frozen = {"winner": winner, "checkpoints": ckpts}
    (root / "frozen.json").write_text(json.dumps(frozen))
    past = time.time() - 100
    os.utime(root / "frozen.json", (past, past))
    for key, ck in ckpts.items():
        cfg, s = key.rsplit("_s", 1)
        for e in m["final_test"]["evaluation_seeds"]:
            jid = f"final/{key}_e{e}"
            d = root / "final" / jid.split("/", 1)[1]
            d.mkdir(parents=True)
            clears = 260 if cfg == winner else 200
            (d / f"eval_{e}.json").write_text(json.dumps(_eval(clears)))
            jobs[jid] = {"kind": "eval", "phase": "final", "config": cfg, "seed": int(s), "eval_seed": e,
                         "model": ck["model"], "model_sha256": ck["sha256"], "state": "done", "dir": str(d),
                         "results": {str(e): {"cleared": clears, "kills": (0.5 + clears / 990) * 990}},
                         "reserved_seconds": 90.0, "elapsed_seconds": 20.5}
            order.append(jid)
    st = {"campaign": "hparam-1019-v1", "phase": "complete", "order": order, "jobs": jobs,
          "selection": {"chosen": chosen}, "frozen": frozen, "final": {"accepted": True}, "charged_seconds": 1.0}
    (root / "status.json").write_text(json.dumps(st))
    return root


def run(root):
    return audit(root, manifest=MANIFEST, parse_args=parse_args)


def _problems(root):
    return [f"{w}: {m}" for w, m in run(root)["problems"]]


def test_clean_synthetic_campaign_passes(tmp_path):
    a = run(build(tmp_path))
    assert a["problems"] == []
    assert a["final"]["accepted"] and a["final"]["mean_gain"] == 60


def _edit_status(root, fn):
    st = json.loads((root / "status.json").read_text())
    fn(st)
    (root / "status.json").write_text(json.dumps(st))


def _first_screen_eval(root):
    st = json.loads((root / "status.json").read_text())
    return Path(st["jobs"]["screen/anchor_G"]["dir"]) / "eval_51001.json"


@pytest.mark.parametrize("case", ["wrong_level_key", "inconsistent_deaths"])
def test_eval_schema_defects_are_reported(tmp_path, case):
    root = build(tmp_path)
    f = _first_screen_eval(root)
    r = json.loads(f.read_text())
    if case == "wrong_level_key":
        r["per_level"]["100"] = r["per_level"].pop("99")
    else:
        r["died"] += 1
        r["timeout"] -= 1  # totals still sum to 990; only the per-level reconciliation catches it
    f.write_text(json.dumps(r))
    probs = _problems(root)
    assert any("screen/anchor_G" in p and ("level keys" in p if case == "wrong_level_key" else "died" in p)
               for p in probs), probs


def test_incomplete_confirmation_makes_a_candidate_ineligible(tmp_path):
    root = build(tmp_path)
    st = json.loads((root / "status.json").read_text())
    c = st["selection"]["chosen"][0]
    _edit_status(root, lambda s: s["jobs"][f"conf/{c}_s4202"].update(state="failed", error="x"))
    a = run(root)
    assert [x["eligible"] for x in a["candidates"]] == [False, True]
    assert any("frozen winner" in m for _, m in a["problems"])  # the recorded winner is no longer eligible


def test_changed_checkpoint_hash_is_reported(tmp_path):
    root = build(tmp_path)
    st = json.loads((root / "status.json").read_text())
    (Path(st["jobs"]["conf/anchor_G_s4201"]["dir"]) / "model.pt").write_bytes(b"tampered")
    probs = _problems(root)
    assert any("conf/anchor_G_s4201" in p and "changed" in p for p in probs)
    assert any("frozen checkpoint changed" in p for p in probs)


def test_duplicate_results_are_reported(tmp_path):
    root = build(tmp_path)

    def dup(st):
        j = dict(st["jobs"]["screen/ff01"])
        st["jobs"]["screen/ff01_again"] = j
        st["order"].append("screen/ff01_again")

    _edit_status(root, dup)
    probs = _problems(root)
    assert any("duplicate record" in p for p in probs)
    assert any("same checkpoint hash" in p for p in probs)


def test_final_bank_leak_and_premature_final_file_are_reported(tmp_path):
    root = build(tmp_path)
    st = json.loads((root / "status.json").read_text())
    d = Path(st["jobs"]["screen/ff01"]["dir"])
    (d / "eval_61001.json").write_text(json.dumps(_eval(1)))
    fin = next(j for j in st["jobs"].values() if j["phase"] == "final")
    f = Path(fin["dir"]) / f"eval_{fin['eval_seed']}.json"
    old = time.time() - 1000
    os.utime(f, (old, old))
    probs = _problems(root)
    assert any("final-bank seed evaluated outside" in p for p in probs)
    assert any("predates frozen.json" in p for p in probs)


def test_argv_drift_from_the_manifest_is_reported(tmp_path):
    root = build(tmp_path)
    st = json.loads((root / "status.json").read_text())
    p = Path(st["jobs"]["screen/ff02"]["dir"]) / "argv.json"
    argv = json.loads(p.read_text())
    argv[argv.index("--lr") + 1] = "0.0005"
    p.write_text(json.dumps(argv))
    assert any("screen/ff02" in x and "lr" in x for x in _problems(root))
