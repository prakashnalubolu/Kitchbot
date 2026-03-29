"""
tools/cuisine_tools.py  –  CRUD + query helpers for recipes.json
"""
import json, os, re, difflib
from typing import List, Optional, Dict
from dotenv import load_dotenv
from langchain_core.tools import tool
from tools.textnorm import canonical_key, canonicalize_many


load_dotenv()

DATA_DIR  = os.path.join(os.path.dirname(__file__), os.pardir, "data")
DATA_PATH = os.path.abspath(os.path.join(DATA_DIR, "recipe.json"))
os.makedirs(DATA_DIR, exist_ok=True)

# ── low-level storage helpers ──────────────────────────────────────────────
def _load() -> List[Dict]:
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, encoding="utf-8") as f:
            return json.load(f)  # let JSON errors raise
    return []

def _normalize(name: str) -> str:
    """Return the head noun for loose matching."""
    return name.lower().split()[-1]       # last word

def _normalise_diet(label: str | None) -> str:
    """Map user/recipe diet labels to canonical codes: veg, eggtarian, non-veg."""
    if not label:
        return ""
    s = str(label).strip().lower()
    s = s.replace("_", "-").replace(" ", "-")
    aliases = {
        # vegetarian
        "veg": "veg",
        "vegetarian": "veg",
        "veggie": "veg",
        # eggtarian / ovo-vegetarian
        "eggtarian": "eggtarian",
        "eggetarian": "eggtarian",
        "ovo-vegetarian": "eggtarian",
        "ovo": "eggtarian",
        "egg": "eggtarian",
        # non-vegetarian
        "non-veg": "non-veg",
        "nonveg": "non-veg",
        "non-vegetarian": "non-veg",
        "nonvegetarian": "non-veg",
        "meat": "non-veg",
    }
    return aliases.get(s, s)

def diet_ok(recipe_diet, wanted):
    """Allow veg ⊂ eggtarian ⊂ non-veg (i.e., higher code is more permissive)."""
    r = _normalise_diet(recipe_diet)
    w = _normalise_diet(wanted)
    order = {"veg": 0, "eggtarian": 1, "non-veg": 2}
    if not w:
        # No user filter -> all ok
        return True
    if r not in order or w not in order:
        # Unknown labels: fall back to exact-match to be safe
        return r == w
    return order[r] <= order[w]

_plural_re = re.compile(r"([^aeiou]y|[sxz]|ch|sh)$", re.I)
def _plural(word: str) -> str:
    if _plural_re.search(word): return word + "es"
    return word + "s"

def _fmt_ing(item: str, qty: int | float, unit: str) -> str:
    if unit == "count":
        name = item if qty == 1 else _plural(item)
        return f"- {qty} {name}"
    return f"- {qty} {unit} {item}"

def _clean_name(s: str) -> str:
    s = str(s or "").strip()
    # strip outer matching quotes
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1]
    # strip any stray leading/trailing quotes and collapse spaces
    s = s.strip('\'"')
    s = re.sub(r"\s+", " ", s)
    return s

def _match(a: str, b: str) -> bool:
    return _clean_name(a).lower() == _clean_name(b).lower()

def _find(name: str) -> Optional[Dict]:
    """Exact match first; if not found, fuzzy fallback for common typos."""
    want = _clean_name(name)
    db = _load()
    for r in db:
        if _match(r["name"], want):
            return r
    # fuzzy fallback (handles e.g. "palak pannerr", "kungpao chicken")
    names = [r["name"] for r in db]
    hit = difflib.get_close_matches(want, names, n=1, cutoff=0.85)
    if hit:
        return next((r for r in db if _match(r["name"], hit[0])), None)
    return None

# ── Substitution hints (inline, only for missing ingredients) ──────────────

# Verbs so generic they add no useful context ("add onion" → skip "add")
_GENERIC_VERBS = {
    "heat", "add", "stir", "cook", "use", "mix", "put", "place", "pour",
    "serve", "garnish", "season", "combine", "remove", "set", "let", "keep",
    "bring", "reduce", "simmer", "boil", "fry", "wash", "cut", "chop",
    "dice", "slice", "prepare", "transfer", "cover", "drain", "rinse",
}

def _usage_context(raw_item: str, steps: list) -> str:
    """
    Return a gerund describing what the ingredient is used for
    (e.g. 'marinating', 'glazing') by finding the first recipe step that
    mentions it and reading its opening action verb.
    Returns '' if the verb is too generic or can't be determined.
    """
    keywords = [w for w in raw_item.lower().split() if len(w) > 3]
    if not keywords:
        return ""
    for step in steps:
        if any(kw in step.lower() for kw in keywords):
            word = step.strip().split()[0].rstrip(".,;:").lower()
            # Skip adverbs (end in -ly), prepositions, articles, and generic verbs
            if word.endswith("ly") or len(word) <= 2 or word in _GENERIC_VERBS:
                return ""
            # convert to gerund
            if word.endswith("ing"):
                return word
            if word.endswith("e") and not word.endswith("ee"):
                return word[:-1] + "ing"
            return word + "ing"
    return ""


def _get_sub_hints(recipe: dict) -> list:
    """
    Return a list of hint strings for ingredients the user doesn't have.
    Only shows a hint when an ingredient is actually missing AND a known
    substitute exists in the pantry. Silent otherwise.
    """
    try:
        from tools.manager_tools import (
            _load_pantry, _canonical_item_name, _aggregate_pantry_by_base,
            _SUB_TABLE, _is_universal,
        )
    except ImportError:
        return []

    pantry_raw   = _load_pantry()
    pantry_by_base = _aggregate_pantry_by_base(pantry_raw)

    hints = []
    seen_missing = set()   # deduplicate on canonical base name
    steps = recipe.get("steps", [])

    for ing in recipe.get("ingredients", []):
        raw_item = str(ing.get("item", "") or "").strip()
        if not raw_item:
            continue
        need_qty = float(ing.get("quantity", 0) or 0)
        if need_qty <= 0:
            continue
        # Never flag universal staples (salt, oil, water, sugar …)
        if _is_universal(raw_item):
            continue

        base = _canonical_item_name(raw_item)
        if not base or base in seen_missing:
            continue

        # Check if pantry covers this ingredient (by canonical base name)
        if base in pantry_by_base:
            continue  # have it — no hint needed

        # Also check via fuzzy coverage (e.g. "chicken" covers "boneless chicken breast",
        # but correctly rejects "onion" covering "spring onion")
        raw_lower = raw_item.lower()
        if any(_fuzzy_covers(pb, base) for pb in pantry_by_base):
            continue

        # Ingredient is missing — search for a pantry substitute
        seen_missing.add(base)
        for kw_miss, kw_base, prep_note, conf in _SUB_TABLE:
            if kw_miss not in raw_lower and kw_miss not in base:
                continue
            # Find a pantry item that contains the substitute keyword
            matching = [pb for pb in pantry_by_base if kw_base in pb]
            if not matching:
                continue
            actual = matching[0]

            # Where in the recipe is this ingredient used?
            ctx = _usage_context(raw_item, steps)
            ctx_str = f" (for {ctx})" if ctx else ""

            # Phrasing based on how close the substitute is
            if conf >= 0.85:
                hint = f"**{raw_item}**{ctx_str} → use **{actual}** instead"
            else:
                hint = f"**{raw_item}**{ctx_str} → **{actual}** works if needed (original preferred)"

            if prep_note:
                hint += f" *(tip: {prep_note})*"
            hints.append(hint)
            break   # first match wins per missing ingredient

    return hints


# ── LangChain tools ────────────────────────────────────────────────────────
@tool
def get_recipe(name: str) -> str:
    """Return one full recipe (ingredients & steps) or an error."""
    name = _clean_name(name)
    r = _find(name)
    if not r:
        return f"⚠️ Recipe '{name}' not found."
    header = f"🍽 **{r['name'].title()}** ({r['cuisine']}) – " \
             f"Prep {r['prep_time_min']} min · Cook {r['cook_time_min']} min"
    ings   = [_fmt_ing(i["item"], i["quantity"], i["unit"]) for i in r["ingredients"]]
    steps  = [f"{i+1}. {s}" for i, s in enumerate(r["steps"])]
    body   = "\n".join([header, "", "### Ingredients"] + ings +
                       ["", "### Steps"] + steps)
    hints  = _get_sub_hints(r)
    if hints:
        body += "\n\n### Substitution Hints\n" + "\n".join(f"- {h}" for h in hints)
    return body

@tool
def list_recipes(cuisine: Optional[str] = None,
                 max_time: Optional[int] = None,
                 diet: Optional[str] = None) -> str:
    """
    List recipe names. Optional filters:
      • cuisine = "italian", "indian", …
      • max_time = total time in minutes
      • diet = "veg" | "eggtarian" | "non-veg"
    """
    items = _load()
    if cuisine:
        items = [r for r in items if r["cuisine"].lower() == cuisine.lower()]
    if max_time is not None:
        items = [r for r in items
                 if r["prep_time_min"] + r["cook_time_min"] <= max_time]
    if diet:
        items = [r for r in items if diet_ok(r.get("diet"), diet)]
    if not items:
        return "📭 No recipes found with those filters."
    return "\n".join(f"- {r['name'].title()} ({r['cuisine']})" for r in items)

# ── Substitution-aware ingredient matching ────────────────────────────────
#
# Two-layer design (mirrors what Spoonacular/Yummly use at their core):
#
# LAYER 1 — PREPARATION modifiers: safe to strip.
#   These change the FORM of an ingredient, not its identity.
#   "ground chicken" → "chicken" ✓   "diced tomato" → "tomato" ✓
#
# LAYER 2 — FLAVOR/TYPE qualifiers: NEVER strip, treat compound as atomic.
#   These change the IDENTITY of an ingredient entirely.
#   "coconut milk" ≠ "milk"    "peanut butter" ≠ "butter"
#   "soy sauce"    ≠ "sauce"   "sesame oil" ≠ "oil" (completely different flavor)
#
# Without this split, "milk" would match "coconut milk" via word-subset check —
# a false positive that tells users they can cook Thai curry with dairy milk.

_PREP_MODIFIERS = {
    # cutting / processing
    "ground", "minced", "diced", "chopped", "sliced", "crushed", "shredded",
    "grated", "cubed", "julienned", "mashed", "pureed", "blended",
    # butchery
    "boneless", "skinless", "deboned", "trimmed",
    # preservation state
    "dried", "fresh", "frozen", "canned", "tinned", "pickled",
    # size
    "whole", "half", "large", "small", "medium",
    # cooking state
    "raw", "cooked", "smoked", "roasted", "grilled", "fried", "boiled", "steamed",
    # flour type (all-purpose flour → flour)
    "all-purpose", "all", "purpose",
    # fat qualifiers that don't change the base dairy identity
    "heavy", "light", "double", "single",
    # salt
    "unsalted", "salted",
    # heat level for chilis
    "hot", "mild",
    # colour qualifiers for bell peppers, lentils (red/green pepper → pepper)
    "red", "green", "yellow",
    # refinement (refined oil → oil, but coconut stays because coconut is a flavor qualifier)
    "refined", "extra", "virgin",
}

# Flavor/type qualifiers — the FIRST word in a compound ingredient that defines
# a fundamentally different product.  "coconut milk" is NOT milk; it's its own thing.
# Expanding this list is the primary maintenance task as recipes grow.
_FLAVOR_QUALIFIERS = {
    # plant-based "milks" — none are interchangeable with dairy milk
    "coconut", "almond", "oat", "soy", "rice", "cashew", "hemp",
    # nut/seed butters — not interchangeable with dairy butter
    "peanut", "tahini",
    # flavored oils & sauces — identity defined by the qualifier
    "sesame", "fish", "oyster", "hoisin", "worcestershire", "teriyaki",
    # vinegars
    "balsamic", "apple",
    # sugars where the type matters to the recipe outcome
    "brown", "powdered", "icing", "palm",
    # distinct allium varieties — spring onion ≠ onion
    "spring",
    # stocks / broths — handled via exact match; removing from here
    # because "chicken" as a qualifier would wrongly block "chicken breast"
}

def _is_compound_atomic(phrase: str) -> bool:
    """
    Return True if the first word of a multi-word ingredient is a flavor/type
    qualifier — meaning the whole phrase must be treated as an atomic unit.
    E.g.: "coconut milk" → True  (coconut is a flavor qualifier)
          "ground chicken" → False (ground is a prep modifier, safe to strip)
    """
    words = phrase.strip().split()
    if len(words) < 2:
        return False
    return words[0] in _FLAVOR_QUALIFIERS

def _base_ingredient(canon: str) -> str:
    """
    Strip PREPARATION modifiers to get the core ingredient.
    Only strips if the phrase is NOT a compound atomic (flavor-qualified) ingredient.
    """
    if _is_compound_atomic(canon):
        return canon  # treat "coconut milk" as atomic — don't reduce to "milk"
    words = [w for w in canon.split() if w not in _PREP_MODIFIERS]
    return " ".join(words) if words else canon

def _fuzzy_covers(pantry_canon: str, recipe_canon: str) -> bool:
    """
    Return True if a pantry item can reasonably satisfy a recipe ingredient.

    Safe matches:
      "chicken"   covers "ground chicken", "chicken breast", "boneless chicken"
      "tomato"    covers "diced tomato", "crushed tomato"
      "flour"     covers "all-purpose flour"
      "cream"     covers "heavy cream", "double cream"
      "onion"     covers "red onion"

    Correctly blocked (compound atomic ingredients):
      "milk"      does NOT cover "coconut milk"
      "butter"    does NOT cover "peanut butter"
      "sauce"     does NOT cover "soy sauce"
      "oil"       does NOT cover "sesame oil"
    """
    if pantry_canon == recipe_canon:
        return True

    # Block: if the recipe ingredient is a compound atomic, pantry must match exactly
    # or the pantry item itself must be the same compound.
    # "milk" should not cover "coconut milk".
    if _is_compound_atomic(recipe_canon):
        # Only allow if pantry item IS that compound or its base (same compound family)
        # e.g. "coconut milk" pantry covers "coconut milk" recipe (exact, already caught above)
        # "milk" pantry should NOT cover "coconut milk" recipe
        return False

    # Safe: strip preparation modifiers from both sides and compare
    p_base = _base_ingredient(pantry_canon)
    r_base = _base_ingredient(recipe_canon)
    if p_base and r_base and p_base == r_base:
        return True

    # Safe: pantry item words ⊆ recipe ingredient words
    # "chicken" ⊂ {"ground", "chicken"} → True
    # Guarded: we already blocked compound atomics above so "milk" ⊂ {"coconut","milk"} never reaches here
    p_words = set(pantry_canon.split())
    r_words = set(recipe_canon.split())
    if p_words and p_words.issubset(r_words):
        return True

    return False

def _covered_count(have_set: set, need_set: set) -> int:
    """Count how many recipe ingredients are covered by the pantry (fuzzy-aware)."""
    return sum(
        1 for need in need_set
        if need in have_set or any(_fuzzy_covers(have, need) for have in have_set)
    )

def _canon(s: str) -> str:
    return canonical_key(s)

@tool
def find_recipes_by_items(
    items: List[str],
    cuisine: Optional[str] = None,
    max_time: Optional[int] = None,
    diet: Optional[str] = None,
    k: int = 5,
) -> str:
    """
    Suggest up to *k* recipes that best match the given *items* list.

    Ranking policy (strict):
    • First, show all recipes whose ingredient set is 100% covered by the pantry items (after canonicalization).
    • If no recipe is 100% covered, show partial matches ranked by: more items covered, then shorter total time, then name.
    """
    k = int(k or 5)
    items = [s.strip() for s in (items or []) if s and s.strip()]

    # ---- load & filter candidates
    recipes = _load()
    if diet:
        recipes = [r for r in recipes if diet_ok(r.get("diet"), diet)]
    if cuisine:
        recipes = [r for r in recipes if r.get("cuisine", "").lower() == cuisine.lower()]
    if max_time is not None:
        recipes = [
            r for r in recipes
            if r.get("prep_time_min", 0) + r.get("cook_time_min", 0) <= max_time
        ]

    # ---- fallback: no pantry items provided -> shortest total time
    if not items:
        recipes_sorted = sorted(
            recipes,
            key=lambda r: (r.get("prep_time_min", 0) + r.get("cook_time_min", 0), r.get("name", "")),
        )[:k]
        return (
            "\n".join(f"- {r['name'].title()} ({r['cuisine']})" for r in recipes_sorted)
            or "📭 No recipes match those filters."
        )

    # ---------- Canonicalize and rank ----------
    have_set = set(canonicalize_many(items))  # spaCy primary → inflect fallback
    ranked = []  # (is_full_cover: bool, covered_count: int, total_time: int, recipe: dict, coverage_ratio: float)

    for r in recipes:
        need_set = {
            canonical_key(i.get("item", ""))
            for i in (r.get("ingredients") or [])
            if (i.get("item") or "").strip()
        }
        need_set.discard("")
        total_need = len(need_set)
        if total_need == 0:
            continue

        covered_cnt = _covered_count(have_set, need_set)
        is_full = (covered_cnt == total_need)
        total_time = int(r.get("prep_time_min", 0)) + int(r.get("cook_time_min", 0))
        ratio = covered_cnt / total_need
        ranked.append((is_full, covered_cnt, total_time, r, ratio))

    if not ranked:
        return "📭 No recipes match those items."

    # Sort: 100% coverage first, then higher coverage ratio, then quicker, then name
    ranked.sort(key=lambda t: (not t[0], -t[4], t[2], (t[3].get("name") or "").lower()))

    # Optional bias by requested diet (only meaningful for "non-veg" preference)
    def _diet_rank(recipe_diet: str, user_want: Optional[str]) -> int:
        want = _normalise_diet(user_want)
        r    = _normalise_diet(recipe_diet)
        if want == "non-veg":
            order = {"non-veg": 0, "eggtarian": 1, "veg": 2}
            return order.get(r, 3)
        return 0

    full = [t for t in ranked if t[0]]
    partial = [t for t in ranked if not t[0]]

    if diet:
        full.sort(key=lambda t: (_diet_rank(t[3].get("diet", ""), diet), t[2], (t[3].get("name") or "").lower()))
        partial.sort(key=lambda t: (_diet_rank(t[3].get("diet", ""), diet), -t[4], t[2], (t[3].get("name") or "").lower()))

    top = (full + partial)[:k]

    return "\n".join(
        f"- {t[3]['name'].title()} ({t[3]['cuisine']}) — {round(t[4] * 100):>3}% ingredients covered"
        for t in top
    )
