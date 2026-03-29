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
from tools.manager_tools import _is_universal, _count_to_g, _g_to_count, _ml_to_g, _g_to_ml



##############################################################################
# Shared memory object – survives for the life of the Streamlit session
##############################################################################
memory: SimpleMemory = SimpleMemory(memories={})  # injected into agent via import

# Where we persist finished plans ------------------------------------------------
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PLAN_DIR = os.path.join(ROOT_DIR, "plans")
os.makedirs(PLAN_DIR, exist_ok=True)

# ---------------- Constraints (single source of truth) ----------------
DEFAULT_CONSTRAINTS = {
    # mode: "pantry-preferred" | "pantry-first-strict" | "freeform"
    #   pantry-preferred  — fill from pantry first; freeform fallback for gaps + shopping list
    #   pantry-first-strict — 100% pantry only; leave slot blank if pantry can't cover it
    #   freeform          — any eligible recipe; full shopping list generated
    "mode": "pantry-preferred",
    "allow_repeats": True,
    "cuisine": None,
    "diet": None,            # "veg" | "eggtarian" | "non-veg" | None
    "max_time": None,        # int minutes or None
    "strict_meal_types": False,  # False = any recipe in any slot; True = breakfast-tagged only at breakfast
    "allow_subs": False,
}


def _get_constraints() -> Dict[str, Any]:
    c = memory.memories.get("constraints") or {}
    out = {**DEFAULT_CONSTRAINTS, **c}
    memory.memories["constraints"] = out
    return out

def _normalize_constraints(upd: Dict[str, Any]) -> Dict[str, Any]:
    c = _get_constraints()
    mode = (upd.get("mode") or "").strip().lower()
    if mode in ("pantry-preferred", "preferred", "pantry-first-flexible", "use what i have"):
        c["mode"] = "pantry-preferred"
    elif mode in ("pantry-first-strict", "pantry-first", "strict", "no-shopping", "no shopping"):
        c["mode"] = "pantry-first-strict"
    elif mode in ("freeform", "free", "user-choice", "personal-choice"):
        c["mode"] = "freeform"
    if "strict_meal_types" in upd:
        c["strict_meal_types"] = bool(upd["strict_meal_types"])
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

_MODE_LABELS = {
    "pantry-preferred":    "Pantry-preferred (fill gaps with shopping)",
    "pantry-first-strict": "Pantry-strict (no shopping)",
    "freeform":            "Freeform (full shopping list)",
}

@tool
def set_constraints(
    mode: str,
    allow_repeats: bool = True,
    cuisine: Optional[str] = None,
    diet: Optional[str] = None,
    max_time: Optional[int] = None,
    strict_meal_types: bool = False,
    allow_subs: bool = False,
) -> str:
    """
    Update planning constraints.
    mode: 'pantry-preferred' | 'pantry-first-strict' | 'freeform'
    strict_meal_types: if True, only breakfast-tagged recipes appear in the Breakfast slot.
    """
    c = _normalize_constraints({
        "mode": mode,
        "allow_repeats": allow_repeats,
        "cuisine": cuisine,
        "diet": diet,
        "max_time": max_time,
        "strict_meal_types": strict_meal_types,
        "allow_subs": allow_subs,
    })
    label = _MODE_LABELS.get(c["mode"], c["mode"])
    parts = [f"OK. Mode: {label}"]
    parts.append(f"cuisine: {c['cuisine'] or 'any'}")
    parts.append(f"diet: {c['diet'] or 'any'}")
    if c["max_time"]:
        parts.append(f"max time: {c['max_time']} min")
    if c["strict_meal_types"]:
        parts.append("strict meal types: on")
    return ", ".join(parts) + "."

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
    # Meal-slot discipline
    mt = (rec.get("meal_type") or "lunch_dinner").lower()
    slot = meal_slot.lower()
    if slot in ("lunch", "dinner"):
        # Breakfast-tagged dishes (Idli, Poha, Pancakes …) are never appropriate at lunch/dinner
        if mt == "breakfast":
            return False
    elif slot == "breakfast" and c.get("strict_meal_types", False):
        # Only enforce breakfast-only when user has opted in to strict meal types
        if mt not in ("breakfast", "any"):
            return False
    # Default (strict_meal_types=False): any recipe can appear at breakfast
    return True




def _eligible_recipes(c: Dict[str, Any], meal_slot: str = "") -> List[Dict[str, Any]]:
    return [r for r in _load_recipes() if _recipe_eligible_by_filters(r, c, meal_slot)]

_ALL_SLOTS = ["Breakfast", "Lunch", "Dinner"]

def _slot_names(meals: Any) -> List[str]:
    if isinstance(meals, list) and all(isinstance(m, str) for m in meals):
        return [m for m in meals if m in _ALL_SLOTS] or _ALL_SLOTS
    if isinstance(meals, int):
        if meals == 1:
            return ["Dinner"]
        if meals == 2:
            return ["Lunch", "Dinner"]
        return _ALL_SLOTS   # 3 or any other int → full day
    return _ALL_SLOTS


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
    Return [(canonical_name, unit_family, qty), ...] for a recipe,
    skipping universal staples (salt, water, oil, sugar, etc.) that are
    always assumed available and must never block planning.
    """
    out: list[tuple[str, str, int]] = []
    for ing in rec.get("ingredients", []):
        item = (ing.get("item") or "").strip()
        qty  = int(ing.get("quantity") or 0)
        unit = _normalize_unit(ing.get("unit") or "count")
        if not item or qty <= 0:
            continue
        if _is_universal(item):          # skip salt, water, oil, sugar …
            continue
        name_c, unit_n = _canon_and_unit(item, unit)
        out.append((name_c, unit_n, qty))
    return out

def _shadow_has(shadow: dict[tuple[str, str], int],
                name_c: str, unit_n: str, qty: int) -> bool:
    """
    True if the shadow pantry can cover (name_c, unit_n, qty).
    Tries exact match first, then count↔g conversion for common items.
    """
    if shadow.get((name_c, unit_n), 0) >= qty:
        return True
    # count↔g fallback
    if unit_n == "count":
        have_g = shadow.get((name_c, "g"), 0)
        if have_g > 0:
            as_count = _g_to_count(name_c, have_g)
            if as_count is not None and as_count >= qty:
                return True
    elif unit_n == "g":
        have_cnt = shadow.get((name_c, "count"), 0)
        if have_cnt > 0:
            as_g = _count_to_g(name_c, have_cnt)
            if as_g is not None and as_g >= qty:
                return True
    return False

def _can_fulfill_strict_canon(rec: dict, shadow: dict[tuple[str, str], int]) -> bool:
    """
    True iff every non-universal canonical ingredient can be met from shadow,
    including count↔g conversion for common whole ingredients.
    """
    return all(
        _shadow_has(shadow, name_c, unit_n, qty)
        for name_c, unit_n, qty in _recipe_requirements_canon(rec)
    )

def _apply_deduction_canon(rec: dict, shadow: dict[tuple[str, str], int]) -> None:
    """
    Subtract each canonical ingredient qty from the shadow pantry.
    Applies count↔g conversion so the correct unit is deducted.
    """
    for name_c, unit_n, qty in _recipe_requirements_canon(rec):
        key = (name_c, unit_n)
        if shadow.get(key, 0) >= qty:
            shadow[key] = max(0, shadow[key] - qty)
            continue
        # Deduct from the unit actually stored
        if unit_n == "count":
            g_key = (name_c, "g")
            if shadow.get(g_key, 0) > 0:
                grams = _count_to_g(name_c, qty)
                if grams is not None:
                    shadow[g_key] = max(0, shadow[g_key] - int(grams))
                    continue
        elif unit_n == "g":
            cnt_key = (name_c, "count")
            if shadow.get(cnt_key, 0) > 0:
                counts = _g_to_count(name_c, qty)
                if counts is not None:
                    shadow[cnt_key] = max(0, shadow[cnt_key] - int(counts))
                    continue
        # Fallback: zero out what we have (prevents shadow going negative)
        shadow[key] = 0
        
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
    Fill Day×Meals according to current constraints.

    Modes (set via set_constraints):
      pantry-preferred  — Fill from pantry first (100% covered, unseen-first).
                          Any slot the pantry can't cover falls back to a freeform pick.
                          get_shopping_list covers the freeform gaps.
      pantry-first-strict — 100% pantry only. Unfillable slots are left blank.
      freeform          — Any eligible recipe in every slot.

    Repeat policy:
      allow_repeats=False → avoid placing the same dish in consecutive slots.
      Across all modes, Pass 1 always prefers dishes not yet used in this run.
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

    # Shadow pantry — needed for both pantry modes
    needs_shadow = c["mode"] in ("pantry-first-strict", "pantry-preferred")
    shadow = _shadow_pantry_snapshot_canon() if needs_shadow else {}

    filled = 0
    pantry_slots  = 0   # slots filled 100% from pantry
    shopping_slots = 0  # slots filled via freeform fallback (will need shopping)
    total_slots = len(target_days) * len(meals)

    calc_log = memory.memories.get("calc_log", [])
    if not isinstance(calc_log, list):
        calc_log = []

    # `once_placed` tracks dishes already placed in this run (persists across all slots).
    # Enables Pass 1 to prefer genuinely unseen dishes before repeating.
    once_placed: set[str] = set()

    # Seed prev_dish_lower and once_placed from existing plan (for continue mode)
    prev_dish_lower: Optional[str] = None
    if cont and plan:
        for d_key, d_row in plan.items():
            for dish_val in d_row.values():
                clean = (dish_val or "").strip("✅ ").strip().lower()
                if clean:
                    once_placed.add(clean)
        # Find the very last filled slot so consecutive-repeat guard works correctly
        sorted_days = sorted(plan.keys(), key=lambda d: int(re.sub(r"\D", "", d) or "0"))
        for d_key in reversed(sorted_days):
            for m in reversed(meals):
                dish_val = (plan.get(d_key, {}).get(m) or "").strip()
                if dish_val:
                    prev_dish_lower = dish_val.lower()
                    break
            if prev_dish_lower:
                break

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

            pick = None
            pick_reason = None

            no_consec = not c.get("allow_repeats", True)

            if c["mode"] in ("pantry-first-strict", "pantry-preferred"):
                once_list = _coverable_once_sorted(slot_candidates, shadow)

                # PASS 1 — unseen pantry dish
                for r in once_list:
                    name_l = (r.get("name") or "").strip().lower()
                    if name_l in once_placed:
                        continue
                    if no_consec and name_l == prev_dish_lower:
                        continue
                    pick        = r
                    pick_reason = "pantry"
                    _apply_deduction_canon(pick, shadow)
                    once_placed.add(name_l)
                    break

                # PASS 2 — any pantry dish (repeat allowed)
                if pick is None:
                    for r in once_list:
                        name_l = (r.get("name") or "").strip().lower()
                        if no_consec and name_l == prev_dish_lower:
                            continue
                        pick        = r
                        pick_reason = "pantry"
                        _apply_deduction_canon(pick, shadow)
                        break

                # PASS 3 — freeform fallback (pantry-preferred only)
                if pick is None and c["mode"] == "pantry-preferred":
                    shuffled = list(slot_candidates)
                    random.shuffle(shuffled)
                    for r in shuffled:
                        name_l = (r.get("name") or "").strip().lower()
                        if no_consec and name_l == prev_dish_lower:
                            continue
                        pick        = r
                        pick_reason = "shopping"
                        break

            else:
                # Freeform — any eligible recipe, shuffled for variety
                shuffled = list(slot_candidates)
                random.shuffle(shuffled)
                for r in shuffled:
                    name_l = (r.get("name") or "").strip().lower()
                    if no_consec and name_l == prev_dish_lower:
                        continue
                    pick        = r
                    pick_reason = "shopping"
                    break

            # ---- assign or skip unfillable slot
            if not pick:
                day_row[meal] = ""   # leave blank; continue to next slot
                continue

            dish = (pick.get("name") or "").strip()
            day_row[meal] = dish
            prev_dish_lower = dish.lower()
            filled += 1
            if pick_reason == "pantry":
                pantry_slots += 1
            else:
                shopping_slots += 1

            calc_log.append({
                "slot": f"{day_key} » {meal}",
                "dish": dish,
                "source": pick_reason or "",
                "virtual_deducted": [],
                "still_missing": [],
            })

    # All slots attempted — build summary
    memory.memories["plan"] = plan
    memory.memories["calc_log"] = calc_log

    lines = []
    for d in [f"Day{n}" for n in target_days]:
        row = plan.get(d, {})
        parts = [row.get(m) or "—" for m in meals]
        lines.append(f"{d}: " + ", ".join(parts))

    label = _MODE_LABELS.get(c["mode"], c["mode"])
    msg = [f"Mode: {label}. Filled {filled}/{total_slots} slots."]
    if lines:
        msg.append(" " + " ".join(lines))

    mode = c["mode"]
    empty = total_slots - filled
    if mode == "pantry-preferred":
        if shopping_slots > 0 and pantry_slots > 0:
            msg.append(f" {pantry_slots} slot(s) covered by your pantry, {shopping_slots} slot(s) need shopping. Call get_shopping_list for the exact items to buy.")
        elif pantry_slots == filled and shopping_slots == 0:
            msg.append(" Your pantry covers everything — no shopping needed!")
        elif pantry_slots == 0:
            msg.append(" Your pantry couldn't cover any slot fully — all meals need shopping. Call get_shopping_list.")
    elif mode == "pantry-first-strict":
        if empty > 0:
            msg.append(f" {empty} slot(s) left blank — pantry ran short. Switch to pantry-preferred to fill gaps with a shopping list.")
    else:  # freeform
        if filled > 0:
            msg.append(" Call get_shopping_list for what to buy.")

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
    """Sum required qty per (item,unit) across the whole plan, skipping universal staples."""
    need: Dict[Tuple[str,str], int] = {}
    recipes = {r["name"].lower(): r for r in _load_recipes()}
    for day_dict in plan.values():
        for dish in day_dict.values():
            rec = recipes.get(dish.lower())
            if not rec:
                continue
            for ing in rec.get("ingredients", []):
                raw_item = (ing.get("item") or "").strip()
                if not raw_item or _is_universal(raw_item):
                    continue
                item = _canon(raw_item)
                _, unit = _canon_and_unit(item, ing.get("unit") or "count")
                qty  = int(ing.get("quantity") or 0)
                if qty <= 0 or not item:
                    continue
                need[(item, unit)] = need.get((item, unit), 0) + qty
    return need

def _quantity_shopping_deficits(plan: Dict[str, Dict[str, str]]) -> List[Dict[str, Any]]:
    """Compare plan needs to pantry and return deficits with quantities.

    Handles count↔g unit mismatches (e.g. pantry has 6 garlic count,
    recipe needs 10g garlic → converts and correctly shows no deficit).
    Also deduplicates items that appear in both count and g across recipes.
    """
    pantry = _load_pantry()
    needs = _collect_plan_requirements(plan)

    # Merge count+g needs for the same item into a single unit (grams preferred)
    # so "capsicum 1 count" and "capsicum 100g" don't show as two separate rows.
    merged: Dict[Tuple[str, str], int] = {}
    for (item, unit), qty in needs.items():
        if unit == "count":
            g = _count_to_g(item, qty)
            if g is not None:
                merged[(item, "g")] = merged.get((item, "g"), 0) + int(g)
                continue
        merged[(item, unit)] = merged.get((item, unit), 0) + qty

    deficits: List[Dict[str, Any]] = []
    for (item, unit), need_qty in merged.items():
        # Exact unit match
        key = _find_matching_key(pantry, item, unit)
        have = int(pantry.get(key, 0)) if key else 0

        # Fallback: try alternate unit families with conversion
        if have == 0:
            for alt_unit in ("g", "ml", "count"):
                if alt_unit == unit:
                    continue
                alt_key = _find_matching_key(pantry, item, alt_unit)
                if not alt_key:
                    continue
                alt_qty = int(pantry.get(alt_key, 0))
                converted: Optional[float] = None
                if unit == "g" and alt_unit == "count":
                    converted = _count_to_g(item, alt_qty)
                elif unit == "count" and alt_unit == "g":
                    converted = _g_to_count(item, alt_qty)
                elif unit == "g" and alt_unit == "ml":
                    converted = _ml_to_g(item, alt_qty)
                elif unit == "ml" and alt_unit == "g":
                    converted = _g_to_ml(item, alt_qty)
                if converted is not None:
                    have = int(converted)
                    break

        buy = max(0, need_qty - have)
        if buy > 0:
            deficits.append({"item": item, "unit": unit, "need": need_qty, "have": have, "buy": buy})

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
