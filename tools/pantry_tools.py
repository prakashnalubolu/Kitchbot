# tools/pantry_tools.py
# Supports partial removals and auto-maintains alternate-unit mirrors (e.g., spinach bunches ↔ grams)

from __future__ import annotations
import json
import os
from typing import Dict, Optional, List, Tuple

from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "data")
DATA_PATH = os.path.abspath(os.path.join(DATA_DIR, "pantry.json"))
ALT_UNITS_PATH = os.path.abspath(os.path.join(DATA_DIR, "alt_units.json"))
os.makedirs(DATA_DIR, exist_ok=True)

# -------------------------- alt-units rules --------------------------

def _load_alt_rules() -> dict:
    """
    Format expected in data/alt_units.json:

    {
      "rules": [
        {"item":"spinach","from":"count","to":"g","factor":125,"round":10},
        {"item":"spinach","from":"g","to":"count","factor":0.008,"round":1},
        ...
      ],
      "labels": { "spinach": {"count_label":"bunch"}, ... }   # optional, UI-only
    }
    """
    try:
        with open(ALT_UNITS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"rules": [], "labels": {}}
            data.setdefault("rules", [])
            data.setdefault("labels", {})
            return data
    except FileNotFoundError:
        # Safe default: empty rules, no mirroring
        return {"rules": [], "labels": {}}
    except Exception:
        return {"rules": [], "labels": {}}

_ALT = _load_alt_rules()

def _canon_item(s: str) -> str:
    return str(s or "").strip().lower()

def _norm_unit(u: Optional[str]) -> str:
    if not u: return "count"
    u = str(u).strip().lower()
    if u in ("kg", "kilogram", "kilograms"): return "g"
    if u in ("g", "gram", "grams", "gms"):  return "g"
    if u in ("l", "litre", "liter", "liters", "litres"): return "ml"
    if u in ("ml", "millilitre", "milliliter", "milliliters", "millilitres"): return "ml"
    if u in ("count", "pc", "pcs", "piece", "pieces"): return "count"
    return u

def _key(item: str, unit: str) -> str:
    return f"{_canon_item(item)} ({_norm_unit(unit)})"

def _round_to_step(value: float, step: Optional[int|float]) -> int:
    if not step or step <= 0:
        # nearest integer
        return int(round(value))
    return int(round(value / step) * step)

def _convert_qty(item: str, qty: float, from_unit: str, to_unit: str) -> Optional[float]:
    """Convert qty between units using alt_units rules. Returns None if no rule exists."""
    for r in _ALT.get("rules", []):
        if (_canon_item(r.get("item")) == _canon_item(item) and
                _norm_unit(r.get("from")) == _norm_unit(from_unit) and
                _norm_unit(r.get("to")) == _norm_unit(to_unit)):
            result = qty * float(r.get("factor", 1))
            result = _round_to_step(result, r.get("round"))
            return max(1, result)
    return None

def _alt_transforms_for(item: str, unit_from: str) -> List[dict]:
    """All rules that match this item + from-unit."""
    item = _canon_item(item)
    unit_from = _norm_unit(unit_from)
    rules = []
    for r in _ALT.get("rules", []):
        if _canon_item(r.get("item")) == item and _norm_unit(r.get("from")) == unit_from:
            rules.append(r)
    return rules

# -------------------------- JSON storage -----------------------------

class _PantryDB:
    """
    Persists pantry stock in data/pantry.json as:
      { "<item>": { "qty": <number>, "unit": "g|ml", "count": <int> } }
    Units are only "g" or "ml" — "count" lives in its own field.
    Internally, self.items stays as the old flat { "<item> (<unit>)": qty }
    so that all downstream callers (meal_plan_tools, manager_tools) need
    no changes.
    """

    def __init__(self, path: str = DATA_PATH):
        self.path = path
        self._load()

    def _load(self):
        """Read new nested JSON (or old flat JSON for backward compat) into flat self.items."""
        self.items: Dict[str, int] = {}
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for item, entry in (raw or {}).items():
                item = _canon_item(item)
                if isinstance(entry, dict):
                    # New nested format: {"qty":..., "unit":..., "count":...}
                    if "qty" in entry and "unit" in entry:
                        qty = int(entry.get("qty") or 0)
                        if qty > 0:
                            self.items[_key(item, str(entry["unit"]))] = qty
                    if "count" in entry:
                        cnt = int(entry.get("count") or 0)
                        if cnt > 0:
                            self.items[_key(item, "count")] = cnt
                elif isinstance(entry, (int, float)):
                    # Old flat format: key is "item (unit)" or bare "item"
                    if "(" in item and item.endswith(")"):
                        base, unit = item.rsplit("(", 1)
                        base = base.strip(); unit = unit[:-1]
                    else:
                        base, unit = item, "count"
                    qty = int(entry)
                    if qty > 0:
                        self.items[_key(base, unit)] = qty
        except Exception:
            self.items = {}

    def _save(self):
        """Write flat self.items back as new nested JSON format."""
        nested: Dict[str, dict] = {}
        for k, qty in self.items.items():
            if "(" not in k:
                continue
            base = k.rsplit("(", 1)[0].strip()
            unit = k.rsplit("(", 1)[1].rstrip(")")
            if qty <= 0:
                continue
            entry = nested.setdefault(base, {})
            if unit == "count":
                entry["count"] = qty
            else:
                entry["qty"] = qty
                entry["unit"] = unit
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(nested, f, indent=2, ensure_ascii=False)

    # --- core mutations + mirroring ----------------------------------

    def _bump(self, item: str, unit: str, delta: int) -> None:
        """Add delta (can be negative) to item(unit), dropping key at <=0."""
        k = _key(item, unit)
        current = int(self.items.get(k, 0))
        new_val = current + int(delta)
        if new_val <= 0:
            if k in self.items:
                del self.items[k]
        else:
            self.items[k] = new_val

    def _set_exact(self, item: str, unit: str, qty: int) -> None:
        """Set item(unit) exactly to qty; drop if <=0."""
        k = _key(item, unit)
        if qty <= 0:
            if k in self.items:
                del self.items[k]
        else:
            self.items[k] = int(qty)

    def _mirror_delta(self, item: str, unit_from: str, delta: int) -> None:
        """When we add/remove a delta in (item, unit_from), apply configured delta in every mapped 'to' unit.
        Only mirrors if the target unit is already being tracked — avoids creating a partial entry."""
        if delta == 0:
            return
        for rule in _alt_transforms_for(item, unit_from):
            unit_to = _norm_unit(rule.get("to"))
            if _key(item, unit_to) not in self.items:
                continue  # don't create a new unit entry from a partial delta
            factor  = float(rule.get("factor", 1))
            step    = rule.get("round")
            raw = delta * factor
            d_to = _round_to_step(raw, step)
            if d_to != 0:
                self._bump(item, unit_to, d_to)

    def _mirror_set(self, item: str, unit_from: str, qty: int) -> None:
        """When we set (item, unit_from) exactly to qty, overwrite target units with transformed qty.
        Only mirrors if the target unit is already being tracked."""
        for rule in _alt_transforms_for(item, unit_from):
            unit_to = _norm_unit(rule.get("to"))
            if _key(item, unit_to) not in self.items:
                continue
            factor  = float(rule.get("factor", 1))
            step    = rule.get("round")
            raw = qty * factor
            q_to = _round_to_step(raw, step)
            self._set_exact(item, unit_to, q_to)

    # --- public CRUD --------------------------------------------------

    def add(self, item: str, qty: int, unit: str) -> str:
        item = _canon_item(item)
        unit = _norm_unit(unit)
        if qty <= 0:
            return "⚠️ Quantity must be > 0."
        # base bump
        self._bump(item, unit, qty)
        # mirror bump(s)
        self._mirror_delta(item, unit, qty)
        self._save()
        return f"✅ Added {qty} {unit} of {item}. Now you have {self.items.get(_key(item, unit), 0)} {unit}."

    def update(self, item: str, qty: int, unit: str) -> str:
        item = _canon_item(item)
        unit = _norm_unit(unit)
        if qty < 0:
            return "⚠️ Quantity must be ≥ 0."
        # set base
        self._set_exact(item, unit, qty)
        # overwrite mirrors to stay in sync
        self._mirror_set(item, unit, qty)
        self._save()
        return f"🔄 Set {item} to {qty} {unit}."

    def remove(self, item: str, qty: Optional[int], unit: str) -> str:
        item = _canon_item(item)
        unit = _norm_unit(unit)
        k = _key(item, unit)
        if k not in self.items:
            # Try cross-unit: find which unit this item IS stored in, then convert
            for other in ("count", "g", "ml"):
                if other == unit:
                    continue
                other_key = _key(item, other)
                if other_key in self.items:
                    if qty is None:
                        # "remove all" — just use the unit it's stored in
                        return self.remove(item, None, other)
                    converted = _convert_qty(item, float(qty), unit, other)
                    if converted is not None:
                        converted_int = int(converted)
                        note = (f"({qty} {unit} ≈ {converted_int} {other} "
                                f"based on unit conversion)")
                        result = self.remove(item, converted_int, other)
                        return f"{result} {note}"
                    else:
                        return (f"⚠️ {item.title()} is stored in {other}, not {unit}. "
                                f"No conversion rule found. Please specify quantity in {other}.")
            return f"⚠️ {item} not found in your pantry."

        if qty is None:
            # remove all -> compute delta = -current
            delta = -int(self.items.get(k, 0))
            # base
            self._bump(item, unit, delta)
            # mirror
            self._mirror_delta(item, unit, delta)
            self._save()
            return f"🗑️ Removed all {item} ({unit})."

        if qty <= 0:
            return "⚠️ Quantity must be > 0."

        # partial removal
        existing = int(self.items.get(k, 0))
        delta = -min(int(qty), existing)  # don't underflow
        self._bump(item, unit, delta)
        self._mirror_delta(item, unit, delta)
        self._save()
        left = self.items.get(k, 0)
        if left == 0:
            return f"🗑️ Removed {qty} {unit} of {item}. Remaining: 0."
        return f"🗑️ Removed {qty} {unit} of {item}. Remaining: {left} {unit}."

    def list(self) -> str:
        if not self.items:
            return "📭 Pantry is empty."
        # Group by base item name for clean display
        grouped: Dict[str, dict] = {}
        for k in sorted(self.items.keys()):
            base = k.rsplit("(", 1)[0].strip() if "(" in k else k
            unit = k.rsplit("(", 1)[1].rstrip(")") if "(" in k else "count"
            qty = self.items[k]
            entry = grouped.setdefault(base, {})
            if unit == "count":
                entry["count"] = qty
            else:
                entry["qty"] = qty
                entry["unit"] = unit
        lines = []
        for base in sorted(grouped.keys()):
            e = grouped[base]
            if "qty" in e and "count" in e:
                lines.append(f"{base}: {e['count']} pieces ({e['qty']} {e['unit']})")
            elif "count" in e:
                lines.append(f"{base}: {e['count']} pieces")
            else:
                lines.append(f"{base}: {e['qty']} {e['unit']}")
        return "\n".join(lines)

_db = _PantryDB()

def get_pantry_items() -> Dict[str, int]:
    """Return a copy of the current pantry as { '<item> (<unit>)': qty }."""
    return dict(_db.items)

# -------------------------- tool I/O wrappers ------------------------

def _parse_payload(payload: str) -> dict:
    """
    Extract the first valid JSON object from a possibly-noisy string.
    """
    try:
        start = payload.find('{'); end = payload.rfind('}') + 1
        if start == -1 or end <= start:
            raise ValueError("No JSON object found.")
        data = json.loads(payload[start:end])
        if not isinstance(data, dict):
            raise ValueError("Payload must decode to a JSON object.")
        return data
    except Exception as err:
        raise ValueError(f"Invalid JSON payload: {err}") from err

@tool
def add_to_pantry(item: str, quantity: float, unit: str = "count") -> str:
    """Add *quantity* of *item* with the given *unit* (`count`, `g`, or `ml`)."""
    return _db.add(item=item, qty=int(quantity), unit=unit)

@tool
def update_pantry(item: str, quantity: float, unit: str = "count") -> str:
    """Set the stock level for *item* and *unit* exactly to *quantity*."""
    return _db.update(item=item, qty=int(quantity), unit=unit)

@tool
def remove_from_pantry(item: str, quantity: Optional[float] = None, unit: str = "count") -> str:
    """
    Remove *quantity* of *item* (default all) for the specified *unit*.

    • If *quantity* is omitted/null, the entire entry is deleted.
    • Otherwise only that amount is deducted.
    """
    return _db.remove(
        item=item,
        qty=None if quantity is None else int(quantity),
        unit=unit,
    )

@tool
def list_pantry() -> str:
    """Return a human-readable listing of the pantry."""
    return _db.list()
