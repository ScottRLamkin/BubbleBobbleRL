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
