"""Gymnasium environment around the Bubble Bobble reimplementation."""

from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .game import Buttons, Game, SCREEN_H, SCREEN_W
from .levels import GRID_COLS, GRID_ROWS, load_levels
from .render import draw_rgb, draw_screen

# Minimal action set, ALE-style: every useful button combination.
ACTIONS: tuple[Buttons, ...] = (
    Buttons(),                          # 0 noop
    Buttons(left=True),                 # 1
    Buttons(right=True),                # 2
    Buttons(jump=True),                 # 3
    Buttons(left=True, jump=True),      # 4
    Buttons(right=True, jump=True),     # 5
    Buttons(shoot=True),                # 6
    Buttons(left=True, shoot=True),     # 7
    Buttons(right=True, shoot=True),    # 8
)
ACTION_MEANINGS = (
    "NOOP", "LEFT", "RIGHT", "JUMP", "LEFT+JUMP",
    "RIGHT+JUMP", "SHOOT", "LEFT+SHOOT", "RIGHT+SHOOT",
)

MAX_ENEMIES = 16
MAX_BUBBLES = 16


class BubbleBobbleEnv(gym.Env):
    """One level (or a run of levels) of calculator Bubble Bobble.

    obs_type:
      "screen" - (64, 96) uint8 binary frame, the 1-bit LCD picture.
      "state"  - flat float32 vector: player state, tile grid, and fixed
                 slots for enemies and bubbles (positions scaled to [0, 1]).

    Reward is the in-game score delta (display points / 100 to keep
    magnitudes sane), with small optional shaping terms.
    """

    metadata = {"render_modes": ["rgb_array", "ansi"], "render_fps": 60}

    def __init__(
        self,
        level: int = 1,
        obs_type: str = "screen",
        frame_skip: int = 4,
        lives: int = 1,
        auto_advance: bool = False,
        max_episode_frames: int = 60 * 60 * 4,  # ~4 minutes of game time
        death_penalty: float = 1.0,
        clear_bonus: float = 10.0,
        capture_bonus: float = 0.1,
        render_mode: str | None = None,
    ):
        super().__init__()
        if obs_type not in ("screen", "state"):
            raise ValueError(f"unknown obs_type {obs_type!r}")
        self.obs_type = obs_type
        self.frame_skip = frame_skip
        self.max_episode_frames = max_episode_frames
        self.death_penalty = death_penalty
        self.clear_bonus = clear_bonus
        self.capture_bonus = capture_bonus
        self.render_mode = render_mode

        self._levels = load_levels()
        self.game = Game(
            level=level, lives=lives, levels=self._levels, auto_advance=auto_advance
        )

        self.action_space = spaces.Discrete(len(ACTIONS))
        if obs_type == "screen":
            self.observation_space = spaces.Box(
                0, 1, shape=(SCREEN_H, SCREEN_W), dtype=np.uint8
            )
        else:
            n = 8 + GRID_ROWS * GRID_COLS + MAX_ENEMIES * 5 + MAX_BUBBLES * 5
            self.observation_space = spaces.Box(
                -1.0, 1.0, shape=(n,), dtype=np.float32
            )

    # ------------------------------------------------------------ obs

    def _obs(self) -> np.ndarray:
        if self.obs_type == "screen":
            return draw_screen(self.game).astype(np.uint8)
        g = self.game
        p = g.player
        player = [
            p.x / SCREEN_W,
            (p.y + 16) / 92.0,
            p.facing,
            (p.jump & 3) / 3.0,
            p.shoot_cooldown / 14.0,
            1.0 if p.invincible else 0.0,
            1.0 if p.dead_ticks >= 0 else 0.0,
            g.alive_enemies / 8.0,
        ]
        grid = (g.grid == 0).astype(np.float32).ravel()

        enemies = np.zeros((MAX_ENEMIES, 5), dtype=np.float32)
        for i, e in enumerate(g.enemies[:MAX_ENEMIES]):
            enemies[i] = (
                1.0,
                e.x / SCREEN_W,
                (e.y + 16) / 92.0,
                e.facing,
                1.0 if e.angry else (0.5 if e.falling_in else 0.0),
            )
        bubbles = np.zeros((MAX_BUBBLES, 5), dtype=np.float32)
        for i, bub in enumerate(g.bubbles[:MAX_BUBBLES]):
            bubbles[i] = (
                1.0,
                bub.x / SCREEN_W,
                (bub.y + 16) / 92.0,
                1.0 if bub.captured is not None else 0.0,
                min(bub.life or 256, 256) / 256.0,
            )
        return np.concatenate(
            [np.array(player, dtype=np.float32), grid, enemies.ravel(), bubbles.ravel()]
        )

    # ------------------------------------------------------------ api

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        level = (options or {}).get("level")
        self.game.reset(level=level, seed=int(self.np_random.integers(2**31)))
        self._frames = 0
        return self._obs(), self._info()

    def step(self, action: int):
        buttons = ACTIONS[int(action)]
        reward = 0.0
        terminated = False
        for _ in range(self.frame_skip):
            ev = self.game.step(buttons)
            self._frames += 1
            reward += ev.score_delta / 100.0
            reward += ev.captured * self.capture_bonus
            if ev.died:
                reward -= self.death_penalty
            if ev.level_complete:
                reward += self.clear_bonus
                if not self.game.auto_advance:
                    terminated = True
            if self.game.game_over:
                terminated = True
            if terminated:
                break
        truncated = self._frames >= self.max_episode_frames and not terminated
        return self._obs(), reward, terminated, truncated, self._info()

    def _info(self) -> dict[str, Any]:
        g = self.game
        return {
            "score": g.score,
            "lives": g.lives,
            "level": g.level_num,
            "enemies_alive": g.alive_enemies,
            "frame": getattr(self, "_frames", 0),
        }

    def render(self):
        if self.render_mode == "ansi":
            screen = draw_screen(self.game)
            chars = np.where(screen, "#", " ")
            return "\n".join("".join(row) for row in chars[::2])  # halve height
        return draw_rgb(self.game)


def make(**kwargs) -> BubbleBobbleEnv:
    return BubbleBobbleEnv(**kwargs)
