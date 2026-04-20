# tools/history_tools.py
# Meal history, recipe ratings, food waste impact tracking, variety suggestions.
# All data persists to data/ JSON files so it survives server restarts.

from __future__ import annotations

import json
import os
import datetime
from typing import Dict, Any, List, Optional

from langchain_core.tools import tool

ROOT_DIR        = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DATA_DIR        = os.path.join(ROOT_DIR, "data")
HISTORY_PATH    = os.path.join(DATA_DIR, "history.json")
FEEDBACK_PATH   = os.path.join(DATA_DIR, "feedback.json")
IMPACT_PATH     = os.path.join(DATA_DIR, "impact.json")

os.makedirs(DATA_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Low-level JSON helpers
# ─────────────────────────────────────────────────────────────────────────────

def _read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def _write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# Meal History
# ─────────────────────────────────────────────────────────────────────────────
# history.json  →  list of:
# { "dish": str, "cooked_at": ISO str, "day": str, "meal": str,
#   "ingredients_consumed": [{"item": str, "qty": int, "unit": str}],
#   "household_size": int, "waste_saved_g": float }

def log_meal_to_history(
    dish: str,
    day: Optional[str] = None,
    meal: Optional[str] = None,
    ingredients_consumed: Optional[List[Dict]] = None,
    household_size: int = 1,
) -> None:
    """Append a cooked-meal record to history.json and update impact stats."""
    history: List[Dict] = _read_json(HISTORY_PATH, [])
    waste_saved_g = sum(
        ing.get("qty", 0) for ing in (ingredients_consumed or [])
        if ing.get("unit") == "g"
    )
    record = {
        "dish":                  dish,
        "cooked_at":             datetime.datetime.now().isoformat(timespec="seconds"),
        "day":                   day or "",
        "meal":                  meal or "",
        "ingredients_consumed":  ingredients_consumed or [],
        "household_size":        household_size,
        "waste_saved_g":         waste_saved_g,
    }
    history.append(record)
    _write_json(HISTORY_PATH, history)
    _update_impact(waste_saved_g=waste_saved_g, pantry_meal=True)


def get_history_raw() -> List[Dict]:
    return _read_json(HISTORY_PATH, [])


def recently_cooked_dishes(within_days: int = 7) -> List[str]:
    """Return dish names cooked within the last N days (lowercase)."""
    cutoff = datetime.datetime.now() - datetime.timedelta(days=within_days)
    out = []
    for rec in get_history_raw():
        try:
            ts = datetime.datetime.fromisoformat(rec["cooked_at"])
        except Exception:
            continue
        if ts >= cutoff:
            out.append(rec["dish"].lower())
    return list(dict.fromkeys(out))  # deduplicated, preserving order


@tool
def get_cook_history(days: int = 30) -> str:
    """Return a summary of meals cooked in the last *days* days."""
    history = get_history_raw()
    if not history:
        return "No cooking history yet. Mark meals as cooked to start tracking!"

    cutoff = datetime.datetime.now() - datetime.timedelta(days=int(days))
    recent = []
    for rec in history:
        try:
            ts = datetime.datetime.fromisoformat(rec["cooked_at"])
        except Exception:
            continue
        if ts >= cutoff:
            recent.append(rec)

    if not recent:
        return f"No meals cooked in the last {days} days."

    lines = [f"**Meals cooked in the last {days} days** ({len(recent)} total):"]
    for rec in sorted(recent, key=lambda r: r["cooked_at"], reverse=True)[:20]:
        dt = rec["cooked_at"][:10]
        lines.append(f"- {rec['dish'].title()} — {dt} ({rec.get('meal','').lower() or 'meal'})")
    return "\n".join(lines)


@tool
def suggest_variety(days: int = 7) -> str:
    """Suggest recipes not cooked in the last *days* days, using pantry coverage."""
    from tools.meal_plan_tools import _load_pantry, _can_fulfill_strict_canon, _shadow_pantry_snapshot_canon
    from tools.cuisine_tools import _load as _load_recipes

    avoid = set(recently_cooked_dishes(within_days=int(days)))
    shadow = _shadow_pantry_snapshot_canon()
    recipes = _load_recipes()

    # Prefer highly-rated dishes
    feedback = get_feedback_raw()

    def _score(r: dict) -> tuple:
        name_l = (r.get("name") or "").lower()
        fb = feedback.get(name_l, {})
        rating_score = fb.get("thumbs_up", 0) - fb.get("thumbs_down", 0)
        coverable    = _can_fulfill_strict_canon(r, dict(shadow))
        return (not coverable, name_l in avoid, -rating_score)

    candidates = sorted(recipes, key=_score)

    # Pantry-coverable first, then anything not recently cooked
    pantry_new  = [r for r in candidates if r["name"].lower() not in avoid
                   and _can_fulfill_strict_canon(r, dict(shadow))][:5]
    pantry_any  = [r for r in candidates if _can_fulfill_strict_canon(r, dict(shadow))
                   and r["name"].lower() in avoid][:3]

    lines = []
    if pantry_new:
        lines.append(f"**Dishes you haven't cooked in {days}+ days (pantry-ready):**")
        for r in pantry_new:
            name_l = r["name"].lower()
            fb = feedback.get(name_l, {})
            stars = "👍" if fb.get("thumbs_up", 0) > fb.get("thumbs_down", 0) else ""
            lines.append(f"- {r['name'].title()} ({r['cuisine']}) {stars}")
    if not pantry_new:
        lines.append(f"All pantry-coverable dishes have been cooked recently (within {days} days).")
        if pantry_any:
            lines.append("\n**Pantry-ready options (even if cooked recently):**")
            for r in pantry_any[:3]:
                lines.append(f"- {r['name'].title()} ({r['cuisine']})")

    return "\n".join(lines) if lines else "No suggestions available."


# ─────────────────────────────────────────────────────────────────────────────
# Recipe Feedback / Ratings
# ─────────────────────────────────────────────────────────────────────────────
# feedback.json  →  { "<dish_lower>": {"thumbs_up": int, "thumbs_down": int,
#                                       "last_rated": ISO, "last_rating": "up"|"down"} }

def get_feedback_raw() -> Dict[str, Any]:
    return _read_json(FEEDBACK_PATH, {})


def get_recipe_rating(recipe_name: str) -> Optional[str]:
    """Return "up", "down", or None for the most recent rating of a recipe."""
    fb = get_feedback_raw()
    return (fb.get(recipe_name.lower()) or {}).get("last_rating")


@tool
def rate_recipe(recipe_name: str, rating: str) -> str:
    """
    Rate a recipe. *rating* must be 'up' (👍) or 'down' (👎).

    Example: rate_recipe("Palak Paneer", "up")
    """
    rating = rating.strip().lower()
    if rating not in ("up", "down", "thumbs_up", "thumbs_down", "good", "bad",
                      "like", "dislike", "yes", "no", "1", "0"):
        return "⚠️ Rating must be 'up' (liked it) or 'down' (didn't like it)."

    normalized = "up" if rating in ("up", "thumbs_up", "good", "like", "yes", "1") else "down"

    feedback: Dict[str, Any] = get_feedback_raw()
    key = recipe_name.strip().lower()
    entry = feedback.setdefault(key, {"thumbs_up": 0, "thumbs_down": 0})
    entry[f"thumbs_{normalized}"] = entry.get(f"thumbs_{normalized}", 0) + 1
    entry["last_rated"]  = datetime.datetime.now().isoformat(timespec="seconds")
    entry["last_rating"] = normalized
    _write_json(FEEDBACK_PATH, feedback)

    emoji = "👍" if normalized == "up" else "👎"
    return f"{emoji} Rated **{recipe_name.title()}** thumbs {normalized}. Thanks for the feedback!"


@tool
def get_top_recipes(limit: int = 10) -> str:
    """Return the top-rated recipes based on thumbs-up votes."""
    feedback = get_feedback_raw()
    if not feedback:
        return "No recipe ratings yet. Rate dishes as you cook them!"

    scored = []
    for name, fb in feedback.items():
        net = fb.get("thumbs_up", 0) - fb.get("thumbs_down", 0)
        scored.append((net, fb.get("thumbs_up", 0), name))

    scored.sort(reverse=True)
    top = scored[:int(limit)]
    lines = [f"**Your top-rated recipes:**"]
    for net, ups, name in top:
        up_icon = "👍" * min(ups, 5)
        lines.append(f"- {name.title()} — {up_icon} ({net:+d} net)")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Food Waste Impact
# ─────────────────────────────────────────────────────────────────────────────
# impact.json  →
# { "total_meals_cooked": int, "total_pantry_meals": int,
#   "total_waste_saved_g": float, "sessions": int }

_CO2_PER_KG_FOOD_WASTE = 2.5  # kg CO2 equivalent per kg food waste


def _update_impact(waste_saved_g: float = 0, pantry_meal: bool = False) -> None:
    impact: Dict[str, Any] = _read_json(IMPACT_PATH, {})
    impact.setdefault("total_meals_cooked", 0)
    impact.setdefault("total_pantry_meals", 0)
    impact.setdefault("total_waste_saved_g", 0.0)
    impact["total_meals_cooked"]  += 1
    impact["total_waste_saved_g"] += waste_saved_g
    if pantry_meal:
        impact["total_pantry_meals"] += 1
    _write_json(IMPACT_PATH, impact)


def get_impact_raw() -> Dict[str, Any]:
    return _read_json(IMPACT_PATH, {
        "total_meals_cooked": 0,
        "total_pantry_meals": 0,
        "total_waste_saved_g": 0.0,
    })


@tool
def get_impact_stats() -> str:
    """Return your food waste impact stats — how much food and CO2 you've saved."""
    impact = get_impact_raw()
    total_meals   = impact.get("total_meals_cooked", 0)
    pantry_meals  = impact.get("total_pantry_meals", 0)
    waste_saved_g = float(impact.get("total_waste_saved_g", 0))
    waste_kg      = waste_saved_g / 1000
    co2_saved_kg  = waste_kg * _CO2_PER_KG_FOOD_WASTE

    if total_meals == 0:
        return "No impact data yet. Start cooking to track your food waste savings!"

    lines = [
        "🌱 **Your Food Waste Impact**",
        f"- Meals tracked: **{total_meals}**",
        f"- Pantry-first meals: **{pantry_meals}** ({int(pantry_meals/total_meals*100) if total_meals else 0}%)",
        f"- Estimated food saved: **{waste_kg:.1f} kg**",
        f"- CO₂ equivalent avoided: **{co2_saved_kg:.2f} kg**",
        "",
        "_Every pantry-first meal reduces food waste. Keep it up!_",
    ]
    return "\n".join(lines)
