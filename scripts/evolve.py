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

Tracking: every child is an MLflow run in experiment "evolve-<name>", with its
genome as parameters, training curves, and after scoring its evaluation
(eval_cleared, eval_rank, ...) and a "survived" tag. Each generation adds a
summary run. MLflow is mandatory: workers log through the project's service
($MLFLOW_TRACKING_URI, else the UI on :5000), the run refuses to start if it does
not answer, and a tracking failure stops the run.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import multiprocessing as mp
import os
import random
import shutil
import time
import traceback
from dataclasses import asdict, dataclass, replace
from pathlib import Path

LEVELS = "1-99"  # level 100's boss is not implemented; the level never clears


@dataclass(frozen=True)
class Genome:
    """Everything a child may differ in from its parent. Defaults are the
    recipe of the current best agent (time 0.01, still 0.005 over 32 px,
    death 5), so an unmutated child is a plain continuation of it."""

    # reward shaping
    clear_bonus: float = 10.0
    time_penalty: float = 0.01
    stationary_penalty: float = 0.005
    stationary_band: int = 32
    death_penalty: float = 5.0
    timeout_penalty: float = 4.0
    capture_bonus: float = 0.1
    explore_bonus: float = 0.0
    reward_pops: bool = True
    # PPO optimisation
    lr: float = 2.5e-4
    ent_coef: float = 0.01
    clip: float = 0.1
    gamma: float = 0.99
    gae_lambda: float = 0.95
    vf_coef: float = 0.5
    epochs: int = 4
    # PPO data collection
    num_envs: int = 16
    rollout_len: int = 128


# (low, high) for the continuous genes. Mutation jitters on a log scale;
# gamma is jittered as (1 - gamma), stationary_band is rounded to pixels.
RANGES = {
    "clear_bonus": (2.0, 300.0),
    "time_penalty": (0.0, 0.1),
    "stationary_penalty": (0.0, 0.1),
    "stationary_band": (8, 64),
    "death_penalty": (0.25, 30.0),
    "timeout_penalty": (0.0, 30.0),
    "capture_bonus": (0.0, 3.0),
    "explore_bonus": (0.0, 3.0),
    "lr": (1e-5, 1e-3),
    "ent_coef": (0.0005, 0.1),
    "clip": (0.03, 0.5),
    "gamma": (0.9, 0.999),
    "gae_lambda": (0.8, 0.99),
    "vf_coef": (0.1, 2.0),
    "epochs": (1, 10),
    "num_envs": (4, 64),
    "rollout_len": (32, 1024),
}
FLOORS = {"time_penalty": 0.001, "stationary_penalty": 0.001, "timeout_penalty": 0.1,
          "capture_bonus": 0.01, "explore_bonus": 0.05}
INT_GENES = {"stationary_band", "epochs", "num_envs", "rollout_len"}
ONE_MINUS = {"gamma", "gae_lambda"}  # jittered as (1 - value)
POP_FLIP_PROB = 0.1
MUTATION_GENES = (1, 4)  # how many genes a child changes (uniform in this range)
MUTATION_SCALE = 3.0  # each changed gene is multiplied by a factor in [1/scale, scale]


def mutate(genome: Genome, rng: random.Random, n_genes=MUTATION_GENES, scale=MUTATION_SCALE) -> Genome:
    """Jitter some genes on a log scale, and maybe flip reward_pops."""
    changes: dict = {}
    k = rng.randint(n_genes[0], min(n_genes[1], len(RANGES)))
    for gene in rng.sample(sorted(RANGES), k):
        lo, hi = RANGES[gene]
        value = getattr(genome, gene)
        factor = math.exp(rng.uniform(-math.log(scale), math.log(scale)))
        if gene in ONE_MINUS:
            value = 1.0 - (1.0 - value) * factor
        else:
            value = max(value, FLOORS.get(gene, 0.0)) * factor
        value = min(max(value, lo), hi)
        changes[gene] = int(round(value)) if gene in INT_GENES else value
    if rng.random() < POP_FLIP_PROB:
        changes["reward_pops"] = not genome.reward_pops
    return replace(genome, **changes)


def seed_variants(base: Genome) -> list[Genome]:
    """Hand-picked first-generation genomes: the obvious ideas get a slot each."""
    return [
        base,  # control: plain continuation of the baseline
        replace(base, stationary_penalty=0.02),
        replace(base, stationary_penalty=0.05),
        replace(base, stationary_penalty=0.02, death_penalty=10.0),
        replace(base, time_penalty=0.02),
        replace(base, time_penalty=0.005, stationary_penalty=0.0),
        replace(base, clear_bonus=30.0),
        replace(base, capture_bonus=0.5),
        replace(base, death_penalty=2.0),
        replace(base, lr=1e-4),
        replace(base, ent_coef=0.02),
        replace(base, gamma=0.98),
        replace(base, clip=0.2),
        replace(base, reward_pops=False, capture_bonus=0.5),
    ]


# Names in train_ppo's config.json -> Genome fields (reward_pops is the inverse of no_pop_reward).
CONFIG_TO_GENE = {k: k for k in (
    "clear_bonus", "time_penalty", "stationary_penalty", "stationary_band", "death_penalty",
    "timeout_penalty", "capture_bonus", "explore_bonus", "lr", "ent_coef", "clip", "gamma",
    "gae_lambda", "vf_coef", "epochs", "num_envs", "rollout_len",
)}


def inherit_genome(model_path: Path) -> tuple[Genome, str]:
    """A base's real training recipe: from the evolve spec (genome.json) or the
    trainer's config.json next to the model. Every gene must be recorded there;
    nothing is filled from defaults."""
    folder = model_path.parent
    spec = folder / "genome.json"
    if spec.exists():
        return Genome(**json.loads(spec.read_text())["genome"]), str(spec)
    cfg = folder / "config.json"
    if not cfg.exists():
        raise FileNotFoundError(f"no genome.json or config.json next to {model_path}: its recipe is unknown")
    c = json.loads(cfg.read_text())
    fields = {gene: c[key] for key, gene in CONFIG_TO_GENE.items() if key in c}
    if "pop_reward" in c:
        fields["reward_pops"] = bool(c["pop_reward"])
    elif "no_pop_reward" in c:
        fields["reward_pops"] = not c["no_pop_reward"]
    missing = [f for f in Genome.__dataclass_fields__ if f not in fields]
    if missing:
        raise KeyError(f"{cfg} does not record genes {missing}")
    return Genome(**fields), str(cfg)


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
    if gen == 1 and len(parents) == 1:
        base = parents[0]
        genomes = seed_variants(Genome(**{**asdict(Genome()), **base["genome"]}))[:population]
        while len(genomes) < population:
            genomes.append(mutate(rng.choice(genomes[:14]), rng))
        pairs = [(base, g) for g in genomes]
    else:  # several bases start like any later generation: shared children, first ones unmutated
        pairs = []
        for i in range(population):
            parent = parents[i % len(parents)]
            genome = Genome(**{**asdict(Genome()), **parent["genome"]})
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
        from hyperparams import validate
        from train_ppo import checkpoint_obs_spec, parse_args, train

        # The child's experiment: the run's base configuration (every
        # hyperparameter stated), its genome's genes, its parent and budget.
        g = spec["genome"]
        cfg = json.loads(Path(spec["config"]).read_text())
        cfg.update({gene: g[gene] for gene in CONFIG_TO_GENE.values()})
        cfg.update(pop_reward=bool(g["reward_pops"]), total_steps=spec["steps"], seed=spec["seed"],
                   init_model=spec["parent_model"], fresh_optimizer=False)
        cfg = validate(cfg)
        parent = checkpoint_obs_spec(spec["parent_model"])
        if parent is None or any(parent[k] != cfg[k] for k in parent):
            raise ValueError(f"parent {spec['parent_model']} observation {parent} differs from the run "
                             f"configuration {({k: cfg[k] for k in ('obs', 'control_obs', 'nearest_first')})}")
        experiment = member_dir / "experiment.json"
        experiment.write_text(json.dumps(cfg, indent=1))
        argv = ["--config", str(experiment), "--run-dir", str(member_dir), "--run-name", spec["id"],
                "--no-tensorboard", "--quiet", "--experiment", spec["experiment"], "--log-every", "10"]
        for k in ("generation", "parent"):
            argv += ["--mlflow-tag", f"{k}={spec.get(k, '')}"]
        argv += ["--mlflow-tag", "lineage=" + ">".join(spec["lineage"])]
        with open(member_dir / "train.log", "w") as log, contextlib.redirect_stdout(log):
            train(parse_args(argv))
    except Exception:
        (member_dir / "error.txt").write_text(traceback.format_exc())
        return {"id": spec["id"], "ok": False, "error": traceback.format_exc(limit=1)}
    seconds = round(time.time() - start)
    if (member_dir / "best.pt").exists():  # the child's result is its best checkpoint, with its optimizer
        shutil.copy(member_dir / "best.pt", member_dir / "model.pt")
        if (member_dir / "best_optimizer.pt").exists():
            shutil.copy(member_dir / "best_optimizer.pt", member_dir / "optimizer.pt")
        else:  # no matching state: drop the final-step one rather than pair it with other weights
            (member_dir / "optimizer.pt").unlink(missing_ok=True)
    done.write_text(json.dumps({"seconds": seconds}))
    return {"id": spec["id"], "ok": True, "seconds": seconds}


def score_member(job: dict) -> dict:
    """Evaluate one model on this generation's seeds."""
    try:
        from evaluate import evaluate
        from train_ppo import parse_levels

        from train_ppo import checkpoint_obs_spec

        o = checkpoint_obs_spec(job["model"])
        if o is None:
            raise ValueError(f"{job['model']} records no observation (arch.json/config.json); refusing to guess")
        result = evaluate(
            job["model"], parse_levels(LEVELS), job["episodes"], job["max_steps"], job["seed"],
            obs=o["obs"], control_obs=o["control_obs"], nearest_first=o["nearest_first"],
        )
        result.pop("per_level", None)
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

    def require_mlflow(self) -> None:
        """MLflow is mandatory: raise unless the project's service answers.
        Workers inherit $MLFLOW_TRACKING_URI, so every child logs there."""
        from exptrack.mlflow_sink import preflight, resolve_uri

        uri = resolve_uri()
        preflight(uri)
        os.environ["MLFLOW_TRACKING_URI"] = uri
        os.environ["MLFLOW_DISABLE_AGENT_HINT"] = "1"
        self.log(f"mlflow via {uri} (experiment evolve-{self.args.name})")

    def log(self, msg: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        with open(self.dir / "evolve.log", "a") as f:
            f.write(line + "\n")

    def load_state(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        # Generation 0 is the baseline(s), copied in so the run is self-contained.
        bases = []
        for i, path in enumerate(self.args.base):
            bid = "base" if len(self.args.base) == 1 else f"base{i}"
            base_dir = self.dir / "gen_00" / bid
            base_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(path, base_dir / "model.pt")
            opt = Path(path).with_name("optimizer.pt")
            if Path(path).name == "best.pt" and Path(path).with_name("best_optimizer.pt").exists():
                opt = Path(path).with_name("best_optimizer.pt")
            if opt.exists():
                shutil.copy(opt, base_dir / "optimizer.pt")
            for meta in ("config.json", "arch.json"):  # keep the base's recorded recipe and observation
                if Path(path).with_name(meta).exists():
                    shutil.copy(Path(path).with_name(meta), base_dir / meta)
            genome, source = inherit_genome(Path(path))
            self.log(f"{bid}: genome from {source}; optimizer state {'copied' if opt.exists() else 'absent'}")
            bases.append({
                "id": bid,
                "lineage": [],
                "model": str(base_dir / "model.pt"),
                "genome": asdict(genome),
            })
        state = {"generation": 0, "base": bases[0], "survivors": bases, "history": []}
        self.save_state(state)
        self.log(f"new run from {', '.join(self.args.base)}")
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
            for c in children:  # plans written before tracking was mandatory
                c.setdefault("experiment", f"evolve-{a.name}")
        else:
            rng = random.Random(a.seed * 1000 + gen)
            children = plan_generation(gen, state["survivors"], a.population, a.steps, rng)
            for c in children:
                c["dir"] = str(gen_dir / c["id"])
                c["model"] = str(gen_dir / c["id"] / "model.pt")
                c["generation"] = gen
                c["config"] = str(Path(a.config).resolve())
                c["experiment"] = f"evolve-{a.name}"
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
        to_score.setdefault(state["base"]["id"], state["base"])
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
        self.track_generation(gen, ranked, keep, results.get(state["base"]["id"]))
        state["generation"] = gen
        state["survivors"] = [
            {k: s[k] for k in ("id", "lineage", "model", "genome")} for s in survivors
        ]
        state["history"].append({
            "generation": gen,
            "minutes": round((time.time() - start) / 60, 1),
            "base_result": results.get(state["base"]["id"]),
            "ranking": [
                {"id": m["id"], "parent": (m["lineage"] or [None])[-1], "genome": m["genome"],
                 "result": m["result"], "survived": m["id"] in keep}
                for m in ranked
            ],
        })
        self.save_state(state)
        self.write_leaderboard(state)
        best = ranked[0]
        base_r = results.get(state["base"]["id"], {})
        self.log(
            f"generation {gen} done in {state['history'][-1]['minutes']} min: "
            f"best {best['id']} cleared {best['result']['cleared']}/{best['result']['episodes']}, "
            f"baseline {base_r.get('cleared', '?')}/{base_r.get('episodes', '?')}"
        )

    def track_generation(self, gen: int, ranked: list[dict], keep: set, base_result) -> None:
        """Attach the evaluation to each member's MLflow run and add a
        generation summary run, so curves and fitness live in one place."""
        import mlflow
        from mlflow.tracking import MlflowClient

        client = MlflowClient()
        for rank, m in enumerate(ranked, 1):
            run_id_file = Path(m.get("dir", "")) / "mlflow_run_id.txt" if m.get("dir") else None
            if not run_id_file or not run_id_file.exists():
                continue
            run_id = run_id_file.read_text().strip()
            r = m["result"]
            for k in ("cleared", "died", "timeout", "levels_cleared", "mean_score"):
                client.log_metric(run_id, f"eval_{k}", float(r[k]), step=gen)
            client.log_metric(run_id, "eval_rank", rank, step=gen)
            client.set_tag(run_id, "survived", str(m["id"] in keep))
        mlflow.set_experiment(f"evolve-{self.args.name}")
        with mlflow.start_run(run_name=f"generation_{gen:02d}"):
            mlflow.set_tags({"generation": gen, "summary": "true"})
            cleared = [m["result"]["cleared"] for m in ranked]
            mlflow.log_metrics({
                "best_cleared": max(cleared),
                "mean_cleared": sum(cleared) / len(cleared),
                "survivor_floor_cleared": min(m["result"]["cleared"] for m in ranked if m["id"] in keep),
                "baseline_cleared": (base_result or {}).get("cleared", float("nan")),
            }, step=gen)
            mlflow.log_dict({m["id"]: {"genome": m["genome"], "result": m["result"]} for m in ranked},
                            f"generation_{gen:02d}.json")

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
        self.require_mlflow()
        ctx = mp.get_context("spawn")
        with ctx.Pool(a.workers, initializer=_init_worker) as pool:
            for gen in range(state["generation"] + 1, a.generations + 1):
                self.generation(gen, state, pool)
        champion = state["survivors"][0]
        self.log(f"finished. champion {champion['id']}: {champion['model']}")
        self.log(f"leaderboard: {self.dir / 'leaderboard.md'}")


def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True,
                   help="complete experiment configuration (scripts/hyperparams.py): every child's hyperparameters "
                        "except its genome's genes, parent, seed and step budget")
    p.add_argument("--base", nargs="+", required=True, help="one or more model.pt files to start from")
    p.add_argument("--name", required=True, help="run directory under runs/evolve/")
    p.add_argument("--generations", type=int, required=True)
    p.add_argument("--population", type=int, required=True)
    p.add_argument("--survivors", type=int, required=True)
    p.add_argument("--steps", type=int, required=True, help="fine-tune steps per child")
    p.add_argument("--workers", type=int, required=True)
    p.add_argument("--eval-episodes", type=int, required=True, help="episodes per level when scoring")
    p.add_argument("--eval-max-steps", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    return p.parse_args(argv)


if __name__ == "__main__":
    Run(parse_args()).run()
