# tools/expiry_tools.py
# Track expiry dates for pantry items. Alert when items are expiring soon.
# Data persists to data/expiry.json so it survives restarts.

from __future__ import annotations

import json
import os
import datetime
from typing import Dict, Any, List, Optional

from langchain_core.tools import tool

ROOT_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DATA_DIR    = os.path.join(ROOT_DIR, "data")
EXPIRY_PATH = os.path.join(DATA_DIR, "expiry.json")

os.makedirs(DATA_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Storage helpers
# ─────────────────────────────────────────────────────────────────────────────

def _read_expiry() -> Dict[str, Any]:
    try:
        with open(EXPIRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _write_expiry(data: Dict[str, Any]) -> None:
    with open(EXPIRY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers (used by UI without going through agent)
# ─────────────────────────────────────────────────────────────────────────────

def get_expiring_items(within_days: int = 3) -> List[Dict[str, Any]]:
    """
    Return pantry items expiring within *within_days* days.
    Each item: {"item": str, "expires": "YYYY-MM-DD", "days_left": int}
    """
    expiry = _read_expiry()
    today  = datetime.date.today()
    result = []
    for item, meta in expiry.items():
        exp_str = (meta if isinstance(meta, str) else meta.get("expires", ""))
        if not exp_str:
            continue
        try:
            exp_date  = datetime.date.fromisoformat(exp_str)
            days_left = (exp_date - today).days
        except ValueError:
            continue
        if days_left <= within_days:
            result.append({
                "item":      item,
                "expires":   exp_str,
                "days_left": days_left,
            })
    result.sort(key=lambda x: x["days_left"])
    return result


def get_all_expiry() -> Dict[str, Any]:
    return _read_expiry()


# ─────────────────────────────────────────────────────────────────────────────
# LangChain tools
# ─────────────────────────────────────────────────────────────────────────────

@tool
def set_expiry(item: str, expires: str) -> str:
    """
    Set an expiry date for a pantry item.

    *item*: ingredient name (e.g. "milk")
    *expires*: date as YYYY-MM-DD (e.g. "2026-04-22")

    Example: set_expiry("milk", "2026-04-22")
    """
    item = item.strip().lower()
    if not item:
        return "⚠️ Item name is required."
    try:
        exp_date = datetime.date.fromisoformat(expires.strip())
    except ValueError:
        return f"⚠️ Invalid date '{expires}'. Use YYYY-MM-DD format (e.g. 2026-04-22)."

    expiry = _read_expiry()
    expiry[item] = {"expires": str(exp_date)}
    _write_expiry(expiry)

    today     = datetime.date.today()
    days_left = (exp_date - today).days
    if days_left < 0:
        return f"⚠️ Set expiry for **{item}** — already expired {-days_left} day(s) ago!"
    if days_left == 0:
        return f"⚠️ Set expiry for **{item}** — expires TODAY."
    return f"✅ Set expiry for **{item}**: {exp_date} ({days_left} day(s) from now)."


@tool
def remove_expiry(item: str) -> str:
    """Remove the expiry date for a pantry item."""
    item  = item.strip().lower()
    expiry = _read_expiry()
    if item not in expiry:
        return f"No expiry date found for **{item}**."
    del expiry[item]
    _write_expiry(expiry)
    return f"🗑️ Removed expiry date for **{item}**."


@tool
def get_expiring_soon(within_days: int = 3) -> str:
    """
    List pantry items expiring within *within_days* days.
    Suggests recipes that use those ingredients to prevent waste.
    """
    items = get_expiring_items(within_days=int(within_days))
    if not items:
        return f"✅ No pantry items expiring in the next {within_days} days."

    lines = [f"⚠️ **Items expiring soon (within {within_days} days):**"]
    expiring_names = []
    for it in items:
        d = it["days_left"]
        if d < 0:
            label = f"expired {-d} day(s) ago!"
        elif d == 0:
            label = "expires TODAY"
        elif d == 1:
            label = "expires tomorrow"
        else:
            label = f"expires in {d} days ({it['expires']})"
        lines.append(f"- **{it['item'].title()}** — {label}")
        expiring_names.append(it["item"])

    # Suggest recipes that use these items
    if expiring_names:
        try:
            from tools.cuisine_tools import find_recipes_by_items
            suggestion = find_recipes_by_items.invoke({
                "items": expiring_names,
                "k": 3,
            })
            if suggestion and "📭" not in suggestion:
                lines.append("\n**Use them up — recipes you can make:**")
                lines.append(suggestion)
        except Exception:
            pass

    return "\n".join(lines)
