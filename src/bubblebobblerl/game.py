"""Pure-Python reimplementation of the core of DWedit's Bubble Bobble.

The mechanics are transcribed from the Z80 source in ``bubble/bbsource/``
(mainly bub_ai.z80 and bub_main.z80).  Where this file simplifies or
approximates the original, the comment says so explicitly.

Implemented: player movement/jumping, bubble shooting, floating bubbles with
per-tile air currents, capture/pop/explode chains, dead-enemy fruit, all
eight enemy kinds with their projectiles (Buster, Beluga, Stoner + rocks,
Drunk + boomerang beer, Hullaballoon, Banebou, Hidegonsu + fireballs,
Invader + lasers), falling-in spawns, anger states, lives and level-clear.

Not implemented (yet): special bubbles (water/fire/thunder), items and
potions, the hurry-up baron, pit bubbles, linkplay, and level 100's boss.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .levels import (
    GRID_COLS,
    GRID_ROWS,
    Level,
    TILE_DOWN,
    TILE_LEFT,
    TILE_RIGHT,
    TILE_WALL,
    load_levels,
)

SCREEN_W = 96
SCREEN_H = 64
PLAY_HEIGHT = 92  # sprite y wraps in [-16, 76)
PLAYER_START = (8, 52)  # DefaultBubTable
JUMP_COUNTER_START = 74  # 18*4+2 -> 19 frames of rising, 19 px
PREBUBBLE_FRAMES = 27  # (Bubble - Prebubble) * 9 frames of horizontal flight
BREAK_FRAMES = 16
DEAD_PLAYER_TICKS = 14  # 4-frame ticks of death animation
RESPAWN_INVINCIBLE = 72  # frames (approximation: original units unclear)
CLEAR_DELAY = 256  # frames between last kill and level advance
CHAIN_WINDOW = 16  # frames in which consecutive kills chain (popcount)

# PopScoreTable from bub_tabl.h, in displayed points (internal value * 10).
POP_SCORES = (500, 1000, 2000, 4000, 8000, 16000, 32000, 64000)
POP_EVENT_SCORE = 10  # Add1ToScore on any burst or bubble bounce
PICKUP_SCORE = 100  # approximation for the static fruit/item pickups

# Enemy kinds, as indexed in bub_map.h / levels.MONSTER_NAMES.
BUSTER, BELUGA, STONER, DRUNK, HULLABALLOON, BANEBOU, HIDEGONSU, INVADER = range(8)
FLOATER_KINDS = frozenset({BELUGA, HULLABALLOON})
SHOOTER_KINDS = frozenset({STONER, DRUNK, HIDEGONSU})

# Shooter timing from StonerShoot1 / HidegonsuShoot1: frames the player must
# stay level with the enemy before it may fire, length of the shooting
# animation, and the frame within it on which the projectile appears.
SHOOTER_TIMING = {
    STONER: (11, 16, 8),
    DRUNK: (11, 16, 8),  # Drunk reuses the Stoner code, only the shot differs
    HIDEGONSU: (17, 8, 4),
}
STATE_SHOOT = 6
INVADER_RELOAD = 43  # + random 0..3 frames
BEER_IDLE = 16  # frames a beer sits before it flies


@dataclass(frozen=True)
class Buttons:
    left: bool = False
    right: bool = False
    jump: bool = False
    shoot: bool = False


@dataclass
class Player:
    x: int = PLAYER_START[0]
    y: int = PLAYER_START[1]
    facing: int = 1  # 1 right, -1 left
    jump: int = 0  # packed counter, asm ix+4: &3 -> 0 ground, 1 fall, 2 rise
    shoot_cooldown: int = 0
    invincible: int = 0
    on_bubble: bool = False
    kill_pending: bool = False
    dead_ticks: int = -1  # >=0 while the death animation runs


@dataclass
class Enemy:
    kind: int
    x: int
    y: int
    facing: int
    spawn_delay: int  # 4-frame ticks until activation while falling in
    falling_in: bool = True
    state: int = 0  # buster: 0 fall 1 walk 2/3/4 hop 5 jump-up; beluga: 0 up 1 down
    counter: int = 0
    angry: bool = False
    want_up: bool = False
    want_down: bool = False
    walk_counter: int = 0  # asm ix+5: frames level with the player / shot timer
    reload: int = 0  # invader: frames until the next laser
    beer_out: bool = False  # drunk: frozen while its beer is away

    @property
    def floater(self) -> bool:
        return self.kind in FLOATER_KINDS


@dataclass
class Projectile:
    """Enemy shot: 'stone' (rolls, breaks on walls), 'fire' (fast, through
    walls), 'laser' (falls straight down), 'beer' (boomerang, returns to its
    Drunk).  All kill the player on contact and are not stopped by bubbles."""

    kind: str
    x: int
    y: int
    dx: int = 0  # horizontal direction, -1/0/1
    age: int = 0
    owner: Enemy | None = None  # beer only
    bounced: bool = False  # beer only
    breaking: bool = False  # stone that hit a wall: 16 harmless frames


@dataclass
class Prebubble:
    x: int
    y: int
    facing: int
    age: int = 0


@dataclass
class BubbleSprite:
    x: int
    y: int
    life: int  # 4-frame ticks; decremented before test, so 0 lasts 256
    captured: Enemy | None = None
    push: int = 0  # pending horizontal push from the player
    breaking: str | None = None  # None | "pop" (escape) | "explode" (kill)
    break_age: int = 0


@dataclass
class DeadEnemy:
    x: int
    y: int
    facing: int  # flies in the direction the player faced at pop time
    age: int = 0


@dataclass
class Fruit:
    x: int
    y: int
    value: int
    age: int = 0


@dataclass
class Pickup:
    x: int
    y: int
    taken: bool = False


@dataclass
class StepEvents:
    score_delta: int = 0
    pop_score: int = 0  # part of score_delta from bare pops and bubble bounces
    died: bool = False
    captured: int = 0
    killed: int = 0
    popped: int = 0
    level_complete: bool = False


class Game:
    """One game of Bubble Bobble.  Call step() once per 60 Hz-ish frame."""

    def __init__(
        self,
        level: int = 1,
        lives: int = 3,
        levels: list[Level] | None = None,
        seed: int | None = None,
        auto_advance: bool = True,
    ):
        self.levels = levels if levels is not None else load_levels()
        self.start_level = level
        self.start_lives = lives
        self.auto_advance = auto_advance
        self.rng = random.Random(seed)
        self.reset()

    # ------------------------------------------------------------- setup

    def reset(self, level: int | None = None, seed: int | None = None) -> None:
        if seed is not None:
            self.rng = random.Random(seed)
        self.level_num = level if level is not None else self.start_level
        self.lives = self.start_lives
        self.score = 0
        self.game_over = False
        self._load_level(self.level_num)

    def _load_level(self, number: int) -> None:
        self.level = self.levels[number - 1]
        self.grid = self.level.grid
        self.timer = 0
        self.player = Player()
        self.prev_jump = False
        self.prev_shoot = False
        self.enemies: list[Enemy] = [
            Enemy(
                kind=s.kind,
                x=s.x,
                y=-s.y_pix,  # falls in from above, activates at y_pix
                facing=-1 if s.facing_left else 1,
                spawn_delay=s.y_pix,
            )
            for s in self.level.spawns
        ]
        self.prebubbles: list[Prebubble] = []
        self.projectiles: list[Projectile] = []
        self.bubbles: list[BubbleSprite] = []
        self.dead_enemies: list[DeadEnemy] = []
        self.fruits: list[Fruit] = []
        self.pickups = [Pickup(*self.level.fruit), Pickup(*self.level.item)]
        self.alive_enemies = len(self.enemies)
        self.clear_countdown = -1
        self.chain = 0
        self.chain_timer = 0
        self.bounces = 0  # jumps off the top of a bubble (statistics only)

    # ------------------------------------------------------------ tiles

    def tile(self, x: int, y: int) -> int:
        # GetXY: any y outside the visible screen reads map row 0, which is
        # how the top/bottom wraparound works.
        row = y // 4 if 0 <= y < SCREEN_H else 0
        col = (x // 4) & 0x3F
        if col >= GRID_COLS:
            return TILE_WALL
        return int(self.grid[row, col])

    def solid(self, x: int, y: int) -> bool:
        return self.tile(x, y) == TILE_WALL

    def standing(self, x: int, y: int) -> bool:
        """CheckBelow: on ground, and feet not buried inside a tile."""
        for dx in (0, 7, 4):
            if self.solid(x + dx, y + 7):
                return False
        return any(self.solid(x + dx, y + 8) for dx in (0, 7, 4))

    @staticmethod
    def wrap_y(y: int) -> int:
        while y >= 76:
            y -= PLAY_HEIGHT
        while y < -16:
            y += PLAY_HEIGHT
        return y

    @staticmethod
    def _delta_wrapped(a: int, b: int) -> int:
        """Smallest difference a-b in the 92-pixel wrapped y space."""
        d = a - b
        if d > PLAY_HEIGHT // 2:
            d -= PLAY_HEIGHT
        elif d < -PLAY_HEIGHT // 2:
            d += PLAY_HEIGHT
        return d

    def _overlap(self, ax, ay, bx, by, margin) -> bool:
        return (
            abs(ax - bx) <= margin
            and abs(self._delta_wrapped(ay, by)) <= margin
        )

    # ------------------------------------------------------------- step

    def step(self, buttons: Buttons) -> StepEvents:
        ev = StepEvents()
        if self.game_over:
            return ev
        self.timer += 1
        jump_pressed = buttons.jump and not self.prev_jump
        shoot_pressed = buttons.shoot and not self.prev_shoot
        self.prev_jump = buttons.jump
        self.prev_shoot = buttons.shoot

        self._step_player(buttons, jump_pressed, shoot_pressed, ev)
        self._step_prebubbles()
        self._step_enemies(ev)
        self._step_projectiles()
        self._step_bubbles(ev)
        self._step_dead_enemies(ev)
        self._step_fruits(ev)
        self._step_pickups(ev)

        if self.chain_timer > 0:
            self.chain_timer -= 1
            if self.chain_timer == 0:
                self.chain = 0

        if self.clear_countdown > 0:
            self.clear_countdown -= 1
            if self.clear_countdown == 0:
                ev.level_complete = True
                if self.auto_advance and self.level_num < len(self.levels):
                    self.level_num += 1
                    self._load_level(self.level_num)
                else:
                    self.game_over = True
        return ev

    # ------------------------------------------------------------ player

    def _step_player(self, b: Buttons, jump_pressed: bool, shoot_pressed: bool, ev) -> None:
        p = self.player
        if p.dead_ticks >= 0:
            self._step_dead_player(ev)
            return
        if p.invincible > 0:
            p.invincible -= 1

        self._player_gravity(p, b.jump, jump_pressed, ev)

        # PlayerFlags: bubble pushback applies every other frame.
        # (Pushback flags are set during the bubble pass and consumed here.)
        p.on_bubble = False

        if p.kill_pending:
            p.kill_pending = False
            if p.invincible == 0:
                p.dead_ticks = 0
                ev.died = True
                return

        self._blow_bubbles(p, b.shoot, shoot_pressed)

        # Walking: both directions held cancel out (GetDir).
        direction = (-1 if b.left else 0) + (1 if b.right else 0)
        if direction:
            p.facing = direction  # facing updates even when blocked
            self._try_walk(p, direction)
        p.y = self.wrap_y(p.y)

    def _try_walk(self, p: Player, direction: int) -> None:
        probe_x = p.x + 8 if direction > 0 else p.x - 1
        if not self.solid(probe_x, p.y + 7):
            p.x += direction

    def _player_gravity(self, p: Player, jump_held: bool, jump_pressed: bool, ev) -> None:
        mode = p.jump & 3
        if mode == 0:  # grounded
            if self.standing(p.x, p.y):
                if jump_pressed and jump_held:
                    p.jump = JUMP_COUNTER_START
            else:
                p.jump = 1
                self._fall(p, jump_held, ev)
        elif mode == 1:  # falling
            if self.standing(p.x, p.y):
                p.jump = 0
            else:
                self._fall(p, jump_held, ev)
        else:  # rising: 19 frames up, ignores platforms (jump-through)
            p.y -= 1
            nxt = p.jump - 5
            p.jump = nxt & 0xFF if nxt < 0 else nxt + 1

    def _fall(self, p: Player, jump_held: bool, ev) -> None:
        p.y += 1
        if p.on_bubble and jump_held:  # bubble bounce
            self.bounces += 1
            self.score += POP_EVENT_SCORE
            ev.score_delta += POP_EVENT_SCORE
            ev.pop_score += POP_EVENT_SCORE
            p.jump = JUMP_COUNTER_START

    def _blow_bubbles(self, p: Player, shoot_held: bool, shoot_pressed: bool) -> None:
        if p.shoot_cooldown > 0:
            p.shoot_cooldown -= 1
            return
        if shoot_pressed and shoot_held:
            self.prebubbles.append(Prebubble(x=p.x, y=p.y, facing=p.facing))
            p.shoot_cooldown = 14

    def _step_dead_player(self, ev) -> None:
        p = self.player
        if self.timer % 4 != 0:
            return
        p.dead_ticks += 1
        if p.dead_ticks < DEAD_PLAYER_TICKS:
            return
        self.lives -= 1
        if self.lives <= 0:
            self.game_over = True
            return
        self.player = Player(invincible=RESPAWN_INVINCIBLE)
        if self.alive_enemies > 1:  # UnPissOffEnemies
            for e in self.enemies:
                e.angry = False

    # -------------------------------------------------------- prebubbles

    def _step_prebubbles(self) -> None:
        for pb in self.prebubbles:
            pb.age += 1
            # Stops at walls but keeps aging (becomes a bubble at the wall).
            probe_x = pb.x + 8 if pb.facing > 0 else pb.x - 1
            if not self.solid(probe_x, pb.y + 7):
                pb.x += pb.facing
        for pb in [p for p in self.prebubbles if p.age >= PREBUBBLE_FRAMES]:
            self.prebubbles.remove(pb)
            self.bubbles.append(BubbleSprite(x=pb.x, y=pb.y, life=0))

    # ----------------------------------------------------------- enemies

    def _step_enemies(self, ev) -> None:
        for e in list(self.enemies):
            if e.falling_in:
                self._step_falling_in(e)
                continue
            if e.kind == INVADER:
                self._invader_step(e, ev)
                continue
            # StandardEnemy: normal enemies act every other frame.
            if not e.angry and self.timer % 2 == 1:
                continue
            if self._enemy_hazards(e, ev):
                continue
            self._touch_player(e.x, e.y)
            if e.kind == BELUGA:
                self._beluga_ai(e)
            elif e.kind == HULLABALLOON:
                self._hulla_ai(e)
            elif e.kind == BANEBOU:
                self._banebou_ai(e)
            else:  # buster, stoner, drunk, hidegonsu share the walker machine
                self._buster_ai(e)
            e.y = self.wrap_y(e.y)

    def _touch_player(self, x: int, y: int) -> None:
        """MonsterHitPlayer: anything hostile overlapping Bub kills him."""
        if self._overlap(x, y, self.player.x, self.player.y, 5):
            self.player.kill_pending = True

    def _step_falling_in(self, e: Enemy) -> None:
        if self.timer % 2 == 1:
            return
        e.y += 1
        if self.timer % 4 != 0:
            return
        e.spawn_delay -= 1
        if e.spawn_delay <= 0:
            e.falling_in = False

    def _enemy_hazards(self, e: Enemy, ev) -> bool:
        """Prebubble capture. Returns True if the enemy left the enemy list."""
        for pb in self.prebubbles:
            if self._overlap(e.x, e.y, pb.x, pb.y, 7):
                self.prebubbles.remove(pb)
                self.enemies.remove(e)
                life = self.level.pop_time  # 0 decodes as 256 ticks
                self.bubbles.append(
                    BubbleSprite(x=e.x, y=e.y, life=life, captured=e)
                )
                ev.captured += 1
                return True
        return False

    # Buster (Zen-Chan) state machine, HandleBubbleBuster.  Stoner, Drunk and
    # Hidegonsu (HandleStoner/HandleDrunk/HandleHidegonsu) reuse it with a
    # smarter walk and a seventh state for shooting.
    def _buster_ai(self, e: Enemy) -> None:
        if e.state == STATE_SHOOT:
            self._shooter_shoot(e)
        elif e.state == 0:  # falling
            if self.standing(e.x, e.y):
                e.state = 1
                if self.rng.getrandbits(2) == 0:
                    self._look_around(e)
            else:
                e.y += 1
        elif e.state == 1:
            self._buster_walk(e)
        elif e.state in (2, 3, 4):  # hop across a gap: up, level, down
            if e.state == 2:
                e.y -= 1
            elif e.state == 4:
                e.y += 1
            self._enemy_forward(e)
            e.counter += 1
            if e.counter in (6, 6 + 8, 6 + 8 + 6):
                e.state += 1
                if e.state == 5:
                    e.state, e.counter = 0, 0
                    if self.rng.getrandbits(2) == 0:
                        self._look_around(e)
        elif e.state == 5:  # jump up through platforms
            e.counter += 1
            if e.counter < 18:
                return
            e.y -= 1
            if self.standing(e.x, e.y):
                e.state, e.counter = 0, 0

    def _buster_walk(self, e: Enemy) -> None:
        self._enemy_forward(e)
        if e.kind in (STONER, DRUNK):  # SmartWalk: looks every 16 frames
            if self.timer % 16 == 0:
                self._look_around(e)
        elif self.timer % 4 != 0 and self.rng.getrandbits(4) == 0:  # DumbWalk
            self._look_around(e)
        # Hop over upcoming gap, unless trying to follow the player down.
        if not e.want_down:
            probe_x = e.x + 8 if e.facing > 0 else e.x - 1
            if not self.solid(probe_x, e.y + 8):
                e.state, e.counter = 2, 0
                return
        if not self.standing(e.x, e.y):
            e.state = 0
            return
        if e.kind in SHOOTER_KINDS and self._shooter_aim(e):
            return
        # StandardJumpCode: occasionally jump if the player is above.
        if e.want_up and e.x % 8 < 4 and self.rng.getrandbits(3) == 0:
            for dy in range(4, 24, 4):
                if self.standing(e.x, e.y - dy):
                    e.state, e.counter = 5, 0
                    return

    def _look_around(self, e: Enemy) -> None:
        e.want_up = e.want_down = False
        p = self.player
        dy = self._delta_wrapped(e.y - 1, p.y + 8)
        if dy >= 0:
            e.want_up = True
        elif dy + 19 < 0:
            e.want_down = True
        elif e.x + 12 < p.x + 8:
            e.facing = 1
        else:
            e.facing = -1

    def _enemy_forward(self, e: Enemy) -> None:
        probe_x = e.x + 8 if e.facing > 0 else e.x - 1
        if e.floater:
            blocked = self.solid(probe_x, e.y + 7) or self.solid(probe_x, e.y)
        else:
            blocked = self.solid(probe_x, e.y + 7)
        if blocked:
            e.facing = -e.facing
        else:
            e.x += e.facing

    # ---- shooters: Stoner (rocks), Drunk (beer), Hidegonsu (fireballs)

    def _shooter_aim(self, e: Enemy) -> bool:
        """StonerShoot1: fire after being level with the player for a while.
        Returns True when the normal jump check should be skipped."""
        aim_frames, _, _ = SHOOTER_TIMING[e.kind]
        p = self.player
        if not -15 <= p.y - e.y < 17:  # TestHAligned
            return False
        e.walk_counter += 1
        if e.walk_counter < aim_frames:
            return False
        if self.rng.getrandbits(2) == 0:
            e.walk_counter = 0
            e.state = STATE_SHOOT
        return True

    def _shooter_shoot(self, e: Enemy) -> None:
        _, length, fire_at = SHOOTER_TIMING[e.kind]
        if e.kind == DRUNK:  # DrunkShoot: throw once, then wait for the beer
            if not e.beer_out:
                e.beer_out = True
                self.projectiles.append(
                    Projectile("beer", e.x + 8 * e.facing, e.y, dx=e.facing, owner=e)
                )
            return
        e.walk_counter += 1
        if e.walk_counter >= length:
            e.walk_counter = 0
            e.state = 1
            self._look_around(e)
        elif e.walk_counter == fire_at:
            kind = "stone" if e.kind == STONER else "fire"
            self.projectiles.append(Projectile(kind, e.x, e.y, dx=e.facing))

    # ---- Invader: HandleInvader.  Not gated like the others: it acts every
    # frame, twice per frame when angry, and drops lasers on a timer.

    def _invader_step(self, e: Enemy, ev) -> None:
        if self._enemy_hazards(e, ev):
            return
        self._touch_player(e.x, e.y)
        for _ in range(2 if e.angry else 1):
            e.reload -= 1
            if e.reload == 0:
                self.projectiles.append(Projectile("laser", e.x, e.y))
            if e.reload <= 0:
                e.reload = INVADER_RELOAD + self.rng.getrandbits(2)
            if self.standing(e.x, e.y):
                self._enemy_forward(e)
            else:
                e.y += 1
        e.y = self.wrap_y(e.y)

    # ---- Banebou: HandleBanebou.  Falls, short hop, falls, long hop, repeat.

    def _banebou_ai(self, e: Enemy) -> None:
        if e.state in (0, 2):  # falling
            if not self.standing(e.x, e.y):
                e.y += 1
                return
            e.counter = 0
            e.state += 1
            if e.state == 1 and self.rng.getrandbits(3) == 0:
                self._look_around(e)
        elif e.state in (1, 3):  # hop: up, up+forward, forward, down+forward
            up, up_fwd, fwd, down_fwd = (4, 8, 12, 16) if e.state == 1 else (4, 10, 16, 22)
            t = e.counter
            e.counter += 1
            if t < up:
                e.y -= 1
            elif t < up_fwd:
                self._enemy_forward(e)
                e.y -= 1
            elif t < fwd:
                self._enemy_forward(e)
            elif t < down_fwd:
                self._enemy_forward(e)
                if not self.standing(e.x, e.y):
                    e.y += 1
            else:
                e.state += 1
        else:
            e.state, e.counter = 0, 0

    # Beluga (Monsta): diagonal float, HandleBeluga.
    def _beluga_ai(self, e: Enemy) -> None:
        # CheckInsideWall: nudge up if embedded.
        if self.solid(e.x + 3, e.y + 7) and self.solid(e.x + 3, e.y):
            e.y -= 1
        self._enemy_forward(e)
        if e.state == 0:  # drifting up
            if self.solid(e.x, e.y - 1) or self.solid(e.x + 7, e.y - 1):
                e.state = 1
            else:
                e.y -= 1
        else:  # drifting down
            if self.solid(e.x, e.y + 8) or self.solid(e.x + 7, e.y + 8):
                e.state = 0
            else:
                e.y += 1

    # Hullaballoon: HandleHullaballoon.  A Beluga with narrower probes that
    # also takes an extra step forward every fourth frame.
    def _hulla_ai(self, e: Enemy) -> None:
        if self.solid(e.x + 3, e.y + 7) and self.solid(e.x + 3, e.y):
            e.y -= 1
        self._enemy_forward(e)
        if e.state == 0:
            if self.solid(e.x + 2, e.y - 1) or self.solid(e.x + 5, e.y - 1):
                e.state = 1
            else:
                e.y -= 1
        else:
            if self.solid(e.x + 2, e.y + 8) or self.solid(e.x + 5, e.y + 8):
                e.state = 0
            else:
                e.y += 1
        if self.timer % 4 == 0:
            self._enemy_forward(e)

    # ------------------------------------------------------- projectiles

    def _step_projectiles(self) -> None:
        for pr in list(self.projectiles):
            pr.age += 1
            if pr.kind == "stone":
                if pr.breaking:  # HandleGenericPop
                    if pr.age >= BREAK_FRAMES:
                        self.projectiles.remove(pr)
                    continue
                self._touch_player(pr.x, pr.y)
                pr.x += pr.dx
                if self.solid(pr.x + (7 if pr.dx > 0 else 0), pr.y + 4):
                    pr.breaking, pr.age = True, 0
            elif pr.kind == "fire":  # HandleHostileFire: 2 px/frame, through walls
                self._touch_player(pr.x, pr.y)
                pr.x += 2 * pr.dx
                if pr.x < -5 or pr.x >= SCREEN_W:
                    self.projectiles.remove(pr)
            elif pr.kind == "laser":  # HandleLaser: straight down, no wrap
                pr.y += 1
                if pr.y >= SCREEN_H:
                    self.projectiles.remove(pr)
                else:
                    self._touch_player(pr.x, pr.y)
            else:
                self._step_beer(pr)

    def _step_beer(self, pr: Projectile) -> None:
        """HandleBeer: wait, fly out, bounce off one wall, return to the Drunk."""
        owner = pr.owner
        if owner not in self.enemies:  # drunk was bubbled: beer vanishes
            self.projectiles.remove(pr)
            return
        if pr.age <= BEER_IDLE:
            return
        self._touch_player(pr.x, pr.y)
        if pr.x == owner.x:  # BeerCaught: drunk is free to move again
            self.projectiles.remove(pr)
            owner.beer_out = False
            owner.state, owner.counter = 0, 0
            return
        probe_x = pr.x + 8 if pr.dx > 0 else pr.x - 1
        if self.solid(probe_x, pr.y + 7) and not pr.bounced:
            pr.bounced = True
            pr.dx = -pr.dx
        pr.x += pr.dx

    # ----------------------------------------------------------- bubbles

    def _step_bubbles(self, ev) -> None:
        p = self.player
        for bub in list(self.bubbles):
            if bub.breaking is not None:
                self._step_breaking(bub, ev)
                continue
            self._bubble_player_interaction(bub, p)
            if self.timer % 4 != 0:
                continue
            if bub.push:
                probe_x = bub.x + 8 if bub.push > 0 else bub.x - 1
                if not self.solid(probe_x, bub.y + 4):
                    bub.x += bub.push
                bub.push = 0
            bub.life = (bub.life - 1) & 0xFF
            if bub.life == 0:
                self._start_break(bub, "pop")  # timed out: captive escapes
                continue
            self._float_bubble(bub)
            bub.y = self.wrap_y(bub.y)

    def _bubble_player_interaction(self, bub: BubbleSprite, p: Player) -> None:
        if p.dead_ticks >= 0:
            return
        if not self._overlap(bub.x, bub.y, p.x, p.y, 7):
            return
        dy = self._delta_wrapped(bub.y, p.y)
        if dy >= 4:  # player on top: ride (enables the bubble bounce)
            p.on_bubble = True
        elif abs(dy) < 4 and abs(bub.x - p.x) >= 4:
            bub.push = 1 if bub.x > p.x else -1  # nudge it along
        else:
            self._start_break(bub, "explode")  # touching pops it

    def _float_bubble(self, bub: BubbleSprite) -> None:
        current = self.tile(bub.x + 4, bub.y + 4)
        if current == TILE_LEFT:
            bub.x -= 1
        elif current == TILE_RIGHT:
            bub.x += 1
        elif current == TILE_DOWN:
            bub.y += 1
        else:  # up-current and (inside a wall) both drift up
            bub.y -= 1

    def _start_break(self, bub: BubbleSprite, kind: str) -> None:
        if bub.breaking is not None:
            return
        bub.breaking = kind
        bub.break_age = 0
        if kind == "explode":
            # Explosions chain to floating bubbles within a 20x20 box.
            for other in self.bubbles:
                if other.breaking is None and self._overlap(
                    other.x, other.y, bub.x, bub.y, 10
                ):
                    self._start_break(other, "explode")

    def _step_breaking(self, bub: BubbleSprite, ev) -> None:
        bub.break_age += 1
        if bub.break_age < BREAK_FRAMES:
            return
        self.bubbles.remove(bub)
        self.score += POP_EVENT_SCORE
        ev.score_delta += POP_EVENT_SCORE
        ev.pop_score += POP_EVENT_SCORE
        ev.popped += 1
        e = bub.captured
        if e is None:
            return
        e.x, e.y = bub.x, bub.y
        if bub.breaking == "pop":  # escaped: back to life, angry
            e.angry = True
            e.state, e.counter = 0, 0
            e.walk_counter, e.beer_out = 0, False
            self.enemies.append(e)
        else:  # killed
            ev.killed += 1
            self.dead_enemies.append(
                DeadEnemy(x=bub.x, y=bub.y, facing=self.player.facing)
            )
            self._enemy_died()

    def _enemy_died(self) -> None:
        self.alive_enemies -= 1
        if self.alive_enemies == 1:  # MakeEnemiesAngry
            for e in self.enemies:
                e.angry = True
        if self.alive_enemies <= 0:
            for bub in self.bubbles:  # NoMoreEnemies pops leftovers
                if bub.breaking is None:
                    self._start_break(bub, "explode")
            self.clear_countdown = CLEAR_DELAY

    # ----------------------------------------------- dead enemies, fruit

    def _step_dead_enemies(self, ev) -> None:
        # Approximation: the original tumbles the corpse along an arc; we
        # fly it up-and-sideways for 16 frames, then drop it as fruit.
        for de in list(self.dead_enemies):
            de.age += 1
            de.y -= 2
            de.x = max(0, min(SCREEN_W - 8, de.x + de.facing))
            de.y = self.wrap_y(de.y)
            if de.age >= 16:
                self.dead_enemies.remove(de)
                value = POP_SCORES[min(self.chain, len(POP_SCORES) - 1)]
                self.chain += 1
                self.chain_timer = CHAIN_WINDOW
                self.fruits.append(Fruit(x=de.x, y=de.y, value=value))

    def _step_fruits(self, ev) -> None:
        p = self.player
        for fr in list(self.fruits):
            fr.age += 1
            if fr.age >= 1024:
                self.fruits.remove(fr)
                continue
            if not self.standing(fr.x, fr.y):
                fr.y = self.wrap_y(fr.y + 1)
            if p.dead_ticks < 0 and self._overlap(fr.x, fr.y, p.x, p.y, 7):
                self.fruits.remove(fr)
                self.score += fr.value
                ev.score_delta += fr.value

    def _step_pickups(self, ev) -> None:
        p = self.player
        for pk in self.pickups:
            if pk.taken or p.dead_ticks >= 0:
                continue
            if self._overlap(pk.x, pk.y, p.x, p.y, 7):
                pk.taken = True
                self.score += PICKUP_SCORE
                ev.score_delta += PICKUP_SCORE
