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


def test_stationary_penalty_after_window_without_horizontal_movement():
    env = BubbleBobbleEnv(stationary_penalty=0.5, stationary_window=5, frame_skip=4)
    env.reset(seed=0)
    env.game.enemies, env.game.alive_enemies = [], 1  # nothing to die from
    rewards = [env.step(3)[1] for _ in range(8)]  # jump in place: y moves, x does not
    assert all(r == pytest.approx(0.0) for r in rewards[:5])
    assert all(r == pytest.approx(-0.5) for r in rewards[5:])
    walked = [env.step(2)[1] for _ in range(10)]  # walk right: band widens past 8 px
    assert walked[-1] == pytest.approx(0.0)


def test_stationary_band_is_configurable():
    env = BubbleBobbleEnv(stationary_penalty=0.5, stationary_window=5, stationary_band=32, frame_skip=4)
    env.reset(seed=0)
    env.game.enemies, env.game.alive_enemies = [], 1
    for _ in range(5):
        env.step(2)  # walk right 4 px per step: 16 px over the window, under the 32 px band
    assert env.step(2)[1] == pytest.approx(-0.5)


def test_explore_bonus_pays_once_per_new_column():
    env = BubbleBobbleEnv(explore_bonus=1.0, frame_skip=4)
    env.reset(seed=0)
    env.game.enemies, env.game.alive_enemies = [], 1
    rewards = [env.step(2)[1] for _ in range(6)]  # walk right 4 px per step from x=8
    assert sum(r >= 1.0 for r in rewards) == 3  # columns 2, 3 and 4 (x=16, 24, 32)
    back = [env.step(1)[1] for _ in range(6)]  # walk back over visited ground
    assert all(r < 1.0 for r in back)


def test_nearest_first_puts_the_closest_enemy_in_slot_zero():
    from bubblebobblerl.env import EGO_COLS, EGO_ROWS, GRID_COLS, GRID_ROWS
    from bubblebobblerl.game import Enemy

    for obs_type, e0 in (("state", 8 + GRID_ROWS * GRID_COLS), ("ego", 8 + EGO_ROWS * EGO_COLS)):
        env = BubbleBobbleEnv(obs_type=obs_type, nearest_first=True)
        env.reset(seed=0)
        p = env.game.player
        far = Enemy(kind=0, x=p.x + 60, y=p.y, facing=1, spawn_delay=0, falling_in=False)
        close = Enemy(kind=1, x=p.x + 12, y=p.y, facing=1, spawn_delay=0, falling_in=False)
        env.game.enemies = [far, close]  # spawn order: far first
        obs = env._obs()
        assert obs[e0 + 5] == pytest.approx(1 / 7)  # slot 0 holds the beluga (kind 1): the close one
        env.nearest_first = False
        assert env._obs()[e0 + 5] == pytest.approx(0.0)  # default keeps spawn order


def test_timeout_penalty_is_charged_once_at_truncation():
    env = BubbleBobbleEnv(timeout_penalty=4.0, max_episode_frames=40, frame_skip=4)
    env.reset(seed=0)
    env.game.enemies, env.game.alive_enemies = [], 1
    rewards = []
    for _ in range(10):
        _, r, term, trunc, _ = env.step(0)
        rewards.append(r)
    assert trunc and rewards[-1] == pytest.approx(-4.0) and all(r == pytest.approx(0.0) for r in rewards[:-1])


def test_control_obs_distinguishes_held_from_fresh_shoot():
    """The review's reproduction: identical pictures, different button history."""
    import copy

    env = BubbleBobbleEnv(obs_type="state", control_obs=True)
    env.reset(seed=1)
    env.game.player.shoot_cooldown = 0
    env.game.prev_shoot = False
    twin = copy.deepcopy(env)
    twin.game.prev_shoot = True
    assert not np.array_equal(env._obs(), twin._obs())
    assert env.observation_space.shape[0] == twin.observation_space.shape[0] == 660
    plain = BubbleBobbleEnv(obs_type="state")
    assert plain.observation_space.shape[0] == 656  # older checkpoints unaffected


def test_reward_components_are_reported_and_sum_to_the_reward():
    env = BubbleBobbleEnv(time_penalty=0.01, kill_bonus=2.0, score_reward=False)
    env.reset(seed=0)
    _, r, _, _, info = env.step(0)
    parts = [v for k, v in info.items() if k.startswith("r_")]
    assert len(parts) == 9 and sum(parts) == pytest.approx(r) and info["r_time"] == pytest.approx(-0.01)


def test_evaluate_preserves_caller_rng_and_is_reproducible(tmp_path):
    """The trainer calls evaluate() mid-run: it must leave torch/numpy RNG
    streams untouched, and the same checkpoint + seed must give the same result."""
    import sys
    from pathlib import Path

    import torch

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from evaluate import evaluate
    from train_ppo import Agent

    env = BubbleBobbleEnv(obs_type="state")
    torch.manual_seed(0)
    agent = Agent(env.observation_space, env.action_space.n)
    ckpt = tmp_path / "model.pt"
    torch.save(agent.state_dict(), ckpt)
    torch.manual_seed(123)
    np.random.seed(123)
    before_t, before_n = torch.get_rng_state().clone(), np.random.get_state()[1].copy()
    r1 = evaluate(str(ckpt), [1, 2], episodes=1, max_steps=30, seed=1001)
    assert torch.equal(torch.get_rng_state(), before_t)
    assert np.array_equal(np.random.get_state()[1], before_n)
    r2 = evaluate(str(ckpt), [1, 2], episodes=1, max_steps=30, seed=1001)
    assert r1["per_level"] == r2["per_level"] and r1["mean_score"] == r2["mean_score"]


def _countdown_state(env):
    """All enemies dead: the game's 256-frame clear countdown is running."""
    g = env.game
    g.enemies = []
    g.alive_enemies = 1
    g._enemy_died()
    assert g.alive_enemies == 0 and g.clear_countdown > 0
    return g


def test_dying_during_the_clear_countdown_is_not_a_clear():
    """Regression (2026-10-19): the evaluator used to count any episode that
    ended with every enemy dead as a clear."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from evaluate import classify_outcome

    from bubblebobblerl.game import Projectile

    env = BubbleBobbleEnv(death_penalty=5, clear_bonus=10)
    env.reset(seed=0, options={"level": 1})
    g = _countdown_state(env)
    g.projectiles.append(Projectile("fire", x=g.player.x - 4, y=g.player.y, dx=1))
    completed, total = False, 0.0
    while True:
        _, r, term, trunc, info = env.step(0)
        total += r
        completed |= info["level_complete"]
        if term or trunc:
            break
    assert info["all_enemies_dead"] and g.game_over and not completed
    assert total == pytest.approx(-5.0)  # training saw a death, no clear bonus
    assert classify_outcome(completed, g) == "death"


def test_running_out_of_time_during_the_countdown_is_a_timeout_and_a_full_countdown_is_a_clear():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from evaluate import classify_outcome

    env = BubbleBobbleEnv(max_episode_frames=40, timeout_penalty=4, clear_bonus=10)
    env.reset(seed=0, options={"level": 1})
    g = _countdown_state(env)
    g.player.invincible = 10**6
    completed = False
    while True:
        _, r, term, trunc, info = env.step(0)
        completed |= info["level_complete"]
        if term or trunc:
            break
    assert trunc and not completed and classify_outcome(completed, g) == "timeout"

    env = BubbleBobbleEnv(max_episode_frames=3600, clear_bonus=10)
    env.reset(seed=0, options={"level": 1})
    g = _countdown_state(env)
    g.player.invincible = 10**6
    completed, total = False, 0.0
    while True:
        _, r, term, trunc, info = env.step(0)
        total += r
        completed |= info["level_complete"]
        if term or trunc:
            break
    assert term and completed and total == pytest.approx(10.0) and classify_outcome(completed, g) == "clear"


def test_vector_autoreset_is_next_step():
    """The trainer's masking assumes NEXT_STEP autoreset: the step after a
    terminal/truncated step returns reward 0 and the reset observation. If a
    Gymnasium upgrade changes this, the masking would drop real first steps."""
    import gymnasium as gym

    import bubblebobblerl  # noqa: F401

    envs = gym.vector.SyncVectorEnv([lambda: gym.make(
        "BubbleBobble-v0", obs_type="state", control_obs=True, max_episode_frames=12, time_penalty=0.5)])
    envs.reset(seed=0)
    out = [envs.step(np.array([0])) for _ in range(4)]
    assert [bool(o[3][0]) for o in out] == [False, False, True, False]  # truncated at the 3rd step
    assert out[3][1][0] == 0.0 and out[3][0][0][-1] == 1.0  # fake step: reward 0, time-left reset to 1


def test_gae_stops_at_terminal_steps_and_masks_fake_transitions():
    import sys
    from pathlib import Path

    import torch

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from train_ppo import gae_with_autoreset

    # One env, five steps: s0 s1 s2(terminal) F(fake, after the terminal step) s4; bootstrap after s4.
    rew = torch.tensor([[1.0], [1.0], [5.0], [0.0], [1.0]])
    val = torch.tensor([[0.5], [0.5], [0.5], [9.0], [0.5]])
    done = torch.tensor([[0.0], [0.0], [0.0], [1.0], [0.0]])  # done flag returned by the previous step
    adv, ret, real = gae_with_autoreset(rew, val, done, torch.tensor([2.0]), torch.tensor([0.0]), 0.9, 1.0)
    assert real.squeeze().tolist() == [True, True, True, False, True]
    assert adv[2].item() == 5.0 - 0.5  # terminal: no bootstrap from the fake step's value (9.0)
    assert adv[1].item() == pytest.approx(1.0 + 0.9 * 0.5 - 0.5 + 0.9 * (5.0 - 0.5))
    assert adv[4].item() == pytest.approx(1.0 + 0.9 * 2.0 - 0.5)  # last step bootstraps next_value
    assert torch.allclose(ret, adv + val)


def test_checkpoint_refuses_a_different_observation(tmp_path):
    """Regression (2026-10-19): an ego checkpoint evaluated on state observations
    used to run silently (the longer vector was trimmed to the model's input
    size), giving meaningless scores."""
    import json
    import sys
    from pathlib import Path

    import torch

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from evaluate import evaluate
    from train_ppo import Agent

    ego = BubbleBobbleEnv(obs_type="ego", control_obs=True)
    torch.save(Agent(ego.observation_space, ego.action_space.n).state_dict(), tmp_path / "model.pt")
    (tmp_path / "arch.json").write_text(json.dumps({"obs": "ego", "control_obs": True, "nearest_first": False}))
    with pytest.raises(ValueError, match="trained with observation"):
        evaluate(str(tmp_path / "model.pt"), [1], episodes=1, max_steps=5, obs="state", control_obs=True)
    r = evaluate(str(tmp_path / "model.pt"), [1], episodes=1, max_steps=5, obs="ego", control_obs=True)
    assert r["episodes"] == 1


def test_continuation_records_the_parents_architecture_and_observation(tmp_path):
    """Regression (2026-10-19): a continuation's arch.json used to record the
    --act/--hidden defaults instead of the parent's actual network, and nothing
    stopped a continuation from silently changing the observation."""
    import json
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from train_ppo import parse_args, train

    common = ["--total-steps", "32", "--num-envs", "2", "--rollout-len", "16", "--eval-every", "0",
              "--no-mlflow", "--no-tensorboard", "--quiet"]
    parent = tmp_path / "parent"
    train(parse_args(common + ["--obs", "ego", "--control-obs", "--act", "relu", "--hidden", "32",
                               "--run-dir", str(parent)]))
    a = json.loads((parent / "arch.json").read_text())
    assert (a["act"], a["hidden"], a["obs"], a["control_obs"]) == ("relu", 32, "ego", True)
    child = tmp_path / "child"
    train(parse_args(common + ["--obs", "ego", "--control-obs", "--init-model", str(parent / "model.pt"),
                               "--run-dir", str(child)]))
    c = json.loads((child / "arch.json").read_text())
    assert (c["act"], c["hidden"], c["obs"], c["control_obs"]) == ("relu", 32, "ego", True)
    with pytest.raises(ValueError, match="trained with observation"):
        train(parse_args(common + ["--control-obs", "--init-model", str(parent / "model.pt"),
                                   "--run-dir", str(tmp_path / "bad")]))


def _fixture_game(facing):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import diag_fixture

    env = BubbleBobbleEnv(obs_type="state", control_obs=True, max_episode_frames=3600, level=1)
    env.reset(seed=1, options={"level": 1})
    g = env.game
    g.player.x, g.player.y, g.player.facing = 44, diag_fixture.FLOOR_Y, facing
    g.enemies, g.alive_enemies, g.grace_left = [], 1, 10**9
    return env, g, diag_fixture


def test_fixture_counts_a_shot_blown_while_an_old_bubble_expires():
    """Regression (2026-10-19): the engagement probe counted shots as net growth
    of the prebubble list per agent step. A bubble lives 27 frames and the
    cooldown is 14, so SHOOT, 5 x NOOP, SHOOT blows the second bubble in the
    step in which the first expires: two bubbles, zero net growth."""
    env, g, fx = _fixture_game(+1)
    events = fx.instrument_shots(g)
    net = 0
    for a in (6, 0, 0, 0, 0, 0, 6, 0):
        n = len(g.prebubbles)
        env.step(a)
        net += len(g.prebubbles) > n
    assert net == 1 and len(events) == 2


def test_fixture_records_launch_facing_before_a_turn():
    """LEFT+SHOOT while facing right blows the bubble rightward (Game blows
    before it turns the player); the post-step facing is left."""
    env, g, fx = _fixture_game(+1)
    events = fx.instrument_shots(g)
    env.step(7)
    assert g.player.facing == -1 and [e["facing"] for e in events] == [+1]


def test_fixture_would_capture_needs_the_targets_band_and_range():
    _, g, fx = _fixture_game(+1)
    y = fx.FLOOR_Y
    assert fx.would_capture(g, 44, y, +1, 44 + 24, y)  # standoff distance, facing it
    assert not fx.would_capture(g, 44, y, -1, 44 + 24, y)  # facing away
    assert not fx.would_capture(g, 44, y - 8, +1, 44 + 24, y)  # one band too high
    assert fx.would_capture(g, 44, y - 7, +1, 44 + 24, y)  # edge of the capture margin
    assert not fx.would_capture(g, 44, y, +1, 44 + 34, y)  # 26 px of flight + 7 margin falls short
    assert fx.would_capture(g, 44, y, +1, 44 + 33, y)


def test_fixture_probes_on_one_env_do_not_share_shot_records():
    """Regression (2026-10-19): the env reuses its Game across resets, and the
    first creation-time instrumentation wrapped the instance attribute, so
    each probe stacked a wrapper and earlier probes' event lists kept growing."""
    import numpy as np

    env, g, fx = _fixture_game(+1)
    sit = next(fx.situations(g))
    recs = [fx.run_one(env, None, "standoff", None, np.random.default_rng(0), sit, 60, 8, +1, True, "live", False)
            for _ in range(3)]
    assert all(r["shots"] > 0 and len(r["shot_events"]) == r["shots"] for r in recs)
    assert recs[0]["shot_events"] == recs[2]["shot_events"]


def test_falling_player_walks_on_odd_frames_only():
    """Regression (2026-10-19): Z80 HandlePlayer2 calls PlayerMoveCounter, which
    ends the player's turn before GetDir on even frames while the jump counter's
    mode is 1 (falling). The port walked and turned every frame in the air, so
    falls drifted sideways at twice the original's speed."""
    from bubblebobblerl.game import Buttons

    env = BubbleBobbleEnv(obs_type="state", level=1)
    env.reset(seed=1, options={"level": 1})
    g = env.game
    g.enemies, g.alive_enemies, g.grace_left = [], 1, 10**9
    p = g.player
    p.x, p.y, p.jump, p.facing = 44, 10, 1, -1  # mid-air on level 1, falling, facing left
    turned_at = None
    for f in range(8):
        g.step(Buttons(right=True))
        assert p.jump & 3 == 1
        if turned_at is None and p.facing == 1:
            turned_at = g.timer
    assert (p.x, p.y) == (48, 18)  # 4 px across for 8 px down
    assert turned_at % 2 == 1  # the turn also waits for an odd frame
    # Grounded walking is unaffected: one pixel per frame.
    p.x, p.y, p.jump = 40, 52, 0
    for _ in range(8):
        g.step(Buttons(right=True))
    assert p.x == 48


def test_wall_limit_stops_between_updates_and_writes_a_summary(tmp_path):
    """--wall-minutes stops before an update projected to end past the budget
    (here: after the first), and the run records steps/updates/seconds."""
    import json
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from train_ppo import parse_args, train

    train(parse_args(["--total-steps", "100000", "--num-envs", "2", "--rollout-len", "16", "--eval-every", "0",
                      "--no-mlflow", "--no-tensorboard", "--quiet", "--wall-minutes", "0.0001",
                      "--run-dir", str(tmp_path)]))
    s = json.loads((tmp_path / "train_summary.json").read_text())
    assert (s["updates"], s["steps"]) == (1, 32) and (tmp_path / "model.pt").exists()
    assert not (tmp_path / "model.pt.tmp").exists()


def _bubble_contact(facing, dx, dy, frames=4):
    from bubblebobblerl.game import BubbleSprite, Buttons

    env = BubbleBobbleEnv(obs_type="state", level=1)
    env.reset(seed=1, options={"level": 1})
    g = env.game
    g.enemies, g.alive_enemies, g.grace_left = [], 1, 10**9
    g.player.x, g.player.y, g.player.facing = 40, 52, facing
    bub = BubbleSprite(x=40 + dx, y=52 + dy, life=100)
    g.bubbles = [bub]
    x0 = bub.x
    for _ in range(frames):
        g.step(Buttons())
    return g.player.x, bub, x0


def test_bubble_contact_follows_bubblehitplayer():
    """Regression (2026-10-19): Z80 BubbleHitPlayer pushes a bubble only when it
    is at least 4 px ahead in the direction Bub faces, and Bub recoils (PlayerFlags,
    odd frames); a bubble behind him breaks. The port pushed on any side contact
    regardless of facing, broke bubbles above him that he faced, and had no recoil."""
    px, bub, x0 = _bubble_contact(facing=-1, dx=5, dy=0)  # behind Bub
    assert bub.breaking == "explode" and px == 40
    px, bub, x0 = _bubble_contact(facing=1, dx=5, dy=0)  # ahead: pushed on, Bub recoils
    assert bub.breaking is None and bub.x == x0 + 1 and px < 40
    px, bub, x0 = _bubble_contact(facing=1, dx=5, dy=-5)  # ahead and above: still pushed
    assert bub.breaking is None and bub.x == x0 + 1 and px < 40
    px, bub, x0 = _bubble_contact(facing=1, dx=2, dy=0)  # too close: breaks
    assert bub.breaking == "explode"


def test_trainer_rollout_storage_is_aligned_end_to_end(tmp_path, monkeypatch):
    """Oracle from the episode structure, not from the trainer's code: with a
    40-frame clock (10 agent steps) every episode is truncated after 10 real
    steps, and in NEXT_STEP autoreset the step after it is a fake transition.
    Captures what train() actually stores and hands to GAE: the done flag marks
    exactly the steps whose observation is a truncated episode's final one
    (time left 0), those steps have reward 0, the next observation is a reset
    one (time left 1), every episode contributes exactly 10 real steps, and the
    done flag carries over between rollouts."""
    import sys
    from pathlib import Path

    import torch

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import train_ppo

    calls, obs_seen = [], []
    orig_gae, orig_av = train_ppo.gae_with_autoreset, train_ppo.Agent.action_value

    def cap_gae(rew, val, done, next_value, next_done, gamma, lam):
        calls.append((rew.clone(), done.clone(), next_done.clone()))
        return orig_gae(rew, val, done, next_value, next_done, gamma, lam)

    def cap_av(self, x, action=None, greedy=False):
        if action is None:  # rollout step: record the time-left feature of each env
            obs_seen.append(x[..., -1].clone())
        return orig_av(self, x, action, greedy)

    monkeypatch.setattr(train_ppo, "gae_with_autoreset", cap_gae)
    monkeypatch.setattr(train_ppo.Agent, "action_value", cap_av)
    T, N = 32, 2
    train_ppo.train(train_ppo.parse_args([
        "--levels", "1", "--control-obs", "--max-episode-frames", "40", "--num-envs", str(N),
        "--rollout-len", str(T), "--total-steps", str(2 * T * N), "--eval-every", "0", "--grace-frames", "10000",
        "--no-mlflow", "--no-tensorboard", "--quiet", "--run-dir", str(tmp_path)]))
    assert len(calls) == 2 and len(obs_seen) == 2 * T
    time_left = torch.stack(obs_seen)  # [2T, N]
    rew = torch.cat([c[0] for c in calls])
    done = torch.cat([c[1] for c in calls])
    assert torch.equal(calls[0][2], calls[1][1][0])  # next_done of rollout 1 == done[0] of rollout 2
    for n in range(N):
        fake = done[:, n] == 1
        assert torch.equal(fake, time_left[:, n] == 0)  # fake steps are exactly the final observations
        assert torch.all(rew[fake, n] == 0)
        after = [t + 1 for t in torch.nonzero(fake).flatten().tolist() if t + 1 < 2 * T]
        assert all(time_left[t, n] == 1.0 for t in after)  # then a reset observation
        idx = torch.nonzero(fake).flatten().tolist()
        assert [b - a - 1 for a, b in zip(idx, idx[1:])] == [10] * (len(idx) - 1)  # 10 real steps each
        assert idx[0] == 10  # the first episode starts at t=0 after the initial reset


def test_explained_variance_ignores_fake_transitions():
    """Logged explained variance used every stored step, including the fake
    autoreset steps. Hand-computed: real targets [1, 3], predictions [1, 2]
    -> 1 - Var([0, 1]) / Var([1, 3]) = 1 - 0.25 / 1 = 0.75; the fake step's
    wild prediction must not count."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from train_ppo import explained_variance

    assert explained_variance([1.0, 2.0, 50.0], [1.0, 3.0, 0.0], [True, True, False]) == 0.75
    assert explained_variance([[1.0], [2.0]], [[2.0], [2.0]], [[True], [True]]) != explained_variance(
        [[1.0], [2.0]], [[2.0], [2.0]], [[True], [True]])  # nan when the targets do not vary


def test_captured_enemy_bubble_contact_kills_or_pushes_by_facing():
    """Decision-note case (2026-10-19): with a captured enemy inside, contact
    from behind Bub explodes the bubble and kills the enemy (the previous rule
    pushed it); a bubble ahead of and above Bub is pushed and nobody dies (the
    previous rule exploded it)."""
    from bubblebobblerl.game import BREAK_FRAMES, BubbleSprite, Buttons, Enemy

    def run(facing, dx, dy):
        env = BubbleBobbleEnv(obs_type="state", level=1)
        env.reset(seed=1, options={"level": 1})
        g = env.game
        g.enemies, g.grace_left = [], 10**9
        g.alive_enemies = 2  # the captive plus one elsewhere, so the level does not end
        g.player.x, g.player.y, g.player.facing = 40, 52, facing
        captive = Enemy(kind=0, x=40 + dx, y=52 + dy, facing=1, spawn_delay=0)
        g.bubbles = [BubbleSprite(x=40 + dx, y=52 + dy, life=100, captured=captive)]
        killed = 0
        for _ in range(4 + BREAK_FRAMES + 4):
            killed += g.step(Buttons()).killed
        return killed, g

    killed, g = run(facing=-1, dx=5, dy=0)  # behind Bub
    assert killed == 1 and len(g.dead_enemies) == 1
    killed, g = run(facing=1, dx=5, dy=-5)  # ahead and above
    assert killed == 0 and len(g.bubbles) == 1


def test_trainer_rollout_storage_is_aligned_for_death_terminations(tmp_path, monkeypatch):
    """Death path of the end-to-end alignment check (no grace, a 100-step clock,
    so episodes end by death or truncation). Oracle from the observation: a
    fake step's observation is a final one (dead flag set, or time left 0), the
    following observation is a reset one (time left 1, alive), every reset
    observation after the first is preceded by a fake step, and fake steps
    carry reward 0. At least one episode must end by death for the check to
    mean anything."""
    import sys
    from pathlib import Path

    import torch

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import train_ppo

    calls, obs_seen = [], []
    orig_gae, orig_av = train_ppo.gae_with_autoreset, train_ppo.Agent.action_value

    def cap_gae(rew, val, done, next_value, next_done, gamma, lam):
        calls.append((rew.clone(), done.clone()))
        return orig_gae(rew, val, done, next_value, next_done, gamma, lam)

    def cap_av(self, x, action=None, greedy=False):
        if action is None:
            obs_seen.append(x[:, [6, -1]].clone())  # player dead flag, time left (state obs + control)
        return orig_av(self, x, action, greedy)

    monkeypatch.setattr(train_ppo, "gae_with_autoreset", cap_gae)
    monkeypatch.setattr(train_ppo.Agent, "action_value", cap_av)
    T, N = 256, 2
    train_ppo.train(train_ppo.parse_args([
        "--levels", "1", "--control-obs", "--max-episode-frames", "400", "--num-envs", str(N),
        "--rollout-len", str(T), "--total-steps", str(2 * T * N), "--eval-every", "0", "--seed", "3",
        "--no-mlflow", "--no-tensorboard", "--quiet", "--run-dir", str(tmp_path)]))
    o = torch.stack(obs_seen)  # [2T, N, 2]
    rew = torch.cat([c[0] for c in calls])
    done = torch.cat([c[1] for c in calls])
    deaths = 0
    for n in range(N):
        dead, left = o[:, n, 0], o[:, n, 1]
        fake = done[:, n] == 1
        final = (dead == 1) | (left == 0)
        assert torch.all(final[fake]) and torch.all(rew[fake, n] == 0)
        for t in torch.nonzero(fake).flatten().tolist():
            if t + 1 < 2 * T:
                assert left[t + 1] == 1.0 and dead[t + 1] == 0
        resets = [t for t in range(1, 2 * T) if left[t] == 1.0]
        assert all(fake[t - 1] for t in resets)
        deaths += int(((dead == 1) & (left > 0) & fake).sum())
    assert deaths >= 1


def _bubble_game():
    env = BubbleBobbleEnv(obs_type="state", level=1)
    env.reset(seed=1, options={"level": 1})
    g = env.game
    g.enemies, g.alive_enemies, g.grace_left = [], 2, 10**9
    g.player.x, g.player.y = 8, 52  # far from the bubbles
    return g


def _tick_aligned(g):
    from bubblebobblerl.game import Buttons

    while g.timer % 4 != 3:  # next frame is a 4-frame tick
        g.step(Buttons())


def test_overlapping_bubbles_drift_apart_and_stacked_ones_stay():
    """Regression (2026-10-19): Z80 BubbleHitBubble flags a one-pixel move
    apart, on each axis where two floating bubbles within 7 px are at least 4 px
    apart; DoBubbleFlags applies it at the next tick. The port had no
    bubble-bubble interaction."""
    from bubblebobblerl.game import BubbleSprite, Buttons

    g = _bubble_game()
    a, b = BubbleSprite(x=40, y=30, life=100), BubbleSprite(x=45, y=30, life=100)
    c, d = BubbleSprite(x=60, y=30, life=100), BubbleSprite(x=62, y=30, life=100)
    g.bubbles = [a, b, c, d]
    _tick_aligned(g)
    for _ in range(8):  # two ticks: flags set on the first, applied on the second
        g.step(Buttons())
    assert b.x - a.x == 7  # 5 px apart -> each moved one pixel away
    assert d.x - c.x == 2  # closer than 4 px: stay stacked


def test_timed_out_bubble_pops_at_the_next_tick():
    """The self-destruct counter reaching 0 only flags the bubble (bits 5 and 7);
    DoBubbleFlags pops it at the next tick and the captive escapes."""
    from bubblebobblerl.game import BubbleSprite, Buttons, Enemy

    g = _bubble_game()
    captive = Enemy(kind=0, x=40, y=30, facing=1, spawn_delay=0)
    bub = BubbleSprite(x=40, y=30, life=1, captured=captive)
    g.bubbles = [bub]
    _tick_aligned(g)
    g.step(Buttons())  # tick: life 1 -> 0, flagged
    assert bub.breaking is None
    for _ in range(4):
        g.step(Buttons())  # next tick: pops
    assert bub.breaking == "pop"


def test_a_shot_flies_26_pixels_before_it_becomes_a_bubble():
    """Regression (2026-10-19): Z80 PrebubbleCounter turns the prebubble into a
    Bubble on its 27th frame and returns without moving it, so it moves on frames
    1-26 only. The port also moved it on the 27th frame."""
    from bubblebobblerl.game import PREBUBBLE_FRAMES, Buttons

    env = BubbleBobbleEnv(obs_type="state", level=1)
    env.reset(seed=1, options={"level": 1})
    g = env.game
    g.enemies, g.alive_enemies, g.grace_left = [], 2, 10**9
    g.player.x, g.player.y, g.player.facing = 30, 52, 1  # open floor to the right
    g.step(Buttons(shoot=True))
    x0 = 30
    for _ in range(PREBUBBLE_FRAMES - 1):
        g.step(Buttons())
    assert not g.prebubbles and len(g.bubbles) == 1
    assert g.bubbles[0].x - x0 == 26
