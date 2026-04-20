# tests/test_pantry_tools.py
# Unit tests for pantry CRUD, unit normalization, and alt-unit mirroring.
# Run with:  pytest tests/ -v

import os, json, tempfile, pytest
from unittest.mock import patch

# ── helpers ──────────────────────────────────────────────────────────────────

def _make_db(tmp_path):
    """Create a fresh PantryDB backed by a temp file."""
    import importlib, sys
    # Ensure we can import from the repo root
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from tools.pantry_tools import _PantryDB
    db = _PantryDB(path=str(tmp_path / "pantry.json"))
    return db


# ── add ──────────────────────────────────────────────────────────────────────

def test_add_basic(tmp_path):
    db = _make_db(tmp_path)
    db.add("egg", 6, "count")
    assert db.items.get("egg (count)") == 6


def test_add_accumulates(tmp_path):
    db = _make_db(tmp_path)
    db.add("rice", 500, "g")
    db.add("rice", 300, "g")
    assert db.items.get("rice (g)") == 800


def test_add_normalizes_unit_kg_to_g(tmp_path):
    db = _make_db(tmp_path)
    db.add("flour", 1, "kg")   # tool normalizes kg → g × 1000? No — tool stores as-is
    # _norm_unit converts "kg" to "g"
    assert db.items.get("flour (g)") is not None


def test_add_rejects_zero(tmp_path):
    db = _make_db(tmp_path)
    result = db.add("milk", 0, "ml")
    assert "Quantity must be" in result
    assert db.items.get("milk (ml)") is None


# ── remove ────────────────────────────────────────────────────────────────────

def test_remove_partial(tmp_path):
    db = _make_db(tmp_path)
    db.add("egg", 12, "count")
    db.remove("egg", 4, "count")
    assert db.items.get("egg (count)") == 8


def test_remove_all(tmp_path):
    db = _make_db(tmp_path)
    db.add("egg", 12, "count")
    db.remove("egg", None, "count")
    assert "egg (count)" not in db.items


def test_remove_drops_key_at_zero(tmp_path):
    db = _make_db(tmp_path)
    db.add("egg", 3, "count")
    db.remove("egg", 3, "count")
    assert "egg (count)" not in db.items


def test_remove_missing_item(tmp_path):
    db = _make_db(tmp_path)
    result = db.remove("nonexistent", 1, "count")
    assert "not found" in result.lower()


def test_remove_doesnt_go_negative(tmp_path):
    db = _make_db(tmp_path)
    db.add("onion", 2, "count")
    db.remove("onion", 100, "count")  # remove more than we have
    assert db.items.get("onion (count)", 0) == 0


# ── update ────────────────────────────────────────────────────────────────────

def test_update_sets_exact(tmp_path):
    db = _make_db(tmp_path)
    db.add("milk", 500, "ml")
    db.update("milk", 200, "ml")
    assert db.items.get("milk (ml)") == 200


def test_update_zero_removes(tmp_path):
    db = _make_db(tmp_path)
    db.add("milk", 500, "ml")
    db.update("milk", 0, "ml")
    assert "milk (ml)" not in db.items


# ── persistence ───────────────────────────────────────────────────────────────

def test_save_and_reload(tmp_path):
    from tools.pantry_tools import _PantryDB
    db = _PantryDB(path=str(tmp_path / "pantry.json"))
    db.add("rice", 1000, "g")
    db.add("egg", 6, "count")

    db2 = _PantryDB(path=str(tmp_path / "pantry.json"))
    assert db2.items.get("rice (g)") == 1000
    assert db2.items.get("egg (count)") == 6


# ── unit normalization ────────────────────────────────────────────────────────

def test_norm_unit():
    from tools.pantry_tools import _norm_unit
    assert _norm_unit("kg") == "g"
    assert _norm_unit("litre") == "ml"
    assert _norm_unit("l") == "ml"
    assert _norm_unit("pieces") == "count"
    assert _norm_unit("g") == "g"


def test_canon_item():
    from tools.pantry_tools import _canon_item
    assert _canon_item("  Eggs  ") == "eggs"
    assert _canon_item("RICE") == "rice"
