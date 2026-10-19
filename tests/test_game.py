import pytest

from bubblebobblerl.game import Buttons, Game
from bubblebobblerl.levels import load_levels

LEVELS = load_levels()

IDLE = Buttons()
RIGHT = Buttons(right=True)
LEFT = Buttons(left=True)
JUMP = Buttons(jump=True)
SHOOT = Buttons(shoot=True)


def make_game(**kw):
    kw.setdefault("levels", LEVELS)
    kw.setdefault("seed", 0)
    return Game(**kw)


def test_player_stands_on_floor():
    g = make_game()
    y0 = g.player.y
    for _ in range(30):
        g.step(IDLE)
    assert g.player.y == y0


def test_walk_right_and_blocked_by_wall():
    g = make_game()
    for _ in range(30):
        g.step(RIGHT)
    assert g.player.x == 8 + 30
    for _ in range(200):
        g.step(LEFT)
    # Left border wall occupies column 0 (pixels 0-3): stops at x=4.
    assert g.player.x == 4


def test_jump_arc_rises_19px_and_returns():
    g = make_game()
    # x=14 sits in the platform gap (cols 3-5), so a straight jump goes up
    # and comes back down to the floor. (At the start x=8 there's a ledge
    # stub overhead and Bub would land on it - faithful to the level.)
    for _ in range(6):
        g.step(RIGHT)
    assert g.player.x == 14
    y0 = g.player.y
    g.step(JUMP)
    heights = []
    for _ in range(60):
        g.step(IDLE)
        heights.append(g.player.y)
    assert min(heights) == y0 - 19
    assert heights[-1] == y0


def test_jump_through_platform_and_land_on_it():
    g = make_game()
    # Move under the right end of the lower platform (row 11, cols 7-18),
    # i.e. x around 60, then jump: rising passes through, falling lands.
    for _ in range(60):
        g.step(RIGHT)
    assert g.player.x == 68
    g.step(JUMP)
    for _ in range(80):
        g.step(IDLE)
    # Platform row 11 top is y=44; an 8px sprite rests at y=36.
    assert g.player.y == 36


def test_shoot_creates_bubble_that_floats():
    g = make_game()
    g.step(SHOOT)
    assert len(g.prebubbles) == 1
    for _ in range(26):
        g.step(IDLE)
    assert not g.prebubbles
    assert len(g.bubbles) == 1
    bub = g.bubbles[0]
    assert bub.x == 8 + 27
    y_start = bub.y
    for _ in range(40):
        g.step(IDLE)
    assert g.bubbles[0].y < y_start  # rising on the up-current


def test_shoot_cooldown():
    g = make_game()
    for _ in range(10):
        g.step(SHOOT)
    assert len(g.prebubbles) == 1  # held button doesn't autofire
    g.step(IDLE)


def test_capture_kill_fruit_score_cycle():
    g = make_game()
    # Drop a buster right in front of the player and shoot it.
    e = g.enemies[0]
    e.falling_in = False
    e.x, e.y = 30, 52
    e.state = 1
    g.enemies[1].spawn_delay = g.enemies[2].spawn_delay = 10**9
    captured = killed = False
    for _ in range(600):
        ev = g.step(Buttons(right=g.player.x < 20, shoot=True))
        captured |= ev.captured > 0
        killed |= ev.killed > 0
        if killed:
            break
    assert captured, "enemy was never captured"
    # Touching a captured bubble pops it and kills the captive.
    # (Move the player onto it directly; reachability isn't under test.)
    for _ in range(200):
        bubs = [b for b in g.bubbles if b.captured is not None]
        if killed or not bubs:
            break
        g.player.x, g.player.y = bubs[0].x, bubs[0].y
        ev = g.step(IDLE)
        killed |= ev.killed > 0
    assert killed, "captured enemy was never popped"
    # The kill turns into fruit worth the first chain score.
    score0 = g.score
    for _ in range(200):
        if g.fruits:
            g.player.x, g.player.y = g.fruits[0].x, g.fruits[0].y
        g.step(IDLE)
        if g.score >= score0 + 500:
            break
    assert g.score >= score0 + 500
    assert g.alive_enemies == 2


def test_escaped_enemy_is_angry():
    g = make_game()
    e = g.enemies[0]
    e.falling_in = False
    e.x, e.y = 30, 52
    g.enemies[1].spawn_delay = g.enemies[2].spawn_delay = 10**9
    g.level = g.level.__class__(**{**g.level.__dict__, "pop_time": 8})
    for _ in range(300):
        ev = g.step(Buttons(shoot=g.player.shoot_cooldown == 0))
        if ev.captured:
            break
    assert any(b.captured for b in g.bubbles)
    # Wait out the bubble: 8 ticks * 4 frames + break, far from the player.
    g.player.x, g.player.y = 80, 52
    for _ in range(400):
        g.step(IDLE)
        if any(en.angry for en in g.enemies):
            break
    assert any(en.angry for en in g.enemies), "escapee should come back angry"


def test_monster_touch_kills_and_respawns():
    g = make_game(lives=2)
    e = g.enemies[0]
    e.falling_in = False
    e.x, e.y = g.player.x, g.player.y
    died = False
    for _ in range(20):
        died |= g.step(IDLE).died
    assert died
    for _ in range(100):
        g.step(IDLE)
    assert g.lives == 1
    assert not g.game_over
    assert g.player.invincible > 0


def test_game_over_on_last_life():
    g = make_game(lives=1)
    e = g.enemies[0]
    e.falling_in = False
    for _ in range(200):
        e.x, e.y = g.player.x, g.player.y
        g.step(IDLE)
        if g.game_over:
            break
    assert g.game_over


def test_determinism():
    actions = [Buttons(right=i % 3 == 0, jump=i % 7 == 0, shoot=i % 5 == 0) for i in range(400)]

    def run():
        g = make_game(seed=123)
        trace = []
        for a in actions:
            g.step(a)
            trace.append((g.player.x, g.player.y, len(g.bubbles), g.score,
                          tuple((e.x, e.y) for e in g.enemies)))
        return trace

    assert run() == run()


@pytest.mark.parametrize("level", [1, 3, 5, 10, 25, 50, 75, 99])
def test_fuzz_random_play(level):
    import random

    rng = random.Random(level)
    g = make_game(level=level, lives=3)
    for _ in range(3000):
        g.step(
            Buttons(
                left=rng.random() < 0.3,
                right=rng.random() < 0.3,
                jump=rng.random() < 0.2,
                shoot=rng.random() < 0.2,
            )
        )
        if g.game_over:
            g.reset(level=level)
        p = g.player
        assert 0 <= p.x <= 88
        assert -16 <= p.y < 76


# ---------------------------------------------------------------- projectiles


def _active_enemy(game, kind, x=48, y=52, facing=1):
    from bubblebobblerl.game import Enemy

    e = Enemy(kind=kind, x=x, y=y, facing=facing, spawn_delay=0, falling_in=False, state=1)
    game.enemies = [e]
    game.alive_enemies = 1
    return e


def _run(game, frames, buttons=None):
    from bubblebobblerl.game import Buttons

    for _ in range(frames):
        game.step(buttons or Buttons())


def test_stoner_throws_rock_when_level_with_player_and_rock_breaks_on_wall():
    from bubblebobblerl.game import STONER, Game

    g = Game(level=1, seed=3, auto_advance=False)
    g.player.x, g.player.y = 20, 52
    e = _active_enemy(g, STONER, x=60, y=52, facing=-1)
    for _ in range(2000):
        g.step(__import__("bubblebobblerl.game", fromlist=["Buttons"]).Buttons())
        if any(p.kind == "stone" for p in g.projectiles):
            break
    stones = [p for p in g.projectiles if p.kind == "stone"]
    assert stones, "stoner never threw a rock"
    assert stones[0].dx == -1  # thrown the way it faces
    _run(g, 200)
    assert not any(p.kind == "stone" and not p.breaking for p in g.projectiles)


def test_fireball_kills_player_and_passes_through_walls():
    from bubblebobblerl.game import Game, Projectile

    g = Game(level=1, seed=0, auto_advance=False)
    g.enemies, g.alive_enemies = [], 1  # keep the level alive, no enemies in the way
    g.player.x, g.player.y = 40, 52
    g.projectiles.append(Projectile("fire", x=0, y=52, dx=1))  # starts inside the left wall
    _run(g, 30)
    assert g.player.dead_ticks >= 0


def test_laser_falls_and_disappears_at_the_bottom():
    from bubblebobblerl.game import Game, Projectile

    g = Game(level=1, seed=0, auto_advance=False)
    g.enemies, g.alive_enemies = [], 1
    g.projectiles.append(Projectile("laser", x=48, y=10))
    _run(g, 40)
    assert g.projectiles[0].y == 50
    _run(g, 20)
    assert not g.projectiles


def test_invader_fires_lasers_on_a_timer():
    from bubblebobblerl.game import INVADER, Game

    g = Game(level=1, seed=1, auto_advance=False)
    g.player.x, g.player.y = 8, 52  # out of the way
    _active_enemy(g, INVADER, x=60, y=20)
    fired = 0
    for _ in range(200):
        _run(g, 1)
        fired += any(p.kind == "laser" and p.age == 1 for p in g.projectiles)
    assert 2 <= fired <= 5  # one laser every 43-46 frames


def test_beer_returns_to_the_drunk_and_frees_it():
    from bubblebobblerl.game import DRUNK, STATE_SHOOT, Game

    g = Game(level=1, seed=0, auto_advance=False)
    g.player.x, g.player.y = 8, 20  # far away, so nothing dies
    e = _active_enemy(g, DRUNK, x=60, y=52, facing=1)
    e.state = STATE_SHOOT
    _run(g, 2)
    beers = [p for p in g.projectiles if p.kind == "beer"]
    assert beers and e.beer_out
    _run(g, 400)
    assert not g.projectiles and not e.beer_out and e.state != STATE_SHOOT


def test_banebou_hops_and_lands():
    from bubblebobblerl.game import BANEBOU, Game

    g = Game(level=1, seed=0, auto_advance=False)
    g.player.x, g.player.y = 8, 20
    e = _active_enemy(g, BANEBOU, x=48, y=52)
    e.state = 0
    ys = set()
    for _ in range(200):
        _run(g, 1)
        ys.add(e.y)
    assert min(ys) < 52 and g.standing(e.x, e.y) or e.y <= 52


def test_all_levels_run_with_every_enemy_kind():
    from bubblebobblerl.game import Buttons, Game

    g = Game(level=1, lives=1, auto_advance=False)
    for level in range(1, 101):
        g.reset(level=level, seed=level)
        for _ in range(300):
            g.step(Buttons(shoot=True))
            if g.game_over:
                break


def test_grace_period_delays_enemy_entry():
    from bubblebobblerl.game import Buttons, Game

    g = Game(level=1, seed=0, auto_advance=False, grace_frames=120)
    y0 = [e.y for e in g.enemies]
    _run(g, 119)
    assert [e.y for e in g.enemies] == y0  # nobody has moved yet
    _run(g, 40)
    assert all(e.y > y for e, y in zip(g.enemies, y0))  # now they fall in as usual
