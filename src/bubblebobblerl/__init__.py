"""BubbleBobbleRL - RL environment for DWedit's calculator Bubble Bobble.

A faithful-where-it-matters Python reimplementation of the TI-82/83/83+
Bubble Bobble (with the author's open-sourced Z80 code in
``bubblebobblerl/bubble/bbsource`` as the spec), exposed as a Gymnasium
environment.
"""

from gymnasium.envs.registration import register

from .env import ACTION_MEANINGS, ACTIONS, BubbleBobbleEnv, make
from .game import Buttons, Game
from .levels import Level, load_levels

__version__ = "0.2.0"
__all__ = [
    "ACTIONS",
    "ACTION_MEANINGS",
    "BubbleBobbleEnv",
    "Buttons",
    "Game",
    "Level",
    "load_levels",
    "make",
]

register(id="BubbleBobble-v0", entry_point="bubblebobblerl.env:BubbleBobbleEnv")


def main() -> None:
    """Tiny smoke demo: a random agent on level 1."""
    env = BubbleBobbleEnv(level=1)
    obs, info = env.reset(seed=0)
    total = 0.0
    for _ in range(1000):
        obs, r, term, trunc, info = env.step(env.action_space.sample())
        total += r
        if term or trunc:
            break
    print(f"random agent: {info['frame']} frames, score={info['score']}, return={total:.2f}")
    print(f"obs shape={obs.shape}, actions={list(ACTION_MEANINGS)}")
