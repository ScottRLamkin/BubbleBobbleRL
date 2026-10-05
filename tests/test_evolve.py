import random
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evolve import RANGES, Genome, mutate, plan_generation, seed_variants, select  # noqa: E402


def test_mutation_stays_in_range_and_changes_something():
    rng = random.Random(0)
    g = Genome()
    changed = 0
    for _ in range(500):
        child = mutate(g, rng)
        for gene, (lo, hi) in RANGES.items():
            assert lo <= getattr(child, gene) <= hi
        changed += child != g
        g = child  # random walk, so the bounds get exercised
    assert changed > 400


def test_zero_time_penalty_can_mutate_upward():
    rng = random.Random(1)
    g = Genome(time_penalty=0.0)
    assert any(mutate(g, rng).time_penalty > 0 for _ in range(50))


def test_select_ranks_by_clears_then_fewest_deaths():
    scored = [
        {"id": "a", "result": {"cleared": 10, "died": 50}},
        {"id": "b", "result": {"cleared": 12, "died": 90}},
        {"id": "c", "result": {"cleared": 10, "died": 20}},
        {"id": "d", "result": {"cleared": 3, "died": 0}},
    ]
    assert [m["id"] for m in select(scored, 3)] == ["b", "c", "a"]


def _parent(i, **genes):
    return {"id": f"p{i}", "lineage": ["base"], "model": f"p{i}.pt",
            "genome": asdict(Genome(**genes))}


def test_first_generation_uses_seed_variants_from_the_base():
    base = {"id": "base", "lineage": [], "model": "base.pt", "genome": asdict(Genome())}
    children = plan_generation(1, [base], 30, 1000, random.Random(0))
    assert len(children) == 30
    assert all(c["parent"] == "base" and c["lineage"] == ["base"] for c in children)
    variants = [asdict(g) for g in seed_variants(Genome())]
    assert [c["genome"] for c in children[: len(variants)]] == variants
    assert children[0]["genome"] == asdict(Genome())  # unmutated control


def test_later_generations_give_each_parent_an_unmutated_child():
    parents = [_parent(i, clear_bonus=20.0 + i) for i in range(10)]
    children = plan_generation(2, parents, 30, 1000, random.Random(0))
    assert len({c["id"] for c in children}) == 30
    for i, p in enumerate(parents):
        assert children[i]["parent"] == p["id"]
        assert children[i]["genome"] == p["genome"]
        assert sum(c["parent"] == p["id"] for c in children) == 3
    assert children[0]["lineage"] == ["base", "p0"]


def test_plan_is_deterministic_for_resume():
    parents = [_parent(i) for i in range(3)]
    a = plan_generation(2, parents, 9, 1000, random.Random(7))
    b = plan_generation(2, parents, 9, 1000, random.Random(7))
    assert a == b
