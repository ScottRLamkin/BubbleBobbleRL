import numpy as np
import pytest

from bubblebobblerl.levels import (
    GRID_COLS,
    GRID_ROWS,
    TILE_WALL,
    load_levels,
)


@pytest.fixture(scope="module")
def levels():
    return load_levels()


def test_all_100_levels_decode(levels):
    assert len(levels) == 100


def test_grid_shapes_and_values(levels):
    for lv in levels:
        assert lv.grid.shape == (GRID_ROWS, GRID_COLS)
        assert lv.grid.max() <= 4


def test_borders_are_solid_outside_holes(levels):
    hole_cols = set(range(6, 10)) | set(range(14, 18))
    for lv in levels:
        for row in (0, GRID_ROWS - 1):
            for col in range(GRID_COLS):
                if col not in hole_cols:
                    assert lv.grid[row, col] == TILE_WALL, (lv.number, row, col)
        assert (lv.grid[:, 0] == TILE_WALL).all()
        assert (lv.grid[:, GRID_COLS - 1] == TILE_WALL).all()


def test_level_one_matches_known_layout(levels):
    lv = levels[0]
    assert len(lv.spawns) == 3
    assert all(s.kind == 0 for s in lv.spawns)  # three Bubble Busters
    assert lv.holes == 0  # no holes on level 1
    # Bottom interior row plus border row are floor.
    assert (lv.grid[15] == TILE_WALL).all()
    # The two platform rows: solid cols 6-17, gaps at cols 3-5 and 18-20.
    for row in (7, 11):
        assert (lv.grid[row, 6:18] == TILE_WALL).all()
        assert (lv.grid[row, 3:6] != TILE_WALL).all()
        assert (lv.grid[row, 18:21] != TILE_WALL).all()


def test_spawns_in_bounds(levels):
    for lv in levels:
        for s in lv.spawns:
            if lv.number == 100:  # boss level, special-cased by the game
                continue
            assert 0 <= s.x < 96
            assert 0 <= s.y_pix < 64
            assert 0 <= s.kind < 8


def test_player_start_is_clear_on_level_one(levels):
    # Bub spawns at (8, 52). A handful of levels (e.g. 20) genuinely start
    # him embedded in a wall; the engine's CheckBelow "feet inside a tile
    # means falling" rule lets him sink through, like the original.
    lv = levels[0]
    assert lv.grid[52 // 4, 8 // 4] != TILE_WALL
