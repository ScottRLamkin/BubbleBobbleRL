"""Evolutionary fine-tuning: train a population, keep the best, reseed, repeat.

    caffeinate -is uv run python scripts/evolve.py \\
        --base runs/ppo_state_all_50M/model.pt --name overnight1

Each generation, every survivor of the previous one seeds several children.
A child copies its parent's weights and genome (reward settings and PPO
hyperparameters), mutates the genome, and fine-tunes with train_ppo.train().
Children and their parents are then scored with evaluate.evaluate() - the
same measure for everyone, independent of the reward each trained on - and
the top --survivors are kept. Losers' model files are deleted.

Everything lives in runs/evolve/<name>/. The run is resumable: re-running the
same command skips members and generations that already finished.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import multiprocessing as mp
import random
import shutil
import time
import traceback
from dataclasses import asdict, dataclass, replace
from pathlib import Path

LEVELS = "1-100"


@dataclass(frozen=True)
class Genome:
    clear_bonus: float = 10.0
    time_penalty: float = 0.002
    reward_pops: bool = True
    death_penalty: float = 1.0
    lr: float = 2.5e-4
    ent_coef: float = 0.01


# (low, high) for the continuous genes. Mutation jitters on a log scale.
RANGES = {
    "clear_bonus": (10.0, 200.0),
    "time_penalty": (0.0, 0.05),
    "death_penalty": (0.5, 5.0),
    "lr": (5e-5, 5e-4),
    "ent_coef": (0.003, 0.03),
}
TIME_PENALTY_FLOOR = 0.001  # so a zero time penalty can still mutate upward
POP_FLIP_PROB = 0.15


def mutate(genome: Genome, rng: random.Random) -> Genome:
    """Jitter one or two continuous genes by x0.5-2, and maybe flip reward_pops."""
    changes: dict = {}
    for gene in rng.sample(sorted(RANGES), rng.choice((1, 2))):
        lo, hi = RANGES[gene]
        value = getattr(genome, gene)
        if gene == "time_penalty":
            value = max(value, TIME_PENALTY_FLOOR)
        value *= math.exp(rng.uniform(math.log(0.5), math.log(2.0)))
        changes[gene] = min(max(value, lo), hi)
    if rng.random() < POP_FLIP_PROB:
        changes["reward_pops"] = not genome.reward_pops
    return replace(genome, **changes)


def seed_variants(base: Genome) -> list[Genome]:
    """Hand-picked first-generation genomes: the obvious ideas get a slot each."""
    return [
        base,  # control: plain continuation of the baseline
        replace(base, clear_bonus=30.0),
        replace(base, clear_bonus=100.0),
        replace(base, time_penalty=0.01),
        replace(base, time_penalty=0.03),
        replace(base, reward_pops=False),
        replace(base, clear_bonus=30.0, time_penalty=0.01),
        replace(base, clear_bonus=100.0, time_penalty=0.01),
        replace(base, clear_bonus=100.0, time_penalty=0.03),
        replace(base, reward_pops=False, clear_bonus=30.0),
        replace(base, reward_pops=False, clear_bonus=100.0),
        replace(base, reward_pops=False, clear_bonus=100.0, time_penalty=0.01),
    ]


def fitness(result: dict) -> tuple:
    """Higher is better: most episodes cleared, then fewest deaths."""
    return (result["cleared"], -result["died"])


def select(scored: list[dict], k: int) -> list[dict]:
    """Top k of [{'id', 'result', ...}] by fitness; stable for equal fitness."""
    return sorted(scored, key=lambda m: fitness(m["result"]), reverse=True)[:k]


def plan_generation(
    gen: int, parents: list[dict], population: int, steps: int, rng: random.Random
) -> list[dict]:
    """Decide every child of a generation up front (so a resume repeats it exactly)."""
    if gen == 1:
        base = parents[0]
        genomes = seed_variants(Genome(**base["genome"]))[:population]
        while len(genomes) < population:
            genomes.append(mutate(rng.choice(genomes[:12]), rng))
        pairs = [(base, g) for g in genomes]
    else:
        pairs = []
        for i in range(population):
            parent = parents[i % len(parents)]
            genome = Genome(**parent["genome"])
            # Each parent's first child continues unmutated, as a control.
            pairs.append((parent, genome if i < len(parents) else mutate(genome, rng)))
    return [
        {
            "id": f"g{gen}m{i:02d}",
            "parent": parent["id"],
            "lineage": parent["lineage"] + [parent["id"]],
            "parent_model": parent["model"],
            "genome": asdict(genome),
            "steps": steps,
            "seed": rng.randrange(1, 2**31),
        }
        for i, (parent, genome) in enumerate(pairs)
    ]


# ------------------------------------------------------------------ workers


def _init_worker() -> None:
    import torch

    torch.set_num_threads(1)


def train_member(spec: dict) -> dict:
    """Fine-tune one child. Returns {'id', 'ok', 'seconds' | 'error'}."""
    member_dir = Path(spec["dir"])
    done = member_dir / "trained.json"
    if done.exists():
        return {"id": spec["id"], "ok": True, "skipped": True}
    member_dir.mkdir(parents=True, exist_ok=True)
    (member_dir / "genome.json").write_text(json.dumps(spec, indent=2))
    start = time.time()
    try:
        from train_ppo import parse_args, train

        g = spec["genome"]
        argv = [
            "--levels", LEVELS,
            "--total-steps", str(spec["steps"]),
            "--init-model", spec["parent_model"],
            "--run-dir", str(member_dir),
            "--seed", str(spec["seed"]),
            "--lr", str(g["lr"]),
            "--ent-coef", str(g["ent_coef"]),
            "--time-penalty", str(g["time_penalty"]),
            "--clear-bonus", str(g["clear_bonus"]),
            "--death-penalty", str(g["death_penalty"]),
            "--no-tensorboard",
            "--quiet",
        ]
        if not g["reward_pops"]:
            argv.append("--no-pop-reward")
        with open(member_dir / "train.log", "w") as log, contextlib.redirect_stdout(log):
            train(parse_args(argv))
    except Exception:
        (member_dir / "error.txt").write_text(traceback.format_exc())
        return {"id": spec["id"], "ok": False, "error": traceback.format_exc(limit=1)}
    seconds = round(time.time() - start)
    done.write_text(json.dumps({"seconds": seconds}))
    return {"id": spec["id"], "ok": True, "seconds": seconds}


def score_member(job: dict) -> dict:
    """Evaluate one model on this generation's seeds."""
    try:
        from evaluate import evaluate
        from train_ppo import parse_levels

        result = evaluate(
            job["model"], parse_levels(LEVELS), job["episodes"], job["max_steps"], job["seed"]
        )
        return {"id": job["id"], "result": result}
    except Exception:
        return {"id": job["id"], "error": traceback.format_exc(limit=1)}


# --------------------------------------------------------------- orchestrator


class Run:
    def __init__(self, args):
        self.args = args
        self.dir = Path("runs") / "evolve" / args.name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.dir / "state.json"

    def log(self, msg: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        with open(self.dir / "evolve.log", "a") as f:
            f.write(line + "\n")

    def load_state(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        # Generation 0 is the baseline, copied in so the run is self-contained.
        base_dir = self.dir / "gen_00" / "base"
        base_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.args.base, base_dir / "model.pt")
        base = {
            "id": "base",
            "lineage": [],
            "model": str(base_dir / "model.pt"),
            "genome": asdict(Genome()),
        }
        state = {"generation": 0, "base": base, "survivors": [base], "history": []}
        self.save_state(state)
        self.log(f"new run from {self.args.base}")
        return state

    def save_state(self, state: dict) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.replace(self.state_path)

    def generation(self, gen: int, state: dict, pool) -> None:
        a = self.args
        gen_dir = self.dir / f"gen_{gen:02d}"
        gen_dir.mkdir(exist_ok=True)
        plan_path = gen_dir / "plan.json"
        if plan_path.exists():
            children = json.loads(plan_path.read_text())
        else:
            rng = random.Random(a.seed * 1000 + gen)
            children = plan_generation(gen, state["survivors"], a.population, a.steps, rng)
            for c in children:
                c["dir"] = str(gen_dir / c["id"])
                c["model"] = str(gen_dir / c["id"] / "model.pt")
            plan_path.write_text(json.dumps(children, indent=2))

        self.log(f"generation {gen}: training {len(children)} children, {a.steps:,} steps each")
        start = time.time()
        trained = set()
        for n, res in enumerate(pool.imap_unordered(train_member, children), 1):
            if res["ok"]:
                trained.add(res["id"])
                note = "already done" if res.get("skipped") else f"{res['seconds']}s"
                self.log(f"  trained {res['id']} ({n}/{len(children)}, {note})")
            else:
                self.log(f"  FAILED {res['id']}: {res['error'].strip()}")

        # Score children, the survivors they came from, and the baseline, all
        # on the same fresh seeds.
        candidates = {c["id"]: c for c in children if c["id"] in trained}
        for s in state["survivors"]:
            candidates[s["id"]] = s
        to_score = dict(candidates)
        to_score.setdefault("base", state["base"])
        jobs = [
            {"id": m["id"], "model": m["model"], "episodes": a.eval_episodes,
             "max_steps": a.eval_max_steps, "seed": a.seed * 1000 + gen}
            for m in to_score.values()
        ]
        self.log(f"generation {gen}: scoring {len(jobs)} models")
        results = {}
        for res in pool.imap_unordered(score_member, jobs):
            if "result" in res:
                results[res["id"]] = res["result"]
            else:
                self.log(f"  SCORING FAILED {res['id']}: {res['error'].strip()}")

        scored = [dict(candidates[i], result=results[i]) for i in candidates if i in results]
        if not scored:
            raise RuntimeError(f"generation {gen}: nothing could be scored, see evolve.log")
        survivors = select(scored, a.survivors)
        keep = {s["id"] for s in survivors}
        for m in scored:  # kill the rest
            model = Path(m["model"])
            if m["id"] not in keep and m["id"] != "base" and self.dir in model.parents:
                model.unlink(missing_ok=True)

        ranked = sorted(scored, key=lambda m: fitness(m["result"]), reverse=True)
        state["generation"] = gen
        state["survivors"] = [
            {k: s[k] for k in ("id", "lineage", "model", "genome")} for s in survivors
        ]
        state["history"].append({
            "generation": gen,
            "minutes": round((time.time() - start) / 60, 1),
            "base_result": results.get("base"),
            "ranking": [
                {"id": m["id"], "parent": (m["lineage"] or [None])[-1], "genome": m["genome"],
                 "result": m["result"], "survived": m["id"] in keep}
                for m in ranked
            ],
        })
        self.save_state(state)
        self.write_leaderboard(state)
        best = ranked[0]
        base_r = results.get("base", {})
        self.log(
            f"generation {gen} done in {state['history'][-1]['minutes']} min: "
            f"best {best['id']} cleared {best['result']['cleared']}/{best['result']['episodes']}, "
            f"baseline {base_r.get('cleared', '?')}/{base_r.get('episodes', '?')}"
        )

    def write_leaderboard(self, state: dict) -> None:
        lines = [f"# Evolution leaderboard: {self.args.name}", ""]
        for h in reversed(state["history"]):
            b = h["base_result"] or {}
            lines += [
                f"## Generation {h['generation']} ({h['minutes']} min)",
                "",
                f"Baseline on this generation's seeds: cleared {b.get('cleared', '?')}"
                f"/{b.get('episodes', '?')}, died {b.get('died', '?')}, "
                f"timed out {b.get('timeout', '?')}.",
                "",
                "| Rank | Member | Parent | Cleared | Levels | Died | Timeout | Kept "
                "| clear bonus | time penalty | pops | death penalty | lr | entropy |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
            ]
            for rank, m in enumerate(h["ranking"], 1):
                r, g = m["result"], m["genome"]
                lines.append(
                    f"| {rank} | {m['id']} | {m['parent'] or '-'} | {r['cleared']} "
                    f"| {r['levels_cleared']} | {r['died']} | {r['timeout']} "
                    f"| {'yes' if m['survived'] else ''} | {g['clear_bonus']:.3g} "
                    f"| {g['time_penalty']:.3g} | {'on' if g['reward_pops'] else 'off'} "
                    f"| {g['death_penalty']:.3g} | {g['lr']:.3g} | {g['ent_coef']:.3g} |"
                )
            lines.append("")
        (self.dir / "leaderboard.md").write_text("\n".join(lines))

    def run(self) -> None:
        a = self.args
        state = self.load_state()
        if state["generation"] >= a.generations:
            self.log(f"already complete ({state['generation']} generations)")
            return
        ctx = mp.get_context("spawn")
        with ctx.Pool(a.workers, initializer=_init_worker) as pool:
            for gen in range(state["generation"] + 1, a.generations + 1):
                self.generation(gen, state, pool)
        champion = state["survivors"][0]
        self.log(f"finished. champion {champion['id']}: {champion['model']}")
        self.log(f"leaderboard: {self.dir / 'leaderboard.md'}")


def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", default="runs/ppo_state_all_50M/model.pt")
    p.add_argument("--name", required=True, help="run directory under runs/evolve/")
    p.add_argument("--generations", type=int, default=3)
    p.add_argument("--population", type=int, default=30)
    p.add_argument("--survivors", type=int, default=10)
    p.add_argument("--steps", type=int, default=10_000_000, help="fine-tune steps per child")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--eval-episodes", type=int, default=5, help="episodes per level when scoring")
    p.add_argument("--eval-max-steps", type=int, default=900)
    p.add_argument("--seed", type=int, default=1)
    return p.parse_args(argv)


if __name__ == "__main__":
    Run(parse_args()).run()
