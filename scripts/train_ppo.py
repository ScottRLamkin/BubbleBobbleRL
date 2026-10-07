"""Single-file PPO for BubbleBobble-v0 (CleanRL-style, readable over fancy).

    uv sync --extra train
    uv run python scripts/train_ppo.py --total-steps 2_000_000

Defaults train an MLP on the structured "state" observation of level 1,
which learns on a laptop CPU. Pass --obs screen for the Atari-style
pixels-in setup (use a GPU and more steps).

Watch progress:  uv run tensorboard --logdir runs/
Watch the agent: uv run python scripts/train_ppo.py --play runs/<run>/model.pt
"""

from __future__ import annotations

import argparse
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
    p.add_argument("--no-pop-reward", action="store_true", help="no reward for bare bubble pops")
    p.add_argument("--clear-bonus", type=float, default=10.0)
    p.add_argument("--death-penalty", type=float, default=1.0)
    p.add_argument("--random-start", action="store_true", help="random player start position")
    p.add_argument("--curriculum", type=float, default=0.0,
                   help="grow the level pool from level 1 to all of --levels over this fraction of training")
    p.add_argument("--obs", choices=["state", "screen"], default="state")
    p.add_argument("--arch", choices=["mlp", "conv"], default="mlp", help="state-obs encoder")
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
    p.add_argument("--quiet", action="store_true", help="one progress line per ~1M steps")
    p.add_argument("--play", default=None, help="path to a model.pt to watch")
    p.add_argument("--greedy", action="store_true", help="with --play: most likely action, no sampling")
    return p.parse_args(argv)


def parse_levels(spec: str) -> list[int]:
    levels: list[int] = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        levels.extend(range(int(lo), int(hi or lo) + 1))
    return levels


def make_env(level, levels, obs, time_penalty, reward_pops, clear_bonus, death_penalty, seed,
             random_start=False):
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
    def __init__(self, obs_space, n_actions: int, arch: str = "mlp"):
        super().__init__()
        self.arch = arch
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
            self.encoder = nn.Sequential(
                layer_init(nn.Linear(int(np.prod(obs_space.shape)), 256)),
                nn.Tanh(),
                layer_init(nn.Linear(256, 256)),
                nn.Tanh(),
            )
            self._is_image = False
        self.actor = layer_init(nn.Linear(256, n_actions), std=0.01)
        self.critic = layer_init(nn.Linear(256, 1), std=1.0)

    @classmethod
    def load(cls, path: str, obs_space, n_actions: int, pad_to: int | None = None) -> "Agent":
        """Build the right architecture for a saved model.pt and load it."""
        state = torch.load(path, map_location="cpu")
        arch = "conv" if any(k.startswith("encoder.grid.") for k in state) else "mlp"
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
        agent = cls(obs_space, n_actions, arch)
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

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    envs = gym.vector.SyncVectorEnv(
        [
            make_env(
                args.level, levels, args.obs, args.time_penalty,
                not args.no_pop_reward, args.clear_bonus, args.death_penalty,
                args.seed + i, args.random_start,
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
            envs.single_observation_space, envs.single_action_space.n, args.arch
        ).to(device)
    optimizer = torch.optim.Adam(agent.parameters(), lr=args.lr, eps=1e-5)

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

    pool_size = 0
    while global_step < args.total_steps:
        if args.curriculum and levels:
            frac = min(1.0, global_step / (args.curriculum * args.total_steps))
            k = max(1, round(frac * len(levels)))
            if k != pool_size:
                pool_size = k
                envs.set_attr("level_pool", [levels[:k]] * args.num_envs)
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
            next_done = torch.as_tensor(
                np.logical_or(term, trunc), dtype=torch.float32, device=device
            )
            if "episode" in infos and "_episode" in infos:
                mask = infos["_episode"]
                for er in np.asarray(infos["episode"]["r"])[mask]:
                    ep_returns.append(float(er))
                    if writer:
                        writer.add_scalar("charts/episodic_return", er, global_step)

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

        b_obs = obs_t.reshape(batch, *envs.single_observation_space.shape)
        b_act = act_t.reshape(batch)
        b_logp = logp_t.reshape(batch)
        b_adv = adv_t.reshape(batch)
        b_ret = ret_t.reshape(batch)

        idx = np.arange(batch)
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

        sps = int(global_step / (time.time() - start))
        recent = np.mean(ep_returns[-20:]) if ep_returns else float("nan")
        per_update = args.num_envs * args.rollout_len
        if not args.quiet or global_step % 1_000_000 < per_update:
            print(f"step {global_step:>9}  return(20ep) {recent:7.2f}  sps {sps}", flush=True)
        if writer:
            writer.add_scalar("charts/sps", sps, global_step)
        torch.save(agent.state_dict(), run_dir / "model.pt")

    envs.close()
    if writer:
        writer.close()
    print(f"saved {run_dir / 'model.pt'}")
    return run_dir / "model.pt"


def main():
    args = parse_args()
    if args.play:
        watch(args.play, args.level, args.obs, args.greedy)
        return
    train(args)


if __name__ == "__main__":
    main()
