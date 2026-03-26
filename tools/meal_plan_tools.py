from __future__ import annotations
import json, os, datetime, re, random
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from langchain_core.tools import tool
from langchain.memory import SimpleMemory
from tools.cuisine_tools import _load as _load_recipes
from tools.textnorm import canonical_key as _canon, canonical_and_unit as _canon_and_unit
from tools import pantry_tools as _pt
from tools.pantry_tools import get_pantry_items as _get_pantry_items



##############################################################################
# Shared memory object – survives for the life of the Streamlit session
##############################################################################
memory: SimpleMemory = SimpleMemory(memories={})  # injected into agent via import

# Where we persist finished plans ------------------------------------------------
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PLAN_DIR = os.path.join(ROOT_DIR, "plans")
os.makedirs(PLAN_DIR, exist_ok=True)

# Default planning mode if not set by UI
DEFAULT_MODE = "pantry-first"

def _get_mode() -> str:
    return (memory.memories.get("mode") or DEFAULT_MODE).strip().lower()

# ---------------- Constraints (single source of truth) ----------------
DEFAULT_CONSTRAINTS = {
    "mode": "pantry-first-strict",   # or "freeform"
    "allow_repeats": True,
    "cuisine": None,
    "diet": None,                    # "veg" | "eggtarian" | "non-veg" | None
    "max_time": None,                # int minutes or None
    "sub_policy": "100%-coverage",   # label only; strict means exact coverage
    "allow_subs": False,             # when True we allow prep/subs to reach 100%
}


def _get_constraints() -> Dict[str, Any]:
    c = memory.memories.get("constraints") or {}
    out = {**DEFAULT_CONSTRAINTS, **c}
    memory.memories["constraints"] = out
    return out

def _normalize_constraints(upd: Dict[str, Any]) -> Dict[str, Any]:
    c = _get_constraints()
    mode = (upd.get("mode") or "").strip().lower()
    if mode in ("pantry-first", "pantry-first-strict", "strict"):
        c["mode"] = "pantry-first-strict"
    elif mode in ("freeform", "user-choice", "personal-choice"):
        c["mode"] = "freeform"
    if "allow_repeats" in upd:
        c["allow_repeats"] = bool(upd["allow_repeats"])
        # NEW: prep/substitutions toggle
    if "allow_subs" in upd:
        c["allow_subs"] = bool(upd["allow_subs"])
    # accept a friendly alias too
    if "include_subs" in upd:
        c["allow_subs"] = bool(upd["include_subs"])
    if "cuisine" in upd:
        val = upd["cuisine"]
        c["cuisine"] = (val.strip().lower() or None) if isinstance(val, str) else None
    if "diet" in upd:
        val = (upd["diet"] or "").strip().lower()
        _diet_aliases = {"vegetarian": "veg", "veggie": "veg", "veg": "veg",
                         "eggtarian": "eggtarian", "eggetarian": "eggtarian",
                         "non-veg": "non-veg", "nonveg": "non-veg", "meat": "non-veg"}
        c["diet"] = _diet_aliases.get(val) or (val if val in ("veg", "eggtarian", "non-veg") else None)
    if "max_time" in upd:
        try:
            c["max_time"] = int(upd["max_time"])
        except Exception:
            c["max_time"] = None
    if "sub_policy" in upd:
        c["sub_policy"] = str(upd["sub_policy"]).strip().lower() or "100%-coverage"
    memory.memories["constraints"] = c
    return c

@tool
def get_constraints() -> str:
    """Return the current planning constraints as JSON."""
    return json.dumps(_get_constraints())

@tool
def set_constraints(
    mode: str,
    allow_repeats: bool = True,
    cuisine: Optional[str] = None,
    diet: Optional[str] = None,
    max_time: Optional[int] = None,
) -> str:
    """Update planning constraints. mode: 'pantry-first-strict' or 'freeform'."""
    c = _normalize_constraints({
        "mode": mode,
        "allow_repeats": allow_repeats,
        "cuisine": cuisine,
        "diet": diet,
        "max_time": max_time,
    })
    nice_mode = "Pantry-first (strict)" if c["mode"] == "pantry-first-strict" else "Freeform"
    return f"OK. Mode: {nice_mode}, repeats: {c['allow_repeats']}, cuisine: {c['cuisine'] or 'any'}, diet: {c['diet'] or 'any'}, max_time: {c['max_time'] or 'any'}."

def _canon_name_unit(item: str, unit: str) -> tuple[str, str]:
    return _canon_and_unit(item, unit)


def _recipe_eligible_by_filters(rec: Dict[str, Any], c: Dict[str, Any],
                                 meal_slot: str = "") -> bool:
    from tools.cuisine_tools import diet_ok
    # cuisine
    if c.get("cuisine"):
        if (rec.get("cuisine") or "").strip().lower() != c["cuisine"]:
            return False
    # diet — use hierarchy: veg ⊂ eggtarian ⊂ non-veg
    want = c.get("diet")
    if want and not diet_ok(rec.get("diet"), want):
        return False
    # time
    if c.get("max_time"):
        total = int(rec.get("prep_time_min", 0)) + int(rec.get("cook_time_min", 0))
        if total > int(c["max_time"]):
            return False
    # meal slot — only allow breakfast recipes in Breakfast slot;
    # only allow non-breakfast recipes in Lunch/Dinner slots
    mt = (rec.get("meal_type") or "lunch_dinner").lower()
    if meal_slot.lower() == "breakfast":
        if mt not in ("breakfast", "any"):
            return False
    elif meal_slot.lower() in ("lunch", "dinner"):
        if mt == "breakfast":
            return False
    return True




def _eligible_recipes(c: Dict[str, Any], meal_slot: str = "") -> List[Dict[str, Any]]:
    return [r for r in _load_recipes() if _recipe_eligible_by_filters(r, c, meal_slot)]

def _slot_names(meals: Any) -> List[str]:
    if isinstance(meals, list) and all(isinstance(m, str) for m in meals):
        return meals
    if isinstance(meals, int):
        return ["Breakfast", "Lunch"] if meals == 2 else (["Dinner"] if meals == 1 else ["Breakfast", "Lunch", "Dinner"])
    return ["Breakfast", "Lunch", "Dinner"]

def _can_fulfill_with_prep(rec: Dict[str, Any], shadow: Dict[str, int]) -> tuple[bool, List[str]]:
    """
    Return (ok, notes). ok=True iff every ingredient is coverable either:
      • exactly from shadow (same name+unit), or
      • via simple prep equivalents (e.g., 'cooked rice (g)' covered by 'rice (g)').
    We do NOT mutate/deduct the shadow here — planning remains non-destructive.
    """
    notes: List[str] = []
    for ing in rec.get("ingredients", []):
        raw_name = (ing.get("item") or "").strip()
        qty = int(ing.get("quantity") or 0)
        unit = _normalize_unit(ing.get("unit") or "count")
        if not raw_name or qty <= 0:
            continue

        name_c, unit_n = _canon_name_unit(raw_name, unit)
        exact_key = f"{name_c} ({unit_n})"
        have_exact = int(shadow.get(exact_key, 0))

        if have_exact >= qty:
            # exact coverage — fine
            continue

        # ---- simple prep equivalents (keep this list tiny & conservative)
        # cooked rice ← rice (assume 1:1 coverage for planning purposes)
        if name_c in ("cooked rice", "steamed rice", "rice (cooked)"):
            base_key = f"rice ({unit_n})"
            if int(shadow.get(base_key, 0)) >= qty:
                notes.append("cooked rice from rice")
                continue

        # Add other tiny prep mappings here later (e.g., "boiled egg" ← "egg (count)")

        # if neither exact nor prep-equivalent covers this ingredient
        return False, notes

    return True, notes

def _shadow_pantry_snapshot_canon() -> dict[tuple[str, str], int]:
    """
    Build a shadow pantry map with canonical names:
      (canonical_name, unit_family) -> quantity
    """
    items = _get_pantry_items()  # uses public API
    shadow: dict[tuple[str, str], int] = {}
    for k, v in items.items():
        base_raw, unit_raw = _split_pantry_key(k)
        name_c, unit_n = _canon_and_unit(base_raw, unit_raw)
        shadow[(name_c, unit_n)] = shadow.get((name_c, unit_n), 0) + int(v or 0)
    return shadow

def _recipe_requirements_canon(rec: dict) -> list[tuple[str, str, int]]:
    """
    Return [(canonical_name, unit_family, qty), ...] for a recipe.
    """
    out: list[tuple[str, str, int]] = []
    for ing in rec.get("ingredients", []):
        item = (ing.get("item") or "").strip()
        qty  = int(ing.get("quantity") or 0)
        unit = _normalize_unit(ing.get("unit") or "count")
        if not item or qty <= 0:
            continue
        name_c, unit_n = _canon_and_unit(item, unit)
        out.append((name_c, unit_n, qty))
    return out

def _can_fulfill_strict_canon(rec: dict, shadow: dict[tuple[str, str], int]) -> bool:
    """
    True iff every canonical ingredient qty can be met from 'shadow'.
    """
    for name_c, unit_n, qty in _recipe_requirements_canon(rec):
        if shadow.get((name_c, unit_n), 0) < qty:
            return False
    return True

def _apply_deduction_canon(rec: dict, shadow: dict[tuple[str, str], int]) -> None:
    """
    Subtract each canonical ingredient qty from the shadow pantry.
    """
    for name_c, unit_n, qty in _recipe_requirements_canon(rec):
        key = (name_c, unit_n)
        shadow[key] = max(0, int(shadow.get(key, 0)) - qty)
        
def _tightness_key(rec: Dict[str, Any], shadow0: dict[tuple[str, str], int]) -> tuple:
    """
    Lower (tighter) first: recipes whose required lines are closest to pantry limits.
    Encourages placing scarce/bottleneck dishes before they get blocked by earlier picks.
    """
    mins = []
    for name_c, unit_n, need in _recipe_requirements_canon(rec):
        have = float(shadow0.get((name_c, unit_n), 0))
        if need <= 0:
            continue
        ratio = have / float(need) if need else float("inf")
        mins.append(ratio)
    min_ratio = min(mins) if mins else float("inf")
    total_time = int(rec.get("prep_time_min", 0)) + int(rec.get("cook_time_min", 0))
    return (min_ratio, total_time, (rec.get("name") or "").lower())


def _coverable_once_sorted(candidates: List[Dict[str, Any]],
                           shadow0: dict[tuple[str, str], int]) -> List[Dict[str, Any]]:
    """
    Return the list of recipes that are 100% coverable from the *initial* shadow pantry,
    sorted by 'tightness' so scarce recipes are scheduled first.
    """
    coverable = [r for r in candidates if _can_fulfill_strict_canon(r, shadow0)]
    coverable.sort(key=lambda r: _tightness_key(r, shadow0))
    return coverable

@tool
def auto_plan(
    days: int = 3,
    meals: Optional[Any] = None,
    continue_plan: bool = False,
) -> str:
    """
    Fill Day×Meals according to constraints.
    days: number of days to plan.
    meals: number of meals per day (int) or list of meal names e.g. ["Breakfast","Lunch","Dinner"].
    continue_plan: if True, append to the existing plan instead of starting fresh.

    Pantry-first (strict):
      • Only recipes fully satisfied by the *canonicalized* shadow pantry.
      • Simulate deductions between slots.
      • Pass 1: place each dish that is 100% coverable from the initial pantry at least once (unseen-first).
      • Pass 2: if no unseen fits now, pick any coverable (still respects no-consecutive).
      • Stop the moment a slot cannot be filled.

    Freeform:
      • Pick eligible recipes (respect cuisine/diet/time); no coverage check.

    Repeat policy:
      • allow_repeats=False ⇒ avoid consecutive repeats (not global uniqueness).
    """
    days  = int(days or 3)
    meals = _slot_names(meals)
    cont  = bool(continue_plan)

    c = _get_constraints()
    plan: Dict[str, Dict[str, str]] = memory.memories.get("plan", {}) if cont else {}
    memory.memories["plan"] = plan  # ensure it exists

    # Build slot list to fill in order
    start_at = 1
    if cont and plan:
        existing_ns = [int(re.sub(r"\D", "", d) or "0") for d in plan.keys()]
        start_at = (max(existing_ns) + 1) if existing_ns else 1
    target_days = list(range(start_at, start_at + days))

    # Shadow pantry for strict mode (canonicalized)
    shadow = _shadow_pantry_snapshot_canon() if c["mode"] == "pantry-first-strict" else {}

    filled = 0
    total_slots = len(target_days) * len(meals)

    calc_log = memory.memories.get("calc_log", [])
    if not isinstance(calc_log, list):
        calc_log = []

    prev_dish_lower: Optional[str] = None

    for day_i in target_days:
        day_key = f"Day{day_i}"
        day_row = plan.setdefault(day_key, {})

        for meal in meals:
            # Skip if already set (continue mode)
            if cont and day_row.get(meal):
                prev_dish_lower = (day_row.get(meal) or "").strip().lower() or prev_dish_lower
                continue

            # Build per-slot candidate pool filtered by meal type (breakfast vs lunch/dinner)
            slot_candidates = _eligible_recipes(c, meal_slot=meal)
            slot_candidates.sort(key=lambda r: (
                (r.get("name") or "").lower(), (r.get("cuisine") or "").lower()
            ))

            pick = None
            pick_reason = None

            if c["mode"] == "pantry-first-strict":
                # ---- compute once-coverable set for this slot
                initial_shadow = dict(shadow)
                once_list = _coverable_once_sorted(slot_candidates, initial_shadow)
                once_names_left: set[str] = {
                    (r.get("name") or "").strip().lower() for r in once_list
                }

                # PASS 1: prefer unseen dishes from the 100%-coverable set
                if once_names_left:
                    for r in once_list:
                        name   = (r.get("name") or "").strip()
                        name_l = name.lower()
                        if name_l not in once_names_left:
                            continue
                        if (not c.get("allow_repeats", True)) and prev_dish_lower and name_l == prev_dish_lower:
                            continue
                        if _can_fulfill_strict_canon(r, shadow):
                            pick        = r
                            pick_reason = "100% pantry coverage (once-each pass)"
                            _apply_deduction_canon(pick, shadow)
                            once_names_left.discard(name_l)
                            break

                # PASS 2: any coverable recipe for this slot
                if pick is None:
                    for r in slot_candidates:
                        name   = (r.get("name") or "").strip()
                        name_l = name.lower()
                        if (not c.get("allow_repeats", True)) and prev_dish_lower and name_l == prev_dish_lower:
                            continue
                        if _can_fulfill_strict_canon(r, shadow):
                            pick        = r
                            pick_reason = "100% pantry coverage"
                            _apply_deduction_canon(pick, shadow)
                            break

            else:
                # Freeform: shuffle for variety, avoid consecutive if requested
                shuffled = list(slot_candidates)
                random.shuffle(shuffled)
                for r in shuffled:
                    name   = (r.get("name") or "").strip()
                    name_l = name.lower()
                    if (not c.get("allow_repeats", True)) and prev_dish_lower and name_l == prev_dish_lower:
                        continue
                    pick        = r
                    pick_reason = "freeform pick"
                    break

            # ---- assign or stop
            if not pick:
                day_row.setdefault(meal, "")
                # Summarize attempted part and exit
                memory.memories["plan"] = plan
                memory.memories["calc_log"] = calc_log
                nice_mode = "Pantry-first (strict)" if c["mode"] == "pantry-first-strict" else "Freeform"

                attempted_keys = [f"Day{n}" for n in range(start_at, day_i + 1)]
                lines = []
                for d in attempted_keys:
                    row = plan.get(d, {})
                    parts = [row.get(m, "—") for m in meals]
                    lines.append(f"{d}: " + ", ".join(parts))

                msg = [f"Mode: {nice_mode}. Filled {filled}/{len(attempted_keys)*len(meals)} slots."]
                if lines:
                    msg.append(" " + " ".join(lines[:min(4, len(lines))]))
                if c["mode"] == "pantry-first-strict":
                    msg.append(" I paused when your pantry couldn’t fully cover the next dish. Say \"allow repeats\", \"relax cuisine/diet/time\", or \"switch to freeform\".")
                return "".join(msg)

            dish = (pick.get("name") or "").strip()
            day_row[meal] = dish
            prev_dish_lower = dish.lower()
            filled += 1

            calc_log.append({
                "slot": f"{day_key} » {meal}",
                "dish": dish,
                "virtual_deducted": [],
                "still_missing": [],
                "reason": pick_reason or "",
            })

    # Completed all slots
    memory.memories["plan"] = plan
    memory.memories["calc_log"] = calc_log
    nice_mode = "Pantry-first (strict)" if c["mode"] == "pantry-first-strict" else "Freeform"

    # Summary (compact)
    lines = []
    for d in [f"Day{n}" for n in target_days]:
        row = plan.get(d, {})
        parts = [row.get(m, "—") for m in meals]
        lines.append(f"{d}: " + ", ".join(parts))

    msg = [f"Mode: {nice_mode}. Filled {filled}/{total_slots} slots."]
    if lines:
        msg.append(" " + " ".join(lines[:min(4, len(lines))]))
    return "".join(msg)

##############################################################################
# 2 · update_plan – mutate planner_state (no shadow-pantry simulation)
##############################################################################
@tool
def update_plan(day: str, meal: str, recipe_name: str, reason: str = "") -> str:
    """Write a recipe into the plan for a given slot.

    day: e.g. "Day1", meal: "Breakfast"|"Lunch"|"Dinner", recipe_name: dish name.
    """
    if not (day and meal and recipe_name):
        return "Error: need 'day', 'meal', and 'recipe_name'."

    # 1) write the slot
    plan: Dict[str, Dict[str, str]] = memory.memories.setdefault("plan", {})
    plan.setdefault(day, {})[meal] = recipe_name
    memory.memories["last_query"] = json.dumps({"day": day, "meal": meal})

    # 2) record a structured calc entry (no shadow/virtual deduction)
    calc_log = memory.memories.get("calc_log", [])
    if not isinstance(calc_log, list):
        calc_log = []
    entry = {
        "slot": f"{day} » {meal}",
        "dish": recipe_name,
        "virtual_deducted": [],   # kept for UI compatibility
        "still_missing": [],      # kept for UI compatibility
    }
    if reason:
        entry["reason"] = reason
    calc_log.append(entry)
    memory.memories["calc_log"] = calc_log

    return f"Set {day} » {meal} to {recipe_name}."

##############################################################################
# 4 · Pantry helpers (normalize names/units, load/save)
##############################################################################
PANTRY_JSON_PATH = os.path.join(ROOT_DIR, "data", "pantry.json")

def _load_pantry() -> Dict[str, int]:
    """Load pantry JSON (new nested or old flat) and return flat {item (unit): qty} dict."""
    try:
        with open(PANTRY_JSON_PATH, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        flat: Dict[str, int] = {}
        for item, entry in data.items():
            if isinstance(entry, dict):
                if "qty" in entry and "unit" in entry:
                    qty = int(entry.get("qty") or 0)
                    if qty > 0:
                        flat[f"{item} ({entry['unit']})"] = qty
                if "count" in entry:
                    cnt = int(entry.get("count") or 0)
                    if cnt > 0:
                        flat[f"{item} (count)"] = cnt
            elif isinstance(entry, (int, float)):
                flat[item] = int(entry)
        return flat
    except FileNotFoundError:
        return {}
    except Exception:
        return {}

def _normalise(name: str) -> str:
    """Lower-case and strip very simple plurals (onions → onion)."""
    n = (name or "").strip().lower()
    if n.endswith("ies"):
        n = n[:-3] + "y"
    elif n.endswith("s") and len(n) > 3:
        n = n[:-1]
    return n

# --- unit normalization ---
def _normalize_unit(u: Optional[str]) -> str:
    """Map many spellings to {'g','ml','count'}."""
    if not u:
        return "count"
    s = str(u).strip().lower()
    aliases = {
        "g": "g", "gram": "g", "grams": "g", "gms": "g",
        "kg": "g", "kilogram": "g", "kilograms": "g",
        "ml": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
        "l": "ml", "liter": "ml", "liters": "ml", "litre": "ml", "litres": "ml",
        "count": "count", "piece": "count", "pieces": "count", "pc": "count", "pcs": "count",
    }
    return aliases.get(s, s)

_name_unit_re = re.compile(r"^\s*(.*?)\s*\(([^)]+)\)\s*$")

def _split_pantry_key(key: str) -> Tuple[str, str]:
    """'tomato (count)' -> ('tomato','count'), 'rice (g)' -> ('rice','g')"""
    m = _name_unit_re.match(key)
    if not m:
        base = key.split("(")[0]
        return _normalise(base), "count"
    return _normalise(m.group(1)), _normalize_unit(m.group(2))

def _find_matching_key(pantry, item, unit):
    name_c, unit_n = _canon_and_unit(item, unit or "count")
    for k in pantry.keys():
        b, u = _split_pantry_key(k)
        if _canon(b) == name_c and _normalize_unit(u) == unit_n:
            return k
    return None

def _load_recipe_by_name(name: str) -> Dict[str, Any] | None:
    name_l = (name or "").strip().lower()
    for r in _load_recipes():
        if r["name"].strip().lower() == name_l:
            return r
    return None

##############################################################################
# 5 · save_plan – write plan + quantity shopping list to disk
##############################################################################
def _collect_plan_requirements(plan: Dict[str, Dict[str, str]]) -> Dict[Tuple[str,str], int]:
    """Sum required qty per (item,unit) across the whole plan."""
    need: Dict[Tuple[str,str], int] = {}
    recipes = {r["name"].lower(): r for r in _load_recipes()}
    for day_dict in plan.values():
        for dish in day_dict.values():
            rec = recipes.get(dish.lower())
            if not rec:
                continue
            for ing in rec.get("ingredients", []):
                item = _canon(ing.get("item",""))
                _, unit = _canon_and_unit(item, ing.get("unit") or "count")  # re-normalize unit family

                qty  = int(ing.get("quantity") or 0)
                if qty <= 0 or not item:
                    continue
                need[(item, unit)] = need.get((item, unit), 0) + qty
    return need

def _quantity_shopping_deficits(plan: Dict[str, Dict[str, str]]) -> List[Dict[str, Any]]:
    """Compare plan needs to pantry and return deficits with quantities."""
    pantry = _load_pantry()
    needs = _collect_plan_requirements(plan)
    deficits: List[Dict[str, Any]] = []
    for (item, unit), need_qty in needs.items():
        key = _find_matching_key(pantry, item, unit)
        have = int(pantry.get(key, 0)) if key else 0
        buy = max(0, need_qty - have)
        if buy > 0:
            deficits.append({"item": item, "unit": unit, "need": need_qty, "have": have, "buy": buy})
    # nice stable sort
    deficits.sort(key=lambda d: (d["unit"], d["item"]))
    return deficits

def _format_deficits(deficits: List[Dict[str, Any]]) -> str:
    if not deficits:
        return "🛒 Shopping list is empty — you have everything needed for the plan."
    lines = []
    for d in deficits:
        lines.append(f"- {d['buy']} {d['unit']} {d['item']}  (need {d['need']}, have {d['have']})")
    return "\n".join(lines)

@tool
def get_shopping_list() -> str:
    """Return a quantity-aware shopping list computed from the current plan."""
    plan = memory.memories.get("plan", {})
    if not plan:
        return "No plan in memory."
    deficits = _quantity_shopping_deficits(plan)
    # keep a copy in memory for UI (your sidebar reads this)
    memory.memories["shopping_list"] = deficits
    return _format_deficits(deficits)

@tool
def save_plan(file_name: Optional[str] = None) -> str:
    """Persist the current plan (with constraints & shopping list) to /plans.
    Omit file_name for an auto-generated timestamped name."""
    plan        = memory.memories.get("plan", {})
    constraints = memory.memories.get("constraints", {})
    if not plan:
        return "No plan in memory to save."

    # quantity-aware shopping list
    deficits = _quantity_shopping_deficits(plan)
    data = {"constraints": constraints, "plan": plan, "shopping_list": deficits}

    if not file_name:
        file_name = f"plan_{datetime.datetime.now().strftime('%Y-%m-%dT%H-%M')}"
    safe_name = file_name.replace(" ", "_")

    path = Path(PLAN_DIR) / f"{safe_name}.json"
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)

    return f"Saved plan to {path.relative_to(ROOT_DIR)}"

##############################################################################
# 6 · cook_meal – mark a slot/dish cooked and consume ingredients from pantry
##############################################################################
def _deduct_one(item: str, qty: int, unit: str) -> None:
    # Normalize exactly like pantry tools do
    name = _pt._canon_item(item)
    u    = _pt._norm_unit(unit or "count")
    _pt._db.remove(name, int(qty), u)

@tool
def cook_meal(
    dish: Optional[str] = None,
    day: Optional[str] = None,
    meal: Optional[str] = None,
) -> str:
    """
    Mark a meal cooked and subtract ingredients from pantry.

    Either provide dish name directly, or provide day+meal to look up from the plan.
    """
    # Resolve the dish name
    if not dish:
        if not (day and meal):
            return "Error: provide dish name or both day and meal."
        plan = memory.memories.get("plan", {}) or {}
        day_plan = plan.get(day, {}) or {}
        dish = day_plan.get(meal)
        if not dish:
            return f"Error: no dish set for {day} » {meal}."

    recipe = _load_recipe_by_name(dish)
    if not recipe:
        return f"Error: recipe '{dish}' not found."

    # Build deducted/missing summaries by comparing before/after around the single
    # source-of-truth pantry DB (_pt._db). DO NOT write the JSON file here.
    deducted, missing = [], []

    for ing in recipe.get("ingredients", []):
        item = (ing.get("item") or "").strip()
        need_qty = int(ing.get("quantity", 0) or 0)
        unit = _normalize_unit(ing.get("unit") or "count")
        if not item or need_qty <= 0:
            continue

        # Canonical key for "before" snapshot
        name_c = _pt._canon_item(item)
        unit_n = _pt._norm_unit(unit)
        key = f"{name_c} ({unit_n})"
        before = int(_pt._db.items.get(key, 0))

        # Deduct via pantry DB (this also mirrors alt units!)
        _deduct_one(item, need_qty, unit)

        after = int(_pt._db.items.get(key, 0))
        used = min(before, need_qty)

        if used > 0:
            deducted.append(f"{used} {unit_n} {item}")
        if used < need_qty:
            missing.append(f"{need_qty - used} {unit_n} {item}")

    # (No direct file writes; _pt._db already saved.)

    # Mark the slot as cooked in the plan (prefix with ✅ for UI)
    plan = memory.memories.get("plan", {})
    if day and meal:
        slot_day = day
        slot_meal = meal
        if plan.get(slot_day, {}).get(slot_meal):
            current = plan[slot_day][slot_meal]
            if not current.startswith("✅"):
                plan[slot_day][slot_meal] = f"✅ {current}"
            memory.memories["plan"] = plan
    else:
        # find by dish name
        for d_key, d_val in plan.items():
            for m_key, m_dish in d_val.items():
                if m_dish.strip("✅ ").lower() == dish.lower() and not m_dish.startswith("✅"):
                    plan[d_key][m_key] = f"✅ {m_dish}"
        memory.memories["plan"] = plan

    # Log for UI
    log = memory.memories.setdefault("planner_log", [])
    log.append({
        "event": "cooked",
        "dish": dish,
        "deducted": deducted,
        "missing": missing,
    })
    memory.memories["planner_log"] = log

    parts = [f"✅ Marked cooked: {dish.title()}."]
    if deducted:
        parts.append("Consumed: " + ", ".join(deducted) + ".")
    if missing:
        parts.append("Still needed (not deducted): " + ", ".join(missing) + ".")
    if not deducted and not missing:
        parts.append("No ingredient lines were found in the recipe.")
    return " ".join(parts)
