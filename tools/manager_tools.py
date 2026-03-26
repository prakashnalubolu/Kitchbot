"""
Lightweight manager utilities kept for shared memory and the string-only
missing_ingredients tool. No agent-to-agent wrappers are used anymore.
"""

from __future__ import annotations
import json, os, re
from typing import Dict, Any, List, Tuple, Optional
from tools.textnorm import canonical_key, canonical_and_unit


from langchain_core.tools import tool
from langchain.memory import SimpleMemory

# Expose a small memory object so the UI can still show "Manager slots".
memory: SimpleMemory = SimpleMemory(memories={})

# --------------------------------------------------------------------- Paths
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PANTRY_JSON_PATH = os.path.join(ROOT_DIR, "data", "pantry.json")

# ----------------------------------------------------------------- Helpers

def _normalise(name: str) -> str:
    """Lower-case and strip very simple plurals (onions → onion)."""
    n = name.strip().lower()
    if n.endswith("ies"):
        n = n[:-3] + "y"
    elif n.endswith("s") and len(n) > 3:
        n = n[:-1]
    return n

# Generic descriptors we drop for base-name matching (kept intentionally short)
_DESCRIPTORS = {
    "white", "boneless", "skinless", "lean", "fresh", "frozen", "dried",
    "ground", "powdered", "powder", "whole", "sliced", "chopped", "fillet", "fillets",
    "medium", "large", "small","red", "green", "yellow", "black", "brown",
}

# A *tiny* alias map (not a big dictionary) to collapse very common variants
_ALIASES = {
    "chilli": "chili", "chilies": "chili", "chillies": "chili",
    "scallion": "spring onion", "scallions": "spring onion",
    "coriander leaves": "coriander leave", "cilantro": "coriander leave",
    "curry leave": "curry leaf",
    "curry leaves": "curry leaf",
}

_plural_re = re.compile(r"(?i)(ies|s)$")

def _depluralize(w: str) -> str:
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith("s") and len(w) > 3:
        return w[:-1]
    return w

# ---------------------- Recipe access (structured, no agent hop)
from tools.cuisine_tools import _load as _load_recipes

def _load_recipe_by_name(name: str) -> Optional[Dict[str, Any]]:
    name = _clean_name(name)
    name_l = name.strip().lower()
    for r in _load_recipes():
        if r["name"].strip().lower() == name_l:
            return r
    return None

# ----------------------------------------------------------------- Tool: gaps
def _clean_name(s: str) -> str:
    s = str(s or "").strip()
    # strip balanced outer quotes
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1]
    # strip any stray quotes/whitespace and collapse spaces
    s = s.strip('\'"\n\r\t ')
    s = re.sub(r"\s+", " ", s)
    return s


def _canonical_item_name(name: str) -> str:
    """Lowercase, drop generic descriptors, collapse trivial aliases, depluralize."""
    s = _clean_name(name).lower()
    # collapse multiword aliases first
    for k, v in sorted(_ALIASES.items(), key=lambda kv: -len(kv[0])):
        s = re.sub(rf"\b{k}\b", v, s)
    # drop descriptors
    tokens = [t for t in re.split(r"\W+", s) if t]
    tokens = [t for t in tokens if t not in _DESCRIPTORS]
    # depluralize each token (lightweight)
    tokens = [_depluralize(t) for t in tokens]
    # heuristics: keep up to two words for things like "spring onion"
    if not tokens:
        return ""
    if len(tokens) >= 2 and "spring" in tokens and "onion" in tokens:
        return "spring onion"
    if len(tokens) >= 2 and tokens[-2] == "fish" and tokens[-1] == "fillet":
        return "fish"
    # fallback: last token as head noun
    return " ".join(tokens[-2:]) if len(tokens) > 1 else tokens[-1]

def canonical_item_name(name: str) -> str:
    return _canonical_item_name(name)

# ------------------------------- Pantry IO ----------------------------------
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


from tools.textnorm import canonical_key
# ----------------------------- Tools ----------------------------------------
_name_unit_re = re.compile(r"^\s*(.*?)\s*\(([^)]+)\)\s*$")

def _normalize_unit(u: str | None) -> str:
    if not u: return "count"
    s = str(u).strip().lower()
    m = {
        "g":"g","gram":"g","grams":"g","gms":"g","kg":"g","kilogram":"g","kilograms":"g",
        "ml":"ml","milliliter":"ml","milliliters":"ml","millilitre":"ml","millilitres":"ml",
        "l":"ml","liter":"ml","liters":"ml","litre":"ml","litres":"ml",
        "count":"count","piece":"count","pieces":"count","pc":"count","pcs":"count"
    }
    return m.get(s, s)

def _split_pantry_key(key: str) -> tuple[str, str]:
    m = _name_unit_re.match(key)
    if not m:
        base = key.split("(")[0]
        return base.strip(), "count"
    return m.group(1).strip(), _normalize_unit(m.group(2))
# Grams-per-count for common whole ingredients used in recipes.
# Used when recipe wants grams but pantry has count (or vice versa).
_G_PER_COUNT: dict[str, float] = {
    "garlic": 5.0,      # one clove ≈ 5 g
    "clove": 5.0,
    "onion": 100.0,     # medium onion ≈ 100 g
    "tomato": 100.0,    # medium tomato ≈ 100 g
    "chili": 5.0,       # one chili ≈ 5 g
    "chilli": 5.0,
    "egg": 50.0,        # one egg ≈ 50 g
    "lemon": 60.0,
    "lime": 60.0,
    "potato": 150.0,    # medium potato ≈ 150 g
    "carrot": 80.0,
}

def _count_to_g(name: str, count_qty: int) -> Optional[float]:
    """Convert a count quantity to grams using the heuristic table. Returns None if unknown."""
    for keyword, gpcount in _G_PER_COUNT.items():
        if keyword in name:
            return count_qty * gpcount
    return None

def _g_to_count(name: str, g_qty: int) -> Optional[float]:
    """Convert a gram quantity to count. Returns None if unknown."""
    for keyword, gpcount in _G_PER_COUNT.items():
        if keyword in name:
            return g_qty / gpcount
    return None

def _pantry_covers(pantry_map: dict[tuple[str, str], int],
                   need_name: str, need_unit: str, need_qty: int) -> bool:
    """
    Return True if the pantry has enough of an ingredient to satisfy a recipe need.

    Two-pass check:
      1. Exact canonical name + unit match.
      2. Fuzzy name match (uses _fuzzy_covers from cuisine_tools) with same-unit
         or count↔g conversion via heuristic table.
    """
    from tools.cuisine_tools import _fuzzy_covers

    # Pass 1: exact match
    have = pantry_map.get((need_name, need_unit), 0)
    if have >= need_qty:
        return True

    # Pass 2: fuzzy name match across all pantry entries
    best_have = have  # track partial coverage for shortfall reporting
    for (p_name, p_unit), p_qty in pantry_map.items():
        if not _fuzzy_covers(p_name, need_name):
            continue
        # Same unit family — direct compare
        if p_unit == need_unit:
            if p_qty >= need_qty:
                return True
            best_have = max(best_have, p_qty)
            continue
        # count ↔ g conversion
        if p_unit == "count" and need_unit == "g":
            converted = _count_to_g(p_name or need_name, p_qty)
            if converted is not None and converted >= need_qty:
                return True
        elif p_unit == "g" and need_unit == "count":
            converted = _g_to_count(p_name or need_name, p_qty)
            if converted is not None and converted >= need_qty:
                return True

    return False

# Ingredients assumed to be always available in any kitchen — never flag as missing.
_UNIVERSAL_INGREDIENTS = {
    "salt", "water", "oil", "cooking oil", "vegetable oil", "black pepper", "pepper",
    "sugar", "white sugar", "baking soda", "baking powder",
}

def _is_universal(item: str) -> bool:
    """Return True if an ingredient is so common it should never be flagged missing."""
    s = _clean_name(item).lower()
    # exact match
    if s in _UNIVERSAL_INGREDIENTS:
        return True
    # single-token suffix match (e.g. "sea salt" → "salt", "olive oil" → "oil")
    tokens = s.split()
    if tokens and tokens[-1] in _UNIVERSAL_INGREDIENTS:
        return True
    return False


@tool
def missing_ingredients(dish: str) -> str:
    """
    Tell the user which ingredients for *dish* are not in their pantry.
    STRING-ONLY input. Returns a short natural-language sentence.

    Matching rules:
    • Fuzzy name matching (e.g. 'chicken' covers 'chicken breast', 'dried chilli' covers 'dried red chilies').
    • Units normalized to g/ml/count; count↔g conversion via heuristics for common items.
    • Universal staples (salt, oil, water, sugar, black pepper) are never flagged as missing.
    """
    dish = _clean_name(dish)
    if not isinstance(dish, str) or not dish:
        return "Please provide a dish name."

    recipe = _load_recipe_by_name(dish)
    if not recipe:
        return f"⚠️ Recipe '{dish}' not found."

    # Build canonical pantry map: (canon_name, unit) -> qty
    pantry_raw = _load_pantry()
    pantry_map: dict[tuple[str, str], int] = {}
    for k, v in pantry_raw.items():
        base_raw, unit_raw = _split_pantry_key(k)
        cname, cunit = canonical_and_unit(base_raw, unit_raw)
        pantry_map[(cname, cunit)] = pantry_map.get((cname, cunit), 0) + int(v or 0)

    deficits: list[str] = []
    for ing in recipe.get("ingredients", []):
        raw_item = str(ing.get("item", "")).strip()
        if not raw_item:
            continue
        need_qty = int(ing.get("quantity", 0) or 0)
        unit_raw = _normalize_unit(ing.get("unit") or "count")
        if need_qty <= 0:
            continue
        # Skip universal staples — always assumed available
        if _is_universal(raw_item):
            continue

        cname, cunit = canonical_and_unit(raw_item, unit_raw)
        if not _pantry_covers(pantry_map, cname, cunit, need_qty):
            deficits.append(f"{need_qty} {cunit} {raw_item}")

    dish_title = dish.strip().title()
    if not deficits:
        return f"You already have every ingredient for {dish_title}!"
    if len(deficits) == 1:
        return f"You'll still need {deficits[0]} to cook {dish_title}."
    *rest, last = deficits
    return f"You'll still need {', '.join(rest)} and {last} to cook {dish_title}."


# ---------- Substitution suggester (schema-bound, deterministic heuristics) --
def _aggregate_pantry_by_base(pantry: Dict[str, int]) -> Dict[str, Dict[str, int]]:
    """
    Returns { base_item: {unit: qty, ...}, ... } using canonical base names.
    """
    out: Dict[str, Dict[str, int]] = {}
    for k, v in pantry.items():
        b, u = _split_pantry_key(k)
        base = _canonical_item_name(b)
        out.setdefault(base, {})
        out[base][u] = int(v)
    return out

# Substitution table: (keyword_in_missing, keyword_in_base) -> (prep_note, confidence)
# Order matters — first match wins.
_SUB_TABLE: list[tuple[str, str, str, float]] = [
    # fish / seafood
    ("fillet",          "fish",     "Cut into boneless fillets; remove skin if present.", 0.84),
    ("shrimp",          "prawn",    "Use interchangeably; adjust cooking time slightly.",  0.90),
    ("prawn",           "shrimp",   "Use interchangeably; adjust cooking time slightly.",  0.90),
    # chili variants
    ("dried",           "chili",    "Dry-roast fresh chilies 2–3 min to mimic dried heat.", 0.75),
    ("chili flake",     "chili",    "Crush dried chilies or use 1 tsp flakes per 2 fresh.", 0.80),
    # dairy
    ("heavy cream",     "cream",    "Use as-is; any cream works for most sauces.",         0.88),
    ("double cream",    "cream",    "Use as-is; any cream works for most sauces.",         0.88),
    ("sour cream",      "yogurt",   "Use plain yogurt; add a squeeze of lemon for tang.",  0.78),
    ("yogurt",          "cream",    "Use plain yogurt in place of cream in curries.",       0.75),
    ("butter",          "ghee",     "Use butter instead of ghee; it browns faster.",        0.85),
    ("ghee",            "butter",   "Clarify butter by skimming foam, or use as-is.",      0.85),
    # oils
    ("sesame oil",      "oil",      "Use a neutral oil; add a drop of toasted sesame if available.", 0.65),
    ("olive oil",       "oil",      "Substitute any neutral cooking oil.",                  0.82),
    # proteins
    ("chicken breast",  "chicken",  "Use any chicken cut; adjust cook time accordingly.",  0.90),
    ("ground beef",     "beef",     "Mince or finely chop beef as substitute.",            0.80),
    ("ground chicken",  "chicken",  "Mince or finely chop chicken as substitute.",        0.80),
    ("tofu",            "paneer",   "Use firm tofu instead of paneer; press out moisture.", 0.72),
    ("paneer",          "tofu",     "Use firm pressed tofu; season with a pinch of salt.", 0.72),
    # aromatics
    ("spring onion",    "onion",    "Use regular onion; milder flavor.",                   0.80),
    ("scallion",        "onion",    "Use regular onion; milder flavor.",                   0.80),
    ("shallot",         "onion",    "Use 1 medium onion for every 3 shallots.",            0.82),
    # acids
    ("lemon juice",     "lime",     "Use lime juice; flavor is slightly more floral.",     0.88),
    ("lime juice",      "lemon",    "Use lemon juice; very similar acidity.",              0.88),
    ("rice vinegar",    "vinegar",  "Use white vinegar with a pinch of sugar.",            0.75),
    # condiments / sauces
    ("soy sauce",       "tamari",   "Use tamari or coconut aminos as soy-free swap.",      0.82),
    ("fish sauce",      "soy sauce","Mix soy sauce with a squeeze of lime for umami.",     0.68),
    ("oyster sauce",    "soy sauce","Mix soy sauce + a pinch of sugar to approximate.",    0.70),
    # herbs
    ("cilantro",        "coriander","Same herb — use interchangeably.",                    0.95),
    ("coriander",       "cilantro", "Same herb — use interchangeably.",                    0.95),
    ("parsley",         "cilantro", "Milder flavor; add a little lemon zest.",             0.65),
    ("basil",           "herb",     "Works in most herb roles; slightly sweeter.",         0.70),
    # starches
    ("cornstarch",      "flour",    "Use 2 tsp flour per 1 tsp cornstarch for thickening.", 0.78),
    ("potato starch",   "cornstarch","Use 1:1 as thickener; results may be slightly cloudier.", 0.80),
    # sugars
    ("brown sugar",     "sugar",    "Use white sugar + a drop of molasses or maple.",      0.85),
    ("palm sugar",      "sugar",    "Use brown sugar or jaggery for a similar caramel note.", 0.80),
]

def _prep_note_for(missing_raw: str, base: str) -> str:
    s = _clean_name(missing_raw).lower()
    b = base.lower()
    for kw_miss, kw_base, prep, _ in _SUB_TABLE:
        if kw_miss in s and kw_base in b:
            return prep
    return ""

def _confidence_for(missing_raw: str, base: str) -> float:
    s = _clean_name(missing_raw).lower()
    b = base.lower()
    for kw_miss, kw_base, _, conf in _SUB_TABLE:
        if kw_miss in s and kw_base in b:
            return conf
    return 0.70  # default for close base-name matches

@tool
def suggest_substitutions(
    dish: str,
    deficits: List[Dict[str, Any]],
    pantry: Optional[List[Dict[str, Any]]] = None,
    constraints: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Propose substitutions for remaining deficits using the user's pantry.

    deficits: list of {"item":"dried chili","need_qty":5,"unit":"count"}
    pantry: optional list of {"item":"red chili","qty":12,"unit":"count"}
    constraints: optional {"allow_prep": true, "max_subs_per_item": 2}

    Output (JSON string):
    {"subs":[
      {"missing":"dried chili",
       "use":[{"item":"red chili","qty":5,"unit":"count"}],
       "prep":"dry-roast 2–3 min",
       "confidence":0.78,
       "reason":"Close variant; roasting approximates dried"}
    ]}
    """
    pantry_list = pantry or []
    allow_prep = bool((constraints or {}).get("allow_prep", True))

    # Build a base-name index for the pantry
    # Prefer the snapshot passed in; fall back to file.
    if pantry_list:
        pantry: Dict[str, int] = {}
        for p in pantry_list:
            k = f"{_canonical_item_name(p.get('item',''))} ({_normalize_unit(p.get('unit'))})"
            pantry[k] = pantry.get(k, 0) + int(p.get("qty", 0))
    else:
        pantry = _load_pantry()

    pantry_by_base = _aggregate_pantry_by_base(pantry)

    results: List[Dict[str, Any]] = []

    for d in deficits:
        raw_item = str(d.get("item",""))
        unit = _normalize_unit(d.get("unit") or "count")
        need_qty = int(d.get("need_qty", 0) or 0)
        if not raw_item or need_qty <= 0:
            continue

        base = _canonical_item_name(raw_item)

        # 1) If pantry already has the base in the same unit family, suggest direct use
        unit_map = pantry_by_base.get(base, {})
        if unit in unit_map and unit_map[unit] >= need_qty:
            results.append({
                "missing": raw_item,
                "use": [{"item": base, "qty": need_qty, "unit": unit}],
                "prep": "",
                "confidence": 0.9,
                "reason": "Same ingredient available under a variant name."
            })
            continue

        # 2) Heuristic generic swaps (no giant dictionary)
        #    fish fillet -> fish; dried chili -> chili
        #    Only if we actually have the base in pantry.
        if base in pantry_by_base and allow_prep:
            prep = _prep_note_for(raw_item, base)
            conf = _confidence_for(raw_item, base)
            # choose the same unit if present; otherwise pick any available unit (agent can rely on alt-units)
            pick_unit = unit if unit in pantry_by_base[base] else (next(iter(pantry_by_base[base].keys())) if pantry_by_base[base] else unit)
            results.append({
                "missing": raw_item,
                "use": [{"item": base, "qty": need_qty, "unit": pick_unit}],
                "prep": prep,
                "confidence": conf,
                "reason": "Close culinary equivalent; simple prep bridges the gap."
            })
            continue

        # 3) Nothing reasonable
        #    (We intentionally do NOT fabricate substitutes.)
        #    Skip adding an entry.

    return json.dumps({"subs": results}, ensure_ascii=False)
