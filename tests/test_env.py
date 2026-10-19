import gymnasium as gym
import numpy as np
import pytest

import bubblebobblerl  # noqa: F401  (registers BubbleBobble-v0)
from bubblebobblerl import BubbleBobbleEnv


def test_registered_with_gymnasium():
    env = gym.make("BubbleBobble-v0")
    obs, info = env.reset(seed=0)
    assert obs.shape == (64, 96)
    env.close()


@pytest.mark.parametrize("obs_type", ["screen", "state"])
def test_obs_space_conformance(obs_type):
    env = BubbleBobbleEnv(obs_type=obs_type)
    obs, _ = env.reset(seed=1)
    assert env.observation_space.contains(obs)
    for _ in range(50):
        obs, r, term, trunc, info = env.step(env.action_space.sample())
        assert env.observation_space.contains(obs)
        if term or trunc:
            break


def test_seeded_reset_is_deterministic():
    def rollout():
        env = BubbleBobbleEnv()
        env.reset(seed=42)
        frames = []
        for i in range(100):
            obs, *_ = env.step(i % env.action_space.n)
            frames.append(obs.copy())
        return np.stack(frames)

    assert (rollout() == rollout()).all()


def test_episode_terminates_on_death():
    env = BubbleBobbleEnv(lives=1, death_penalty=1.0)
    env.reset(seed=0)
    terminated = False
    for _ in range(5000):
        obs, r, terminated, truncated, info = env.step(0)  # stand still and die
        if terminated or truncated:
            break
    assert terminated


def test_truncation():
    env = BubbleBobbleEnv(max_episode_frames=100)
    env.reset(seed=0)
    for _ in range(100):
        obs, r, term, trunc, info = env.step(6)  # shoot in place, stay alive
        if term or trunc:
            break
    assert trunc or term


def test_render_modes():
    env = BubbleBobbleEnv(render_mode="rgb_array")
    env.reset(seed=0)
    frame = env.render()
    assert frame.shape == (256, 384, 3) and frame.dtype == np.uint8
    env.render_mode = "ansi"
    assert isinstance(env.render(), str)


def test_level_pool_resets_within_pool():
    env = BubbleBobbleEnv(levels=[3, 7, 12])
    seen = set()
    for seed in range(30):
        _, info = env.reset(seed=seed)
        seen.add(info["level"])
    assert seen == {3, 7, 12}
    _, info = env.reset(seed=0, options={"level": 5})  # explicit level wins
    assert info["level"] == 5


def test_state_obs_shows_loot_and_prebubbles():
    from bubblebobblerl.env import MAX_LOOT, MAX_PREBUBBLES, MAX_PROJECTILES
    from bubblebobblerl.game import Fruit, Projectile

    env = BubbleBobbleEnv(obs_type="state")
    env.reset(seed=0)
    n_shots = MAX_PROJECTILES * 5
    n_pre = MAX_PREBUBBLES * 4
    loot_at = slice(-(MAX_LOOT * 4 + n_pre + n_shots), -(n_pre + n_shots))
    pre_at = slice(-(n_pre + n_shots), -n_shots)
    loot = env._obs()[loot_at].reshape(MAX_LOOT, 4)
    assert loot[:, 0].sum() == 2  # the two static pickups

    env.game.fruits.append(Fruit(x=48, y=30, value=500))
    loot = env._obs()[loot_at].reshape(MAX_LOOT, 4)
    assert loot[:, 0].sum() == 3
    assert loot[0, 1] == pytest.approx(48 / 96)

    obs, *_ = env.step(6)  # shoot
    pre = obs[pre_at].reshape(MAX_PREBUBBLES, 4)
    assert pre[0, 0] == 1.0

    env.game.projectiles.append(Projectile("laser", x=24, y=10))
    shots = env._obs()[-n_shots:].reshape(MAX_PROJECTILES, 5)
    assert shots[0, 0] == 1.0 and shots[0, 4] == 1.0 and shots[0, 1] == pytest.approx(24 / 96)


def test_time_penalty_is_charged_per_step():
    env = BubbleBobbleEnv(time_penalty=0.5)
    env.reset(seed=0)
    _, r, *_ = env.step(0)
    assert r == pytest.approx(-0.5)


def test_reward_pops_off_ignores_bare_pop_score():
    from bubblebobblerl.game import BubbleSprite

    def pop_reward(reward_pops):
        env = BubbleBobbleEnv(reward_pops=reward_pops, frame_skip=20)
        env.reset(seed=0)
        p = env.game.player
        env.game.bubbles.append(BubbleSprite(x=p.x, y=p.y, life=0))  # touching: pops
        _, r, *_ = env.step(0)
        return r, env.game.score

    assert pop_reward(True) == (pytest.approx(0.1), 10)
    assert pop_reward(False) == (pytest.approx(0.0), 10)


def test_random_start_puts_player_on_a_platform():
    env = BubbleBobbleEnv(random_start=True)
    starts = set()
    for seed in range(20):
        env.reset(seed=seed, options={"level": 3})
        p = env.game.player
        assert env.game.standing(p.x, p.y)
        starts.add((p.x, p.y))
    assert len(starts) > 5


def test_ego_obs_is_centred_on_the_player():
    from bubblebobblerl.env import EGO_COLS, EGO_ROWS

    env = BubbleBobbleEnv(obs_type="ego")
    obs, _ = env.reset(seed=0)
    assert env.observation_space.contains(obs)
    win = obs[8 : 8 + EGO_ROWS * EGO_COLS].reshape(EGO_ROWS, EGO_COLS)
    p = env.game.player
    # the tile under the player's centre is air, the one below its feet is floor
    assert win[EGO_ROWS // 2, EGO_COLS // 2] > 0
    assert win[EGO_ROWS // 2 + 2, EGO_COLS // 2] == 0 or env.game.standing(p.x, p.y)
    # columns left of the screen edge read as wall
    assert (win[:, 0] == 0).all()
    # an enemy straight to the right has a positive x offset, same-row y offset ~0
    from bubblebobblerl.game import Enemy

    env.game.enemies = [Enemy(kind=0, x=p.x + 20, y=p.y, facing=1, spawn_delay=0, falling_in=False)]
    obs = env._obs()
    e0 = 8 + EGO_ROWS * EGO_COLS
    assert obs[e0] == 1.0 and obs[e0 + 1] == pytest.approx(20 / 96) and abs(obs[e0 + 2]) < 1e-6


def test_stationary_penalty_after_window_without_horizontal_movement():
    env = BubbleBobbleEnv(stationary_penalty=0.5, stationary_window=5, frame_skip=4)
    env.reset(seed=0)
    env.game.enemies, env.game.alive_enemies = [], 1  # nothing to die from
    rewards = [env.step(3)[1] for _ in range(8)]  # jump in place: y moves, x does not
    assert all(r == pytest.approx(0.0) for r in rewards[:5])
    assert all(r == pytest.approx(-0.5) for r in rewards[5:])
    walked = [env.step(2)[1] for _ in range(10)]  # walk right: band widens past 8 px
    assert walked[-1] == pytest.approx(0.0)


def test_stationary_band_is_configurable():
    env = BubbleBobbleEnv(stationary_penalty=0.5, stationary_window=5, stationary_band=32, frame_skip=4)
    env.reset(seed=0)
    env.game.enemies, env.game.alive_enemies = [], 1
    for _ in range(5):
        env.step(2)  # walk right 4 px per step: 16 px over the window, under the 32 px band
    assert env.step(2)[1] == pytest.approx(-0.5)


def test_explore_bonus_pays_once_per_new_column():
    env = BubbleBobbleEnv(explore_bonus=1.0, frame_skip=4)
    env.reset(seed=0)
    env.game.enemies, env.game.alive_enemies = [], 1
    rewards = [env.step(2)[1] for _ in range(6)]  # walk right 4 px per step from x=8
    assert sum(r >= 1.0 for r in rewards) == 3  # columns 2, 3 and 4 (x=16, 24, 32)
    back = [env.step(1)[1] for _ in range(6)]  # walk back over visited ground
    assert all(r < 1.0 for r in back)


def test_nearest_first_puts_the_closest_enemy_in_slot_zero():
    from bubblebobblerl.env import EGO_COLS, EGO_ROWS, GRID_COLS, GRID_ROWS
    from bubblebobblerl.game import Enemy

    for obs_type, e0 in (("state", 8 + GRID_ROWS * GRID_COLS), ("ego", 8 + EGO_ROWS * EGO_COLS)):
        env = BubbleBobbleEnv(obs_type=obs_type, nearest_first=True)
        env.reset(seed=0)
        p = env.game.player
        far = Enemy(kind=0, x=p.x + 60, y=p.y, facing=1, spawn_delay=0, falling_in=False)
        close = Enemy(kind=1, x=p.x + 12, y=p.y, facing=1, spawn_delay=0, falling_in=False)
        env.game.enemies = [far, close]  # spawn order: far first
        obs = env._obs()
        assert obs[e0 + 5] == pytest.approx(1 / 7)  # slot 0 holds the beluga (kind 1): the close one
        env.nearest_first = False
        assert env._obs()[e0 + 5] == pytest.approx(0.0)  # default keeps spawn order


def test_timeout_penalty_is_charged_once_at_truncation():
    env = BubbleBobbleEnv(timeout_penalty=4.0, max_episode_frames=40, frame_skip=4)
    env.reset(seed=0)
    env.game.enemies, env.game.alive_enemies = [], 1
    rewards = []
    for _ in range(10):
        _, r, term, trunc, _ = env.step(0)
        rewards.append(r)
    assert trunc and rewards[-1] == pytest.approx(-4.0) and all(r == pytest.approx(0.0) for r in rewards[:-1])


def test_control_obs_distinguishes_held_from_fresh_shoot():
    """The review's reproduction: identical pictures, different button history."""
    import copy

    env = BubbleBobbleEnv(obs_type="state", control_obs=True)
    env.reset(seed=1)
    env.game.player.shoot_cooldown = 0
    env.game.prev_shoot = False
    twin = copy.deepcopy(env)
    twin.game.prev_shoot = True
    assert not np.array_equal(env._obs(), twin._obs())
    assert env.observation_space.shape[0] == twin.observation_space.shape[0] == 660
    plain = BubbleBobbleEnv(obs_type="state")
    assert plain.observation_space.shape[0] == 656  # older checkpoints unaffected


def test_reward_components_are_reported_and_sum_to_the_reward():
    env = BubbleBobbleEnv(time_penalty=0.01, kill_bonus=2.0, score_reward=False)
    env.reset(seed=0)
    _, r, _, _, info = env.step(0)
    parts = [v for k, v in info.items() if k.startswith("r_")]
    assert len(parts) == 9 and sum(parts) == pytest.approx(r) and info["r_time"] == pytest.approx(-0.01)


def test_evaluate_preserves_caller_rng_and_is_reproducible(tmp_path):
    """The trainer calls evaluate() mid-run: it must leave torch/numpy RNG
    streams untouched, and the same checkpoint + seed must give the same result."""
    import sys
    from pathlib import Path

    import torch

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from evaluate import evaluate
    from train_ppo import Agent

    env = BubbleBobbleEnv(obs_type="state")
    torch.manual_seed(0)
    agent = Agent(env.observation_space, env.action_space.n)
    ckpt = tmp_path / "model.pt"
    torch.save(agent.state_dict(), ckpt)
    torch.manual_seed(123)
    np.random.seed(123)
    before_t, before_n = torch.get_rng_state().clone(), np.random.get_state()[1].copy()
    r1 = evaluate(str(ckpt), [1, 2], episodes=1, max_steps=30, seed=1001)
    assert torch.equal(torch.get_rng_state(), before_t)
    assert np.array_equal(np.random.get_state()[1], before_n)
    r2 = evaluate(str(ckpt), [1, 2], episodes=1, max_steps=30, seed=1001)
    assert r1["per_level"] == r2["per_level"] and r1["mean_score"] == r2["mean_score"]
