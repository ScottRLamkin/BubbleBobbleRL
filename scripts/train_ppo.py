"""Single-file PPO for BubbleBobble-v0 (CleanRL-style, readable over fancy).

    uv sync --extra train
    uv run python scripts/train_ppo.py --total-steps 2_000_000

Defaults train an MLP on the structured "state" observation of level 1,
which learns on a laptop CPU. Pass --obs screen for the Atari-style
pixels-in setup (use a GPU and more steps).

Watch progress:  uv run mlflow ui --backend-store-uri sqlite:///mlflow.db   (http://127.0.0.1:5000)
                 uv run tensorboard --logdir runs/
Watch the agent: uv run python scripts/train_ppo.py --play runs/<run>/model.pt

Both trackers get the same curves: episodic return and length, policy and
value loss, entropy, approximate KL, clip fraction, explained variance,
learning rate and steps per second. --no-tensorboard / --no-mlflow turn
either off (evolve.py turns both off for its 30 children per generation).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path

import gymnasium as gym
import numpy as np

import bubblebobblerl  # noqa: F401  (registers BubbleBobble-v0)

try:
    import torch
    import torch.nn as nn
except ImportError:
    raise SystemExit("torch is required: uv sync --extra train")


def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser()
    p.add_argument("--level", type=int, default=1)
    p.add_argument("--levels", default=None, help='train on a pool, e.g. "1-100" or "1,5,20-30"')
    p.add_argument("--time-penalty", type=float, default=0.0, help="reward lost per step")
    p.add_argument("--stationary-penalty", type=float, default=0.0,
                   help="reward lost per step while x stays within --stationary-band for --stationary-window steps")
    p.add_argument("--stationary-window", type=int, default=30, help="agent steps (15 per second)")
    p.add_argument("--stationary-band", type=int, default=8, help="pixels")
    p.add_argument("--no-pop-reward", action="store_true", help="no reward for bare bubble pops")
    p.add_argument("--clear-bonus", type=float, default=10.0)
    p.add_argument("--death-penalty", type=float, default=1.0)
    p.add_argument("--timeout-penalty", type=float, default=0.0, help="charged when the clock runs out")
    p.add_argument("--kill-bonus", type=float, default=0.0, help="reward per enemy killed")
    p.add_argument("--no-score-reward", action="store_true", help="drop the in-game score from the reward")
    p.add_argument("--control-obs", action="store_true",
                   help="observe previous jump/shoot buttons, full jump counter and time left")
    p.add_argument("--max-episode-frames", type=int, default=3600,
                   help="episode cap in game frames (3600 = the standard test's one minute)")
    p.add_argument("--bootstrap-truncation", action="store_true",
                   help="treat the time limit as a cut-off, not an outcome: bootstrap V at truncation")
    p.add_argument("--max-minutes", type=float, default=0.0, help="stop after this much wall time")
    p.add_argument("--save-every", type=int, default=0,
                   help="also keep a numbered snapshot (ckpt_<steps>.pt) every N steps, for trajectory diagnostics")
    p.add_argument("--futility-steps", type=int, default=0,
                   help="stop when the best standard-test score has not improved for this many steps")
    p.add_argument("--fresh-optimizer", action="store_true",
                   help="with --init-model: do not load the optimizer state saved next to it")
    p.add_argument("--capture-bonus", type=float, default=0.1)
    p.add_argument("--explore-bonus", type=float, default=0.0,
                   help="reward per new 8-px column of x reached in an episode")
    p.add_argument("--random-start", action="store_true", help="random player start position")
    p.add_argument("--curriculum", type=float, default=0.0,
                   help="grow the level pool from level 1 to all of --levels over this fraction of training")
    p.add_argument("--obs", choices=["state", "screen", "ego"], default="state")
    p.add_argument("--frame-skip", type=int, default=4, help="game frames per agent step")
    p.add_argument("--nearest-first", action="store_true",
                   help="order observation slots by distance from the player")
    p.add_argument("--grace-frames", type=int, default=0,
                   help="enemies wait this many frames before entering (training only)")
    p.add_argument("--grace-anneal", type=float, default=0.0,
                   help="shrink --grace-frames linearly to 0 over this fraction of training")
    p.add_argument("--lives", type=int, default=1, help="lives per training episode")
    p.add_argument("--arch", choices=["mlp", "conv"], default="mlp", help="state-obs encoder")
    p.add_argument("--hidden", type=int, default=256, help="MLP width")
    p.add_argument("--layers", type=int, default=2, help="MLP depth")
    p.add_argument("--act", choices=["tanh", "relu"], default="tanh", help="MLP activation")
    p.add_argument("--level-sampling", choices=["uniform", "hard"], default="uniform",
                   help="hard: draw levels in proportion to their recent failure rate")
    p.add_argument("--total-steps", type=int, default=2_000_000)
    p.add_argument("--num-envs", type=int, default=16)
    p.add_argument("--rollout-len", type=int, default=128)
    p.add_argument("--lr", type=float, default=2.5e-4)
    p.add_argument("--anneal-lr", action="store_true", help="decay lr linearly to 0")
    p.add_argument("--gamma", type=float, default=0.99)
    p.add_argument("--gae-lambda", type=float, default=0.95)
    p.add_argument("--clip", type=float, default=0.1)
    p.add_argument("--epochs", type=int, default=4)
    p.add_argument("--minibatches", type=int, default=4)
    p.add_argument("--ent-coef", type=float, default=0.01)
    p.add_argument("--vf-coef", type=float, default=0.5)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--run-name", default=None)
    p.add_argument("--run-dir", default=None, help="output directory (default runs/<run-name>)")
    p.add_argument("--init-model", default=None, help="model.pt to fine-tune from")
    p.add_argument("--no-tensorboard", action="store_true")
    p.add_argument("--no-mlflow", action="store_true")
    p.add_argument("--experiment", default="bubblebobble", help="MLflow experiment name")
    p.add_argument("--mlflow-tag", action="append", default=[], metavar="KEY=VALUE",
                   help="tag the MLflow run (repeatable)")
    p.add_argument("--log-every", type=int, default=5, help="log metrics every N PPO updates")
    p.add_argument("--eval-every", type=int, default=2_000_000,
                   help="agent steps between quick evaluations over all levels (0 = off)")
    p.add_argument("--eval-episodes", type=int, default=10, help="episodes per level in the periodic standard test")
    p.add_argument("--quiet", action="store_true", help="one progress line per ~1M steps")
    p.add_argument("--play", default=None, help="path to a model.pt to watch")
    p.add_argument("--greedy", action="store_true", help="with --play: most likely action, no sampling")
    return p.parse_args(argv)


MLFLOW_URI = "sqlite:///mlflow.db"
MLFLOW_UI = "http://127.0.0.1:5000"  # a running `mlflow ui` accepts logging too


def mlflow_tracking_uri() -> str:
    """Where to log: $MLFLOW_TRACKING_URI, else the UI on port 5000 if one is
    up (several runs logging straight into the SQLite file collide; a server
    serialises them), else the SQLite file directly."""
    if os.environ.get("MLFLOW_TRACKING_URI"):
        return os.environ["MLFLOW_TRACKING_URI"]
    try:
        import urllib.request

        urllib.request.urlopen(MLFLOW_UI + "/health", timeout=0.5)
        return MLFLOW_UI
    except Exception:
        return MLFLOW_URI


def parse_levels(spec: str) -> list[int]:
    levels: list[int] = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        levels.extend(range(int(lo), int(hi or lo) + 1))
    return levels


def make_env(level, levels, obs, time_penalty, reward_pops, clear_bonus, death_penalty, seed,
             random_start=False, stationary_penalty=0.0, stationary_window=30, stationary_band=8,
             capture_bonus=0.1, explore_bonus=0.0, frame_skip=4, lives=1, nearest_first=False,
             grace_frames=0, timeout_penalty=0.0, control_obs=False, kill_bonus=0.0,
             score_reward=True, max_episode_frames=3600):
    def thunk():
        env = gym.make(
            "BubbleBobble-v0",
            level=level,
            levels=levels,
            obs_type=obs,
            time_penalty=time_penalty,
            reward_pops=reward_pops,
            clear_bonus=clear_bonus,
            death_penalty=death_penalty,
            random_start=random_start,
            stationary_penalty=stationary_penalty,
            stationary_window=stationary_window,
            stationary_band=stationary_band,
            capture_bonus=capture_bonus,
            explore_bonus=explore_bonus,
            frame_skip=frame_skip,
            lives=lives,
            nearest_first=nearest_first,
            grace_frames=grace_frames,
            timeout_penalty=timeout_penalty,
            control_obs=control_obs,
            kill_bonus=kill_bonus,
            score_reward=score_reward,
            max_episode_frames=max_episode_frames,
        )
        env = gym.wrappers.RecordEpisodeStatistics(env)
        env.reset(seed=seed)
        return env

    return thunk


def layer_init(layer, std=np.sqrt(2), bias=0.0):
    nn.init.orthogonal_(layer.weight, std)
    nn.init.constant_(layer.bias, bias)
    return layer


class GridEncoder(nn.Module):
    """State-vector encoder that reads the 16x24 tile grid with a small CNN.

    The flat MLP sees the grid as 384 unrelated numbers; convolutions give it
    the notion that neighbouring tiles form platforms, which is what a moving
    agent needs to generalise across 100 layouts.
    """

    def __init__(self, n_inputs: int):
        super().__init__()
        from bubblebobblerl.levels import GRID_COLS, GRID_ROWS

        self.grid_slice = slice(8, 8 + GRID_ROWS * GRID_COLS)
        self.shape = (GRID_ROWS, GRID_COLS)
        self.grid = nn.Sequential(
            layer_init(nn.Conv2d(1, 16, 3, padding=1)),
            nn.ReLU(),
            layer_init(nn.Conv2d(16, 32, 3, stride=2, padding=1)),
            nn.ReLU(),
            nn.Flatten(),
            layer_init(nn.Linear(32 * (GRID_ROWS // 2) * (GRID_COLS // 2), 128)),
            nn.ReLU(),
        )
        self.rest = nn.Sequential(
            layer_init(nn.Linear(n_inputs - GRID_ROWS * GRID_COLS, 128)),
            nn.Tanh(),
        )
        self.head = nn.Sequential(layer_init(nn.Linear(256, 256)), nn.Tanh())

    def forward(self, x):
        grid = x[:, self.grid_slice].reshape(-1, 1, *self.shape)
        rest = torch.cat([x[:, : self.grid_slice.start], x[:, self.grid_slice.stop :]], 1)
        return self.head(torch.cat([self.grid(grid), self.rest(rest)], 1))


class Agent(nn.Module):
    def __init__(self, obs_space, n_actions: int, arch: str = "mlp", hidden: int = 256,
                 layers: int = 2, act: str = "tanh"):
        super().__init__()
        self.arch = arch
        Act = nn.ReLU if act == "relu" else nn.Tanh
        if len(obs_space.shape) == 2:  # screen: 64x96 binary
            self.encoder = nn.Sequential(
                layer_init(nn.Conv2d(1, 16, 8, stride=4)),
                nn.ReLU(),
                layer_init(nn.Conv2d(16, 32, 4, stride=2)),
                nn.ReLU(),
                nn.Flatten(),
                layer_init(nn.Linear(32 * 7 * 11, 256)),
                nn.ReLU(),
            )
            self._is_image = True
        elif arch == "conv":
            self.encoder = GridEncoder(int(np.prod(obs_space.shape)))
            self._is_image = False
        else:
            mods, n_in = [], int(np.prod(obs_space.shape))
            for _ in range(layers):
                mods += [layer_init(nn.Linear(n_in, hidden)), Act()]
                n_in = hidden
            self.encoder = nn.Sequential(*mods)
            self._is_image = False
        width = 256 if (len(obs_space.shape) == 2 or arch == "conv") else hidden
        self.actor = layer_init(nn.Linear(width, n_actions), std=0.01)
        self.critic = layer_init(nn.Linear(width, 1), std=1.0)

    @classmethod
    def load(cls, path: str, obs_space, n_actions: int, pad_to: int | None = None) -> "Agent":
        """Build the right architecture for a saved model.pt and load it.
        Leaves the caller's global torch RNG untouched (construction would
        otherwise draw random initial weights before they are overwritten)."""
        with torch.random.fork_rng(devices=[]):
            return cls._load(path, obs_space, n_actions, pad_to)

    @classmethod
    def _load(cls, path: str, obs_space, n_actions: int, pad_to: int | None = None) -> "Agent":
        state = torch.load(path, map_location="cpu")
        arch = "conv" if any(k.startswith("encoder.grid.") for k in state) else "mlp"
        hidden, layers, act = 256, 2, "tanh"
        if arch == "mlp" and "encoder.0.weight" in state:
            hidden = state["encoder.0.weight"].shape[0]
            layers = sum(1 for k in state if k.startswith("encoder.") and k.endswith(".weight"))
            side = Path(path).with_name("arch.json")
            if side.exists():
                act = json.loads(side.read_text()).get("act", act)
        if len(obs_space.shape) == 1 and arch == "mlp" and pad_to:
            # Fine-tune a model trained on a shorter state vector: new inputs
            # start with zero weight, so the old policy is reproduced exactly.
            w = state["encoder.0.weight"]
            if w.shape[1] < pad_to:
                state["encoder.0.weight"] = torch.cat(
                    [w, torch.zeros(w.shape[0], pad_to - w.shape[1])], 1
                )
        n_inputs = None
        if len(obs_space.shape) == 1:
            if arch == "conv":
                n_inputs = state["encoder.rest.0.weight"].shape[1] + 16 * 24
            else:
                n_inputs = state["encoder.0.weight"].shape[1]
            if n_inputs != obs_space.shape[0]:
                # Older model, trained before inputs were appended to the
                # state vector: build it at its own size; callers trim the
                # observation with obs_in().
                from gymnasium import spaces

                obs_space = spaces.Box(-1.0, 1.0, shape=(n_inputs,), dtype=np.float32)
        agent = cls(obs_space, n_actions, arch, hidden, layers, act)
        agent.load_state_dict(state)
        agent.n_inputs = n_inputs
        agent.eval()
        return agent

    def obs_in(self, o):
        """Trim an observation to the inputs this model was trained with."""
        n = getattr(self, "n_inputs", None)
        return o if n is None or o.shape[-1] == n else o[..., :n]

    def _encode(self, x):
        if self._is_image:
            x = x.float().unsqueeze(1)
        return self.encoder(x)

    def value(self, x):
        return self.critic(self._encode(x)).squeeze(-1)

    def action_value(self, x, action=None, greedy=False):
        hidden = self._encode(x)
        logits = self.actor(hidden)
        dist = torch.distributions.Categorical(logits=logits)
        if action is None:
            action = logits.argmax(-1) if greedy else dist.sample()
        return action, dist.log_prob(action), dist.entropy(), self.critic(hidden).squeeze(-1)


def watch(model_path: str, level: int, obs: str, greedy: bool = False):
    env = gym.make("BubbleBobble-v0", level=level, obs_type=obs)
    agent = Agent.load(model_path, env.observation_space, env.action_space.n)
    try:
        import imageio.v3 as iio
        from bubblebobblerl.render import draw_rgb
    except ImportError:
        iio = None
    o, _ = env.reset(seed=0)
    frames, total = [], 0.0
    for _ in range(3000):
        with torch.no_grad():
            a, *_ = agent.action_value(torch.as_tensor(agent.obs_in(o)[None]), greedy=greedy)
        o, r, term, trunc, info = env.step(int(a))
        total += r
        if iio:
            frames.append(draw_rgb(env.unwrapped.game, scale=4))
        if term or trunc:
            break
    print(f"return={total:.2f} score={info['score']}")
    if iio and frames:
        iio.imwrite("agent.gif", frames, duration=33, loop=0)
        print("wrote agent.gif")


def train(args) -> Path:
    """Run PPO with the given parsed args; returns the path of the saved model."""
    levels = parse_levels(args.levels) if args.levels else None
    run_name = args.run_name or f"ppo_{args.obs}_L{args.levels or args.level}_{int(time.time())}"
    run_dir = Path(args.run_dir) if args.run_dir else Path("runs") / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    writer = None
    if not args.no_tensorboard:
        try:
            from torch.utils.tensorboard import SummaryWriter

            writer = SummaryWriter(str(run_dir))
        except ImportError:
            pass
    tracker = None
    if not args.no_mlflow:
        try:
            os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
            os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")  # keep it fully local
            import mlflow

            # Local SQLite store in the repo root (gitignored); artifacts go to mlruns/.
            mlflow.set_tracking_uri(mlflow_tracking_uri())
            import random as _random

            for attempt in range(5):  # concurrent starts race on creating the experiment
                try:
                    exp = mlflow.set_experiment(args.experiment)
                    if exp.name == args.experiment:
                        break
                except Exception:
                    pass
                time.sleep(0.5 + _random.random())
            else:
                raise RuntimeError(f"could not select MLflow experiment {args.experiment!r}")
            active = mlflow.start_run(run_name=run_name, experiment_id=exp.experiment_id)
            assert active.info.experiment_id == exp.experiment_id
            mlflow.log_params({k: v for k, v in vars(args).items() if k not in ("play", "greedy")})
            mlflow.set_tags(dict(t.split("=", 1) for t in args.mlflow_tag))
            (run_dir / "mlflow_run_id.txt").write_text(active.info.run_id)
            tracker = mlflow
        except Exception as exc:  # a tracker problem must never kill a run
            print(f"mlflow disabled: {exc}", flush=True)

    def log_metrics(metrics: dict, step: int) -> None:
        if writer:
            for k, v in metrics.items():
                writer.add_scalar(k, v, step)
        if tracker:
            try:  # a busy SQLite file or a hiccup in the server must not kill the run
                tracker.log_metrics({k.replace("/", "_"): float(v) for k, v in metrics.items()}, step=step)
            except Exception as exc:
                print(f"mlflow log failed at step {step}: {exc}", flush=True)

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    envs = gym.vector.SyncVectorEnv(
        [
            make_env(
                args.level, levels, args.obs, args.time_penalty,
                not args.no_pop_reward, args.clear_bonus, args.death_penalty,
                args.seed + i, args.random_start, args.stationary_penalty,
                args.stationary_window, args.stationary_band, args.capture_bonus,
                args.explore_bonus, args.frame_skip, args.lives, args.nearest_first,
                args.grace_frames, args.timeout_penalty, args.control_obs, args.kill_bonus,
                not args.no_score_reward, args.max_episode_frames,
            )
            for i in range(args.num_envs)
        ]
    )
    if args.init_model:
        agent = Agent.load(
            args.init_model, envs.single_observation_space, envs.single_action_space.n,
            pad_to=int(np.prod(envs.single_observation_space.shape)),
        ).to(device)
        agent.train()
    else:
        agent = Agent(
            envs.single_observation_space, envs.single_action_space.n, args.arch,
            args.hidden, args.layers, args.act,
        ).to(device)
    (run_dir / "arch.json").write_text(json.dumps({"act": args.act}))
    # The full recipe, so a later run (or evolve.py) can inherit it exactly.
    (run_dir / "config.json").write_text(json.dumps(vars(args), indent=1, default=str))
    optimizer = torch.optim.Adam(agent.parameters(), lr=args.lr, eps=1e-5)
    resumed_optimizer = False
    if args.init_model and not args.fresh_optimizer:
        init = Path(args.init_model)
        opt_path = init.with_name("optimizer.pt")
        if init.name == "best.pt":  # the state saved at the same step as best.pt
            opt_path = init.with_name("best_optimizer.pt")
            if not opt_path.exists():
                print("no best_optimizer.pt next to best.pt: not pairing it with optimizer.pt; fresh Adam", flush=True)
        if opt_path.exists():
            try:
                optimizer.load_state_dict(torch.load(opt_path, map_location=device))
                for group in optimizer.param_groups:
                    group["lr"] = args.lr
                resumed_optimizer = True
            except Exception as exc:  # shape mismatch (different architecture/inputs): start fresh
                print(f"optimizer state not loaded ({exc}); fresh Adam", flush=True)
    print(f"optimizer: {'resumed from ' + str(opt_path) if resumed_optimizer else 'fresh Adam'}", flush=True)

    batch = args.num_envs * args.rollout_len
    obs_t = torch.zeros(
        (args.rollout_len, args.num_envs, *envs.single_observation_space.shape),
        device=device,
    )
    act_t = torch.zeros((args.rollout_len, args.num_envs), dtype=torch.long, device=device)
    logp_t = torch.zeros((args.rollout_len, args.num_envs), device=device)
    rew_t = torch.zeros((args.rollout_len, args.num_envs), device=device)
    done_t = torch.zeros((args.rollout_len, args.num_envs), device=device)
    val_t = torch.zeros((args.rollout_len, args.num_envs), device=device)

    o, _ = envs.reset(seed=args.seed)
    next_obs = torch.as_tensor(o, dtype=torch.float32, device=device)
    next_done = torch.zeros(args.num_envs, device=device)
    global_step = 0
    start = time.time()
    ep_returns: list[float] = []
    ep_lengths: list[float] = []
    ep_outcomes: list[str] = []  # "clear" / "death" / "timeout", from training episodes
    n_updates = 0
    next_eval = args.eval_every
    eval_levels = [lv for lv in (levels or [args.level]) if lv != 100] or [args.level]
    best_cleared, best_step = -1, 0  # the run's result is its best evaluated checkpoint
    next_snapshot = args.save_every
    reward_parts = {f"r_{k}": 0.0 for k in ("score", "capture", "kill", "death", "clear", "time",
                                            "stationary", "timeout", "explore")}

    pool_size = 0
    grace = args.grace_frames
    fails: dict[int, list[int]] = {lv: [] for lv in (levels or [])}  # recent outcomes per level
    while global_step < args.total_steps:
        if args.max_minutes and (time.time() - start) / 60 >= args.max_minutes:
            print(f"wall budget of {args.max_minutes} min reached at step {global_step}", flush=True)
            break
        if args.futility_steps and best_step and global_step - best_step >= args.futility_steps:
            print(f"futility: best unchanged since step {best_step} ({args.futility_steps:,} steps ago); stopping at {global_step}", flush=True)
            break
        if args.grace_frames and args.grace_anneal:
            frac = min(1.0, global_step / (args.grace_anneal * args.total_steps))
            g_now = int(round(args.grace_frames * (1.0 - frac)))
            if g_now != grace:
                grace = g_now
                envs.set_attr("grace_frames", [grace] * args.num_envs)
        if args.curriculum and levels:
            frac = min(1.0, global_step / (args.curriculum * args.total_steps))
            k = max(1, round(frac * len(levels)))
            if k != pool_size:
                pool_size = k
                envs.set_attr("level_pool", [levels[:k]] * args.num_envs)
        if args.level_sampling == "hard" and levels and n_updates % 10 == 0:
            # Weighted pool: a level appears as many times as its recent failure
            # share suggests (floor 1), so the hardest levels are drawn most.
            weighted = []
            for lv in levels:
                h = fails.get(lv, [])
                rate = sum(h) / len(h) if h else 1.0
                weighted += [lv] * (1 + int(round(9 * rate)))
            envs.set_attr("level_pool", [weighted] * args.num_envs)
        if args.anneal_lr:
            frac = max(0.0, 1.0 - global_step / args.total_steps)
            optimizer.param_groups[0]["lr"] = frac * args.lr
        for t in range(args.rollout_len):
            global_step += args.num_envs
            obs_t[t] = next_obs
            done_t[t] = next_done
            with torch.no_grad():
                a, logp, _, v = agent.action_value(next_obs)
            act_t[t], logp_t[t], val_t[t] = a, logp, v
            o, r, term, trunc, infos = envs.step(a.cpu().numpy())
            rew_t[t] = torch.as_tensor(r, dtype=torch.float32, device=device)
            next_obs = torch.as_tensor(o, dtype=torch.float32, device=device)
            for k in reward_parts:
                if k in infos:
                    reward_parts[k] += float(np.sum(infos[k]))
            if args.bootstrap_truncation:
                cut = np.logical_and(trunc, np.logical_not(term))
                if cut.any():  # the obs returned at a time-limit cut is the final one: bootstrap it
                    with torch.no_grad():
                        v_final = agent.value(next_obs[torch.as_tensor(cut, device=device)])
                    rew_t[t][torch.as_tensor(cut, device=device)] += args.gamma * v_final
            next_done = torch.as_tensor(
                np.logical_or(term, trunc), dtype=torch.float32, device=device
            )
            if "episode" in infos and "_episode" in infos:
                mask = infos["_episode"]
                alive = np.asarray(infos.get("enemies_alive", np.ones(args.num_envs)))
                for er, el, ea, tr in zip(
                    np.asarray(infos["episode"]["r"])[mask], np.asarray(infos["episode"]["l"])[mask],
                    alive[mask], np.asarray(trunc)[mask],
                ):
                    ep_returns.append(float(er))
                    ep_lengths.append(float(el))
                    ep_outcomes.append("clear" if ea == 0 else ("timeout" if tr else "death"))
                if args.level_sampling == "hard" and levels and "level" in infos:
                    for lv, ea in zip(np.asarray(infos["level"])[mask], alive[mask]):
                        hist = fails.setdefault(int(lv), [])
                        hist.append(0 if ea == 0 else 1)
                        del hist[:-20]

        # GAE
        with torch.no_grad():
            next_value = agent.value(next_obs)
        adv_t = torch.zeros_like(rew_t)
        last_gae = 0.0
        for t in reversed(range(args.rollout_len)):
            nonterminal = 1.0 - (next_done if t == args.rollout_len - 1 else done_t[t + 1])
            nv = next_value if t == args.rollout_len - 1 else val_t[t + 1]
            delta = rew_t[t] + args.gamma * nv * nonterminal - val_t[t]
            last_gae = delta + args.gamma * args.gae_lambda * nonterminal * last_gae
            adv_t[t] = last_gae
        ret_t = adv_t + val_t
        # Gymnasium's vector autoreset (next-step mode) makes the step after a
        # terminal one a fake transition: the action is ignored, the reward is
        # 0 and the "observation" was the previous episode's final frame.
        # done_t marks exactly those steps; keep them out of the update.
        real = (done_t == 0).reshape(-1).cpu().numpy()

        b_obs = obs_t.reshape(batch, *envs.single_observation_space.shape)
        b_act = act_t.reshape(batch)
        b_logp = logp_t.reshape(batch)
        b_adv = adv_t.reshape(batch)
        b_ret = ret_t.reshape(batch)

        idx = np.arange(batch)[real]
        stats = {"pg_loss": [], "v_loss": [], "entropy": [], "approx_kl": [], "clipfrac": []}
        for _ in range(args.epochs):
            np.random.shuffle(idx)
            for mb in np.array_split(idx, args.minibatches):
                mb_t = torch.as_tensor(mb, device=device)
                _, newlogp, entropy, newv = agent.action_value(b_obs[mb_t], b_act[mb_t])
                ratio = (newlogp - b_logp[mb_t]).exp()
                adv = b_adv[mb_t]
                adv = (adv - adv.mean()) / (adv.std() + 1e-8)
                pg_loss = torch.max(
                    -adv * ratio,
                    -adv * ratio.clamp(1 - args.clip, 1 + args.clip),
                ).mean()
                v_loss = 0.5 * ((newv - b_ret[mb_t]) ** 2).mean()
                loss = pg_loss + args.vf_coef * v_loss - args.ent_coef * entropy.mean()
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(agent.parameters(), 0.5)
                optimizer.step()
                with torch.no_grad():
                    stats["pg_loss"].append(pg_loss.item())
                    stats["v_loss"].append(v_loss.item())
                    stats["entropy"].append(entropy.mean().item())
                    stats["approx_kl"].append((b_logp[mb_t] - newlogp).mean().item())
                    stats["clipfrac"].append(((ratio - 1).abs() > args.clip).float().mean().item())

        sps = int(global_step / (time.time() - start))
        recent = np.mean(ep_returns[-20:]) if ep_returns else float("nan")
        window = ep_outcomes[-100:]
        rates = {k: window.count(k) / max(len(window), 1) for k in ("clear", "death", "timeout")}
        per_update = args.num_envs * args.rollout_len
        if not args.quiet or global_step % 1_000_000 < per_update:
            print(
                f"step {global_step:>9}  return(20ep) {recent:7.2f}  "
                f"clear {100 * rates['clear']:3.0f}%  death {100 * rates['death']:3.0f}%  "
                f"timeout {100 * rates['timeout']:3.0f}%  sps {sps}",
                flush=True,
            )
        n_updates += 1
        if args.eval_every and global_step >= next_eval:
            next_eval += args.eval_every
            torch.save(agent.state_dict(), run_dir / "model.pt")
            torch.save(optimizer.state_dict(), run_dir / "optimizer.pt")
            from evaluate import evaluate

            agent.eval()
            ev = evaluate(str(run_dir / "model.pt"), eval_levels, args.eval_episodes,
                          900 * 4 // args.frame_skip, obs=args.obs,
                          frame_skip=args.frame_skip, nearest_first=args.nearest_first,
                          control_obs=args.control_obs)
            agent.train()
            share = ev["cleared"] / ev["episodes"]
            if ev["cleared"] > best_cleared:
                best_cleared, best_step = ev["cleared"], global_step
                shutil.copy(run_dir / "model.pt", run_dir / "best.pt")
                shutil.copy(run_dir / "optimizer.pt", run_dir / "best_optimizer.pt")
                (run_dir / "best_eval.json").write_text(json.dumps(
                    {"step": global_step, **{k: v for k, v in ev.items()}}, indent=1))
            print(
                f"  eval @ {global_step:>9}: cleared {ev['cleared']}/{ev['episodes']} "
                f"({100 * share:.0f}%), died {ev['died']}, timed out {ev['timeout']}, "
                f"levels cleared {ev['levels_cleared']}/{len(eval_levels)}"
                f"{'  <- best so far' if best_step == global_step else ''}",
                flush=True,
            )
            log_metrics({
                "eval/clear_rate": share,
                "eval/best_cleared": best_cleared,
                "eval/death_rate": ev["died"] / ev["episodes"],
                "eval/timeout_rate": ev["timeout"] / ev["episodes"],
                "eval/levels_cleared": ev["levels_cleared"],
                "eval/mean_score": ev["mean_score"],
                "eval/kills_per_episode": ev["kills_per_episode"],
                "eval/minutes_elapsed": (time.time() - start) / 60,
            }, global_step)
        if n_updates % args.log_every == 0:
            logged_parts = dict(reward_parts)
            for k in reward_parts:
                reward_parts[k] = 0.0
            y_pred, y_true = val_t.ravel().cpu().numpy(), ret_t.ravel().cpu().numpy()
            var_y = np.var(y_true)
            log_metrics({
                "charts/episodic_return": recent,
                "charts/train_clear_rate": rates["clear"],
                "charts/train_death_rate": rates["death"],
                "charts/train_timeout_rate": rates["timeout"],
                **{f"reward/{k[2:]}_per_step": v / (args.log_every * args.num_envs * args.rollout_len)
                   for k, v in logged_parts.items()},
                "charts/episodic_length": np.mean(ep_lengths[-20:]) if ep_lengths else float("nan"),
                "charts/sps": sps,
                "charts/learning_rate": optimizer.param_groups[0]["lr"],
                "charts/level_pool": pool_size or (len(levels) if levels else 1),
                "charts/grace_frames": grace,
                "losses/policy_loss": np.mean(stats["pg_loss"]),
                "losses/value_loss": np.mean(stats["v_loss"]),
                "losses/entropy": np.mean(stats["entropy"]),
                "losses/approx_kl": np.mean(stats["approx_kl"]),
                "losses/clipfrac": np.mean(stats["clipfrac"]),
                "losses/explained_variance": float("nan") if var_y == 0 else 1 - np.var(y_true - y_pred) / var_y,
            }, global_step)
        torch.save(agent.state_dict(), run_dir / "model.pt")
        torch.save(optimizer.state_dict(), run_dir / "optimizer.pt")
        if args.save_every and global_step >= next_snapshot:
            next_snapshot += args.save_every
            torch.save(agent.state_dict(), run_dir / f"ckpt_{global_step:09d}.pt")

    envs.close()
    if writer:
        writer.close()
    if tracker:
        tracker.log_artifact(str(run_dir / "model.pt"))
        if (run_dir / "best.pt").exists():
            tracker.log_artifact(str(run_dir / "best.pt"))
            tracker.log_metrics({"eval/best_step": best_step}, step=global_step)
        tracker.end_run()
    print(f"saved {run_dir / 'model.pt'}")
    if best_step:
        print(f"best checkpoint: {run_dir / 'best.pt'} (cleared {best_cleared} at step {best_step})")
    return run_dir / "model.pt"


def main():
    args = parse_args()
    if args.play:
        watch(args.play, args.level, args.obs, args.greedy)
        return
    train(args)


if __name__ == "__main__":
    main()
