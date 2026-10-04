"""Decode the 100 levels of DWedit's Bubble Bobble from the Z80 source.

The level data lives in ``bubble/bbsource/bub_map.h`` as assembler ``.db``
byte tables.  The format (verified against the GetMap/DecompressMap/
ConvertMap/MakeHoles routines in bub_lev.z80, not just the header comment):

Per level:
  byte 0      low nibble = enemy count - 1, high nibble = special bubble flags
  byte 1      hole configuration, 2 bits per hole (TL, TR, BL, BR from LSB):
              bit pair value 1 = "up" hole, 2 = "down" hole, 0 = solid wall
  bytes 2-4   hurry timer, baron timer, pop timer (captured-bubble lifetime)
  bytes 5-6   wall pattern graphic (two 4-pixel rows, nibble per row)
  bytes 7-8   fruit pickup: x, y/2
  bytes 9-10  item pickup: x, y/2
  2*n bytes   monsters: x | facing<<7,  y/2 | type<<5
  RLE map     run = (byte & 0x1F) + 1, tile = byte >> 5, terminated by 0xFF

Tiles: 0 = solid wall; 1-4 = air with a bubble current (1 up, 2 left,
3 right, 4 down).

The RLE encodes a 22x14 interior.  ConvertMap expands it in place into a
24x16 bordered map (border tile 0 = solid), then MakeHoles punches the four
2-bit-configured holes (4 tiles wide) into rows 0 and 15 at columns 6-9 and
14-17.  Some levels (e.g. level 1) encode fewer than 14 rows; the game reads
whatever is in RAM for the missing bottom rows, which is zero (solid) on a
fresh start - we reproduce that by padding with 0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

GRID_ROWS = 16
GRID_COLS = 24
INTERIOR_ROWS = 14
INTERIOR_COLS = 22
TILE_SIZE = 4  # pixels per tile, 96x64 screen

TILE_WALL = 0
TILE_UP = 1
TILE_LEFT = 2
TILE_RIGHT = 3
TILE_DOWN = 4

MONSTER_NAMES = (
    "buster",        # Bubble Buster (Zen-Chan): walks, hops gaps, jumps
    "beluga",        # Beluga (Monsta): floats diagonally, bounces
    "stoner",        # Stoner (Mighta): walker that throws rocks
    "drunk",         # Drunk: walker that throws boomerang mugs
    "hullaballoon",  # Hullaballoon: floater
    "banebou",       # Banebou: bouncer
    "hidegonsu",     # Hidegonsu: walker with fast fireballs
    "invader",       # Invader: fast, drops lasers
)

_MAP_FILE = Path(__file__).parent / "bubble" / "bbsource" / "bub_map.h"

# .db lines look like: ` .db $02,$00,$1E,...`
_DB_RE = re.compile(r"^\s*\.db\s+(.*)$", re.IGNORECASE)
_BYTE_RE = re.compile(r"\$([0-9A-Fa-f]{1,2})|(\d+)")


@dataclass(frozen=True)
class Spawn:
    """A monster spawn point.

    Monsters enter from above the playfield: they are created at y = -y_pix
    and drift down, becoming active exactly at (x, y_pix).
    """

    x: int
    y_pix: int
    kind: int  # index into MONSTER_NAMES
    facing_left: bool


@dataclass(frozen=True)
class Level:
    number: int  # 1-based
    ammo: int  # special-bubble flags: water/thunder/fire/clear from bit 0
    holes: int  # raw hole-configuration byte
    hurry: int
    baron: int
    pop_time: int  # captured-bubble lifetime in 4-frame ticks (0 means 256)
    pattern: tuple[int, int]  # wall graphic bytes
    fruit: tuple[int, int]  # (x, y) static fruit pickup
    item: tuple[int, int]  # (x, y) static item pickup
    spawns: tuple[Spawn, ...]
    grid: np.ndarray  # (16, 24) uint8, read-only

    @property
    def solid(self) -> np.ndarray:
        """Boolean (16, 24) array: True where the tile is a wall."""
        return self.grid == TILE_WALL


def _parse_db_bytes(text: str) -> list[int]:
    """Collect every .db byte after the ``Maps:`` label."""
    lines = text.splitlines()
    for start, line in enumerate(lines):
        if line.strip().startswith("Maps:"):
            break
    else:
        raise ValueError("Maps: label not found in bub_map.h")

    data: list[int] = []
    started = False
    for line in lines[start:]:
        m = _DB_RE.match(line)
        if not m:
            stripped = line.strip()
            # Allow the label itself, blanks, comments, and the
            # `level_count = 100` assignment between label and data.
            if started and stripped and not stripped.startswith(";"):
                break
            continue
        started = True
        for hex_part, dec_part in _BYTE_RE.findall(m.group(1).split(";")[0]):
            data.append(int(hex_part, 16) if hex_part else int(dec_part))
    return data


def _punch_hole(grid: np.ndarray, row: int, col: int, bits: int) -> None:
    if bits & 2:
        value = TILE_DOWN
    elif bits & 1:
        value = TILE_UP
    else:
        value = TILE_WALL
    grid[row, col : col + 4] = value


def _build_grid(cells: list[int], holes: int) -> np.ndarray:
    if len(cells) > INTERIOR_ROWS * INTERIOR_COLS:
        raise ValueError(f"interior too large: {len(cells)} cells")
    if len(cells) % INTERIOR_COLS != 0:
        raise ValueError(f"interior not row-aligned: {len(cells)} cells")
    # Missing bottom rows decode as solid (fresh-RAM behaviour, see module doc).
    cells = cells + [TILE_WALL] * (INTERIOR_ROWS * INTERIOR_COLS - len(cells))
    interior = np.array(cells, dtype=np.uint8).reshape(INTERIOR_ROWS, INTERIOR_COLS)

    grid = np.zeros((GRID_ROWS, GRID_COLS), dtype=np.uint8)  # 0 = wall border
    grid[1 : 1 + INTERIOR_ROWS, 1 : 1 + INTERIOR_COLS] = interior

    _punch_hole(grid, 0, 6, holes)
    _punch_hole(grid, 0, 14, holes >> 2)
    _punch_hole(grid, 15, 6, holes >> 4)
    _punch_hole(grid, 15, 14, holes >> 6)
    grid.setflags(write=False)
    return grid


def _decode_level(data: list[int], pos: int, number: int) -> tuple[Level, int]:
    b = data
    n_enemies = (b[pos] & 0x0F) + 1
    ammo = b[pos] >> 4
    holes = b[pos + 1]
    hurry, baron, pop_time = b[pos + 2 : pos + 5]
    pattern = (b[pos + 5], b[pos + 6])
    fruit = (b[pos + 7] & 0x7F, (b[pos + 8] * 2) & 0xFF)
    item = (b[pos + 9] & 0x7F, (b[pos + 10] * 2) & 0xFF)

    pos += 11
    spawns = []
    for _ in range(n_enemies):
        b1, b2 = b[pos], b[pos + 1]
        spawns.append(
            Spawn(
                x=b1 & 0x7F,
                y_pix=(b2 & 0x1F) * 2,
                kind=b2 >> 5,
                facing_left=bool(b1 & 0x80),
            )
        )
        pos += 2

    cells: list[int] = []
    while b[pos] != 0xFF:
        run = (b[pos] & 0x1F) + 1
        tile = b[pos] >> 5
        cells.extend([tile] * run)
        pos += 1
    pos += 1  # consume the 0xFF terminator

    level = Level(
        number=number,
        ammo=ammo,
        holes=holes,
        hurry=hurry,
        baron=baron,
        pop_time=pop_time,
        pattern=pattern,
        fruit=fruit,
        item=item,
        spawns=tuple(spawns),
        grid=_build_grid(cells, holes),
    )
    return level, pos


def load_levels(path: Path | None = None) -> list[Level]:
    """Decode all levels from the original source data."""
    text = (path or _MAP_FILE).read_text(errors="replace")
    data = _parse_db_bytes(text)
    levels: list[Level] = []
    pos = 0
    number = 1
    while pos < len(data) - 1:
        level, pos = _decode_level(data, pos, number)
        levels.append(level)
        number += 1
    return levels


_ASCII_TILES = {TILE_WALL: "#", TILE_UP: " ", TILE_LEFT: "<", TILE_RIGHT: ">", TILE_DOWN: "v"}


def ascii_map(level: Level, currents: bool = False) -> str:
    """Render a level as text. With currents=False, air is blank."""
    rows = []
    for r in range(GRID_ROWS):
        row = ""
        for c in range(GRID_COLS):
            t = int(level.grid[r, c])
            row += _ASCII_TILES[t] if (currents or t == TILE_WALL) else " "
        rows.append(row)
    for s in level.spawns:
        r, c = s.y_pix // TILE_SIZE, s.x // TILE_SIZE
        if 0 <= r < GRID_ROWS and 0 <= c < GRID_COLS:
            rows[r] = rows[r][:c] + MONSTER_NAMES[s.kind][0].upper() + rows[r][c + 1 :]
    return "\n".join(rows)


if __name__ == "__main__":
    import sys

    levels = load_levels()
    print(f"decoded {len(levels)} levels")
    for arg in sys.argv[1:]:
        lv = levels[int(arg) - 1]
        print(f"\nLevel {lv.number}: spawns={[(MONSTER_NAMES[s.kind], s.x, s.y_pix) for s in lv.spawns]}")
        print(ascii_map(lv, currents=True))
