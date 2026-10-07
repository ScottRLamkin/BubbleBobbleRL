"""Render game state to a 64x96 1-bit screen and to RGB frames.

Sprites use simple hand-drawn 8x8 glyphs rather than the original graphics
from bub_gfx.h - visually distinct shapes are all that matters for pixels-in
RL and for eyeballing the game.  Like the original LCD renderer, the
playfield background is dark and walls are drawn as a light pattern.
"""

from __future__ import annotations

import numpy as np

from .game import Game, SCREEN_H, SCREEN_W
from .levels import TILE_WALL

_G = [
    "........",
    ".XXXXXX.",
    "XX.XX.XX",
    "XXXXXXXX",
    "X.XXXX.X",
    "XX....XX",
    ".XXXXXX.",
    "........",
]
_PLAYER = [
    "..XXXX..",
    ".XXXXXX.",
    "XX.XX.XX",
    "XXXXXXXX",
    "XXXXXXXX",
    ".XXXXXX.",
    ".XX..XX.",
    "........",
]
_ENEMY = [
    "X.X..X.X",
    ".XXXXXX.",
    "XX.XX.XX",
    "XXXXXXXX",
    "X.XXXX.X",
    ".XXXXXX.",
    "X.X..X.X",
    "........",
]
_BUBBLE = [
    "..XXXX..",
    ".X....X.",
    "X..X...X",
    "X.X....X",
    "X......X",
    "X......X",
    ".X....X.",
    "..XXXX..",
]
_CAPTURED = [
    "..XXXX..",
    ".X....X.",
    "X.X..X.X",
    "X..XX..X",
    "X..XX..X",
    "X.X..X.X",
    ".X....X.",
    "..XXXX..",
]
_PREBUBBLE = [
    "........",
    "........",
    "..XXX...",
    ".X...X..",
    ".X.X.X..",
    ".X...X..",
    "..XXX...",
    "........",
]
_FRUIT = [
    "........",
    "...X....",
    "..XXX...",
    ".XXXXX..",
    ".XXXXX..",
    ".XXXXX..",
    "..XXX...",
    "........",
]
_STONE = [
    "........",
    "........",
    "...XX...",
    "..XXXX..",
    "..XXXX..",
    "...XX...",
    "........",
    "........",
]
_FIRE = [
    "........",
    "........",
    "........",
    "X.XXXX..",
    ".XXXXXXX",
    "X.XXXX..",
    "........",
    "........",
]
_LASER = [
    "...X....",
    "...X....",
    "...X....",
    "...X....",
    "...X....",
    "...X....",
    "...X....",
    "...X....",
]
_BEER = [
    "........",
    ".XXXXX..",
    ".X...XX.",
    ".X...X.X",
    ".X...XX.",
    ".X...X..",
    ".XXXXX..",
    "........",
]
_DEAD = [
    "X......X",
    ".X....X.",
    "..X..X..",
    "...XX...",
    "...XX...",
    "..X..X..",
    ".X....X.",
    "X......X",
]


def _glyph(rows: list[str]) -> np.ndarray:
    return np.array([[c == "X" for c in row] for row in rows], dtype=bool)


GLYPHS = {name: _glyph(g) for name, g in {
    "player": _PLAYER, "enemy": _ENEMY, "bubble": _BUBBLE,
    "captured": _CAPTURED, "prebubble": _PREBUBBLE, "fruit": _FRUIT,
    "dead": _DEAD, "pickup": _FRUIT,
    "stone": _STONE, "fire": _FIRE, "laser": _LASER, "beer": _BEER,
}.items()}

# 4x4 wall texture (light brick on the dark background, like the LCD).
_WALL_TILE = np.array(
    [[1, 1, 1, 0], [1, 0, 1, 1], [1, 1, 0, 1], [0, 1, 1, 1]], dtype=bool
)


def _blit(screen: np.ndarray, glyph: np.ndarray, x: int, y: int) -> None:
    h, w = glyph.shape
    for r in range(h):
        sy = y + r
        if not 0 <= sy < SCREEN_H:
            continue
        x0, x1 = max(0, x), min(SCREEN_W, x + w)
        if x0 < x1:
            row = glyph[r, x0 - x : x1 - x]
            screen[sy, x0:x1] |= row


def draw_screen(game: Game) -> np.ndarray:
    """Boolean (64, 96) frame of the current state."""
    screen = np.zeros((SCREEN_H, SCREEN_W), dtype=bool)
    wall = np.kron(game.grid == TILE_WALL, np.ones((4, 4), dtype=bool))
    screen |= wall & np.tile(_WALL_TILE, (16, 24))

    for pk in game.pickups:
        if not pk.taken:
            _blit(screen, GLYPHS["pickup"], pk.x, pk.y)
    for fr in game.fruits:
        _blit(screen, GLYPHS["fruit"], fr.x, fr.y)
    for pb in game.prebubbles:
        _blit(screen, GLYPHS["prebubble"], pb.x, pb.y)
    for bub in game.bubbles:
        name = "captured" if bub.captured is not None else "bubble"
        if bub.breaking is not None and bub.break_age % 2:
            continue  # flicker while breaking
        _blit(screen, GLYPHS[name], bub.x, bub.y)
    for e in game.enemies:
        _blit(screen, GLYPHS["enemy"], e.x, e.y)
    for pr in game.projectiles:
        if pr.breaking and pr.age % 2:
            continue
        _blit(screen, GLYPHS[pr.kind], pr.x, pr.y)
    for de in game.dead_enemies:
        _blit(screen, GLYPHS["dead"], de.x, de.y)

    p = game.player
    if p.dead_ticks >= 0:
        _blit(screen, GLYPHS["dead"], p.x, p.y)
    elif not (p.invincible % 2):  # flicker while invincible
        _blit(screen, GLYPHS["player"], p.x, p.y)
    return screen


# Dark background / light foreground, loosely the LCD's green-grey look.
_BG = np.array([28, 34, 40], dtype=np.uint8)
_FG = np.array([170, 220, 160], dtype=np.uint8)


def draw_rgb(game: Game, scale: int = 4) -> np.ndarray:
    """RGB uint8 frame, upscaled by `scale`."""
    screen = draw_screen(game)
    rgb = np.where(screen[..., None], _FG, _BG).astype(np.uint8)
    if scale > 1:
        rgb = np.kron(rgb, np.ones((scale, scale, 1), dtype=np.uint8))
    return rgb
