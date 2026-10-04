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
