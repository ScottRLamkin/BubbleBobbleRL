"""Gymnasium environment around the Bubble Bobble reimplementation."""

from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .game import BEER_IDLE, Buttons, Game, PICKUP_SCORE, SCREEN_H, SCREEN_W
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
MAX_LOOT = 8  # dropped fruit plus the two static pickups
MAX_PREBUBBLES = 4
MAX_PROJECTILES = 8


class BubbleBobbleEnv(gym.Env):
    """One level (or a run of levels) of calculator Bubble Bobble.

    obs_type:
      "screen" - (64, 96) uint8 binary frame, the 1-bit LCD picture.
      "state"  - flat float32 vector: player state, tile grid (with air
                 currents), and fixed slots for enemies, bubbles, loot
                 (fruit and pickups), in-flight bubbles and enemy
                 projectiles (positions scaled to [0, 1]).

    levels: optional pool of level numbers; each reset() draws one at random
    (an explicit ``options={"level": n}`` still wins).

    Reward is the in-game score delta (display points / 100 to keep
    magnitudes sane), with small optional shaping terms. time_penalty is
    subtracted once per step; it stands in for the unimplemented hurry-up.
    reward_pops=False drops the 10 points per bubble pop or bounce from the
    reward (not from the score), since they can be farmed forever.
    random_start=True puts the player on a random platform at reset instead
    of the fixed start, so a policy cannot rely on always starting bottom-left.
    """

    metadata = {"render_modes": ["rgb_array", "ansi"], "render_fps": 60}

    def __init__(
        self,
        level: int = 1,
        levels: list[int] | None = None,
        obs_type: str = "screen",
        frame_skip: int = 4,
        lives: int = 1,
        auto_advance: bool = False,
        max_episode_frames: int = 60 * 60 * 4,  # ~4 minutes of game time
        death_penalty: float = 1.0,
        clear_bonus: float = 10.0,
        capture_bonus: float = 0.1,
        time_penalty: float = 0.0,
        reward_pops: bool = True,
        random_start: bool = False,
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
        self.time_penalty = time_penalty
        self.reward_pops = reward_pops
        self.random_start = random_start
        self.level_pool = list(levels) if levels else None
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
            n = (
                8
                + GRID_ROWS * GRID_COLS
                + MAX_ENEMIES * 6
                + MAX_BUBBLES * 5
                + MAX_LOOT * 4
                + MAX_PREBUBBLES * 4
                + MAX_PROJECTILES * 5
            )
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
        # 0 = wall, 0.25/0.5/0.75/1 = air with an up/left/right/down current.
        grid = (g.grid / 4.0).astype(np.float32).ravel()

        enemies = np.zeros((MAX_ENEMIES, 6), dtype=np.float32)
        for i, e in enumerate(g.enemies[:MAX_ENEMIES]):
            enemies[i] = (
                1.0,
                e.x / SCREEN_W,
                (e.y + 16) / 92.0,
                e.facing,
                1.0 if e.angry else (0.5 if e.falling_in else 0.0),
                e.kind / 7.0,
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
        loot = np.zeros((MAX_LOOT, 4), dtype=np.float32)
        items = [(fr.x, fr.y, fr.value) for fr in g.fruits]
        items += [(pk.x, pk.y, PICKUP_SCORE) for pk in g.pickups if not pk.taken]
        for i, (x, y, value) in enumerate(items[:MAX_LOOT]):
            loot[i] = (1.0, x / SCREEN_W, (y + 16) / 92.0, min(value / 8000.0, 1.0))
        prebubbles = np.zeros((MAX_PREBUBBLES, 4), dtype=np.float32)
        for i, pb in enumerate(g.prebubbles[:MAX_PREBUBBLES]):
            prebubbles[i] = (1.0, pb.x / SCREEN_W, (pb.y + 16) / 92.0, pb.facing)
        shots = np.zeros((MAX_PROJECTILES, 5), dtype=np.float32)
        live = [
            pr for pr in g.projectiles
            if not pr.breaking and (pr.kind != "beer" or pr.age > BEER_IDLE)
        ]
        for i, pr in enumerate(live[:MAX_PROJECTILES]):
            shots[i] = (
                1.0,
                pr.x / SCREEN_W,
                (pr.y + 16) / 92.0,
                pr.dx * (2 if pr.kind == "fire" else 1) / 2.0,  # x speed / 2
                1.0 if pr.kind == "laser" else 0.0,  # falls
            )
        return np.concatenate(
            [
                np.array(player, dtype=np.float32),
                grid,
                enemies.ravel(),
                bubbles.ravel(),
                loot.ravel(),
                prebubbles.ravel(),
                shots.ravel(),
            ]
        )

    # ------------------------------------------------------------ api

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        level = (options or {}).get("level")
        if level is None and self.level_pool:
            level = int(self.np_random.choice(self.level_pool))
        self.game.reset(level=level, seed=int(self.np_random.integers(2**31)))
        if self.random_start:
            self._randomize_start()
        self._frames = 0
        return self._obs(), self._info()

    def _randomize_start(self) -> None:
        g = self.game
        spots = [
            (x, y)
            for y in range(0, SCREEN_H - 8, 4)
            for x in range(0, SCREEN_W - 8, 4)
            if g.standing(x, y)
            and not any(g.solid(x + dx, y + dy) for dx in (0, 7) for dy in (0, 7))
        ]
        if spots:
            x, y = spots[int(self.np_random.integers(len(spots)))]
            g.player.x, g.player.y = x, y
        g.player.facing = 1 if self.np_random.random() < 0.5 else -1

    def step(self, action: int):

        buttons = ACTIONS[int(action)]
        reward = -self.time_penalty
        terminated = False
        for _ in range(self.frame_skip):
            ev = self.game.step(buttons)
            self._frames += 1
            score = ev.score_delta if self.reward_pops else ev.score_delta - ev.pop_score
            reward += score / 100.0
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
