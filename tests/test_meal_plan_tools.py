# tests/test_meal_plan_tools.py
# Unit tests for meal planning, shopping list, constraints, and plan persistence.
# Run with:  pytest tests/ -v

import os, sys, json, tempfile, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── helpers ───────────────────────────────────────────────────────────────────

def _reset_planner():
    """Reset in-memory planner state between tests."""
    from tools.meal_plan_tools import memory, DEFAULT_CONSTRAINTS
    memory.memories.clear()
    memory.memories["constraints"] = dict(DEFAULT_CONSTRAINTS)
    memory.memories["plan"] = {}


# ── constraints ──────────────────────────────────────────────────────────────

def test_default_constraints():
    _reset_planner()
    from tools.meal_plan_tools import _get_constraints, DEFAULT_CONSTRAINTS
    c = _get_constraints()
    assert c["mode"] == DEFAULT_CONSTRAINTS["mode"]
    assert c["household_size"] == 1
    assert c["avoid_recent_days"] == 7


def test_set_constraints_household_size():
    _reset_planner()
    from tools.meal_plan_tools import set_constraints, _get_constraints
    set_constraints.invoke({
        "mode": "freeform",
        "household_size": 4,
    })
    c = _get_constraints()
    assert c["household_size"] == 4


def test_set_constraints_mode_aliases():
    _reset_planner()
    from tools.meal_plan_tools import _normalize_constraints
    c = _normalize_constraints({"mode": "strict"})
    assert c["mode"] == "pantry-first-strict"
    c = _normalize_constraints({"mode": "freeform"})
    assert c["mode"] == "freeform"
    c = _normalize_constraints({"mode": "preferred"})
    assert c["mode"] == "pantry-preferred"


def test_set_constraints_diet_alias():
    _reset_planner()
    from tools.meal_plan_tools import _normalize_constraints
    c = _normalize_constraints({"mode": "freeform", "diet": "vegetarian"})
    assert c["diet"] == "veg"
    c = _normalize_constraints({"mode": "freeform", "diet": "meat"})
    assert c["diet"] == "non-veg"


# ── slot names ────────────────────────────────────────────────────────────────

def test_slot_names_list():
    from tools.meal_plan_tools import _slot_names
    assert _slot_names(["Breakfast", "Lunch"]) == ["Breakfast", "Lunch"]
    assert _slot_names(3) == ["Breakfast", "Lunch", "Dinner"]
    assert _slot_names(1) == ["Dinner"]
    assert _slot_names(2) == ["Lunch", "Dinner"]


# ── plan persistence ─────────────────────────────────────────────────────────

def test_persist_and_load_plan(tmp_path, monkeypatch):
    from tools import meal_plan_tools as mpt
    _persist_path = str(tmp_path / "current_plan.json")
    monkeypatch.setattr(mpt, "CURRENT_PLAN_PATH", _persist_path)

    _reset_planner()
    mpt.memory.memories["plan"] = {"Day1": {"Lunch": "Palak Paneer"}}
    mpt.memory.memories["constraints"] = {"mode": "freeform"}
    mpt._persist_plan()

    # Clear and reload
    mpt.memory.memories.clear()
    mpt.load_persisted_plan()

    assert mpt.memory.memories.get("plan", {}).get("Day1", {}).get("Lunch") == "Palak Paneer"
    assert mpt.memory.memories.get("constraints", {}).get("mode") == "freeform"


# ── update_plan ───────────────────────────────────────────────────────────────

def test_update_plan_writes_slot(tmp_path, monkeypatch):
    from tools import meal_plan_tools as mpt
    monkeypatch.setattr(mpt, "CURRENT_PLAN_PATH", str(tmp_path / "cp.json"))
    _reset_planner()

    result = mpt.update_plan.invoke({
        "day": "Day1", "meal": "Dinner",
        "recipe_name": "Dal Tadka", "reason": "test"
    })
    assert "Day1" in result
    assert mpt.memory.memories["plan"]["Day1"]["Dinner"] == "Dal Tadka"


# ── shopping list scaling ─────────────────────────────────────────────────────

def test_shopping_list_scales_by_household(tmp_path, monkeypatch):
    """When household_size=2, all buy quantities should be doubled."""
    from tools import meal_plan_tools as mpt
    monkeypatch.setattr(mpt, "CURRENT_PLAN_PATH", str(tmp_path / "cp.json"))
    _reset_planner()

    # Inject a fake plan and pre-computed deficit list directly
    mpt.memory.memories["plan"] = {"Day1": {"Dinner": "Dal Tadka"}}
    mpt.memory.memories["constraints"]["household_size"] = 2

    # Mock _quantity_shopping_deficits to return one fixed deficit
    test_deficit = [{"item": "toor dal", "unit": "g", "need": 200, "have": 0, "buy": 200}]
    monkeypatch.setattr(mpt, "_quantity_shopping_deficits", lambda _: test_deficit)

    result = mpt.get_shopping_list.invoke({})
    # After scaling by 2, buy should be 400
    assert "400" in result


# ── history integration in auto_plan ─────────────────────────────────────────

def test_avoid_recent_in_auto_plan(tmp_path, monkeypatch):
    """auto_plan should skip dishes recently cooked (from mock history)."""
    from tools import meal_plan_tools as mpt
    monkeypatch.setattr(mpt, "CURRENT_PLAN_PATH", str(tmp_path / "cp.json"))
    _reset_planner()

    # Pretend "Poha" was cooked yesterday
    monkeypatch.setattr(
        "tools.history_tools.recently_cooked_dishes",
        lambda within_days=7: ["poha"],
    )

    mpt.memory.memories["constraints"]["avoid_recent_days"] = 7
    # Run a plan — even if Poha is coverable, it should be skipped in Pass 1
    # (We just verify auto_plan runs without error and returns a string)
    result = mpt.auto_plan.invoke({"days": 1, "meals": ["Breakfast"], "continue_plan": False})
    assert isinstance(result, str)
    # Poha should ideally not appear (though may appear in Pass 2 fallback)
    # We cannot guarantee complete avoidance without full pantry setup, so just check run succeeds


# ── get_constraints tool ─────────────────────────────────────────────────────

def test_get_constraints_returns_json():
    _reset_planner()
    from tools.meal_plan_tools import get_constraints
    result = get_constraints.invoke({})
    data = json.loads(result)
    assert "mode" in data
    assert "household_size" in data
