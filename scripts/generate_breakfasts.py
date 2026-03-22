"""
scripts/generate_breakfasts.py
──────────────────────────────
Generate authentic breakfast recipes for all 13 cuisines and merge them
directly into data/recipe.json with meal_type: "breakfast".

Usage:
    python scripts/generate_breakfasts.py           # generate all cuisines
    python scripts/generate_breakfasts.py --cuisine north_indian
    python scripts/generate_breakfasts.py --dry-run # show what would be generated

Cost estimate: ~65 breakfast recipes across 13 cuisine groups
    ~14 GPT-4o-mini calls  ≈ $0.05–0.10 total
"""

from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path
from typing import List, Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

ROOT        = Path(__file__).parent.parent
DATA_DIR    = ROOT / "data"
RECIPE_PATH = DATA_DIR / "recipe.json"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─────────────────────────────────────────────────────────────────────────────
# BREAKFAST CATALOGUE  — 5 dishes per cuisine group
# ─────────────────────────────────────────────────────────────────────────────
BREAKFAST_CATALOGUE: Dict[str, List[Dict[str, str]]] = {

    "north_indian": [
        {"name": "aloo paratha with curd",  "diet": "veg"},
        {"name": "poha",                    "diet": "veg"},
        {"name": "upma",                    "diet": "veg"},
        {"name": "besan chilla",            "diet": "veg"},
        {"name": "anda bhurji toast",       "diet": "eggtarian"},
    ],

    "south_indian": [
        {"name": "idli sambar",             "diet": "veg"},
        {"name": "masala dosa",             "diet": "veg"},
        {"name": "rava upma",               "diet": "veg"},
        {"name": "pesarattu",               "diet": "veg"},
        {"name": "egg dosa",                "diet": "eggtarian"},
    ],

    "east_indian": [
        {"name": "luchi torkari",           "diet": "veg"},
        {"name": "muri ghonto",             "diet": "non-veg"},
        {"name": "chirar pulao",            "diet": "veg"},
        {"name": "egg roll bengali style",  "diet": "eggtarian"},
        {"name": "mishti doi with roti",    "diet": "veg"},
    ],

    "indian_street_food": [
        {"name": "vada pav",                "diet": "veg"},
        {"name": "medu vada",               "diet": "veg"},
        {"name": "bread pakora",            "diet": "veg"},
        {"name": "misal pav",               "diet": "veg"},
        {"name": "egg frankie",             "diet": "eggtarian"},
    ],

    "chinese": [
        {"name": "congee with century egg", "diet": "non-veg"},
        {"name": "jianbing",                "diet": "eggtarian"},
        {"name": "scallion pancakes",       "diet": "veg"},
        {"name": "dim sum har gow",         "diet": "non-veg"},
        {"name": "soy milk with youtiao",   "diet": "veg"},
    ],

    "japanese": [
        {"name": "tamagoyaki",              "diet": "eggtarian"},
        {"name": "tamago gohan",            "diet": "eggtarian"},
        {"name": "japanese miso soup",      "diet": "veg"},
        {"name": "onigiri",                 "diet": "non-veg"},
        {"name": "okayu rice porridge",     "diet": "veg"},
    ],

    "thai": [
        {"name": "jok thai rice porridge",  "diet": "non-veg"},
        {"name": "khao tom",                "diet": "non-veg"},
        {"name": "thai roti with egg",      "diet": "eggtarian"},
        {"name": "pad kra pao with egg",    "diet": "eggtarian"},
        {"name": "mango with sticky rice",  "diet": "veg"},
    ],

    "italian": [
        {"name": "frittata",                "diet": "eggtarian"},
        {"name": "bruschetta pomodoro",     "diet": "veg"},
        {"name": "ricotta toast with honey","diet": "veg"},
        {"name": "italian crepes",          "diet": "eggtarian"},
        {"name": "caprese toast",           "diet": "veg"},
    ],

    "american": [
        {"name": "buttermilk pancakes",     "diet": "eggtarian"},
        {"name": "scrambled eggs on toast", "diet": "eggtarian"},
        {"name": "french toast",            "diet": "eggtarian"},
        {"name": "oatmeal with berries",    "diet": "veg"},
        {"name": "breakfast burrito",       "diet": "eggtarian"},
    ],

    "mexican": [
        {"name": "huevos rancheros",        "diet": "eggtarian"},
        {"name": "chilaquiles verdes",      "diet": "eggtarian"},
        {"name": "tamales de rajas",        "diet": "veg"},
        {"name": "molletes",                "diet": "veg"},
        {"name": "atole",                   "diet": "veg"},
    ],

    "korean": [
        {"name": "juk korean rice porridge","diet": "veg"},
        {"name": "gyeran mari",             "diet": "eggtarian"},
        {"name": "banchan egg bowl",        "diet": "eggtarian"},
        {"name": "tteok guk",               "diet": "non-veg"},
        {"name": "doenjang jjigae breakfast","diet": "non-veg"},
    ],

    "mediterranean": [
        {"name": "shakshuka",               "diet": "eggtarian"},
        {"name": "menemen",                 "diet": "eggtarian"},
        {"name": "labneh with olive oil",   "diet": "veg"},
        {"name": "ful medames",             "diet": "veg"},
        {"name": "greek yogurt with honey", "diet": "veg"},
    ],

    "vietnamese": [
        {"name": "banh mi op la",           "diet": "eggtarian"},
        {"name": "xoi xeo sticky rice",     "diet": "veg"},
        {"name": "pho bo breakfast",        "diet": "non-veg"},
        {"name": "banh cuon",               "diet": "non-veg"},
        {"name": "com tam suon",            "diet": "non-veg"},
    ],
}

# Map catalogue key → cuisine tag stored in recipe JSON
CUISINE_TAG: Dict[str, str] = {
    "north_indian":       "indian",
    "south_indian":       "indian",
    "east_indian":        "indian",
    "indian_street_food": "indian",
    "chinese":            "chinese",
    "japanese":           "japanese",
    "thai":               "thai",
    "italian":            "italian",
    "american":           "american",
    "mexican":            "mexican",
    "korean":             "korean",
    "mediterranean":      "mediterranean",
    "vietnamese":         "vietnamese",
}

# Authenticity hints (breakfast-specific additions on top of general cuisine notes)
_BREAKFAST_HINTS: Dict[str, str] = {
    "north_indian":
        "Indian breakfasts are filling and savoury. Use ghee, mustard oil or vegetable oil. "
        "Spices: cumin, turmeric, green chili, coriander. No pancakes, no toast with jam — "
        "think poha, upma, paratha, chilla.",
    "south_indian":
        "South Indian breakfasts are rice/lentil based. Idli batter is fermented overnight. "
        "Sambar is thin and tangy. Chutneys (coconut, tomato) are essential. "
        "Use coconut oil, curry leaves, mustard seeds, urad dal for tempering.",
    "east_indian":
        "Bengali breakfasts are light. Luchi is deep-fried white flour puri. "
        "Use mustard oil. Chirar pulao uses beaten rice (chira/poha). "
        "Mishti doi is sweetened fermented yogurt — serve cold.",
    "indian_street_food":
        "Street breakfast is fast and bold. Vada pav uses a spiced potato patty in a soft pav bun. "
        "Use chaat masala, tamarind and green chutneys. Everything should be spicy and tangy.",
    "chinese":
        "Chinese breakfast (zaochan) is often light and soupy. Congee is rice simmered very soft. "
        "Jianbing is a savoury crepe with egg, sauces and crispy cracker. "
        "Youtiao are long fried dough sticks. Use soy milk (doujiang), not dairy milk.",
    "japanese":
        "Japanese breakfast is balanced: rice, miso soup, pickles, protein. "
        "Tamagoyaki is a sweet-savoury rolled omelette. Tamago gohan is raw egg on hot rice with soy. "
        "Okayu is soft rice porridge. Keep it simple and clean-tasting.",
    "thai":
        "Thai breakfasts are often rice-based or porridge. Jok is rice congee with pork and ginger. "
        "Khao tom is lighter rice soup. Use fish sauce, white pepper, coriander as garnish. "
        "Roti is flaky fried flatbread — serve with condensed milk or egg.",
    "italian":
        "Italian breakfast (colazione) is light. Frittata is a thick baked omelette. "
        "Bruschetta is grilled bread with tomato. Use extra virgin olive oil, fresh basil, "
        "good ricotta. No heavy sauces — keep it fresh and simple.",
    "american":
        "American breakfast is hearty. Buttermilk makes pancakes fluffy — do not skip it. "
        "French toast uses thick-cut bread soaked in egg and milk. "
        "Breakfast burrito has scrambled eggs, cheese, salsa in a flour tortilla. "
        "Use butter generously.",
    "mexican":
        "Mexican breakfast is bold. Huevos rancheros uses fried eggs on corn tortillas with salsa. "
        "Chilaquiles are tortilla chips simmered in salsa verde or roja, topped with egg and crema. "
        "Molletes are bolillo rolls topped with beans and cheese, broiled. "
        "Atole is a warm masa-based drink.",
    "korean":
        "Korean breakfast is a small version of any meal — rice, soup, banchan. "
        "Juk is smooth rice porridge (plain, abalone, or vegetable). "
        "Gyeran mari is a tightly rolled omelette with vegetables. "
        "Tteok guk is rice cake soup traditionally eaten on New Year but common in winter mornings.",
    "mediterranean":
        "Mediterranean breakfast is mezze-style. Shakshuka: eggs poached in spiced tomato sauce. "
        "Menemen: Turkish scrambled eggs with tomato and green pepper. "
        "Labneh is strained yogurt drizzled with olive oil and za'atar. "
        "Ful medames: slow-cooked fava beans with lemon, cumin, olive oil.",
    "vietnamese":
        "Vietnamese breakfast is often noodle or rice based. Pho is eaten for breakfast daily. "
        "Banh mi op la is a French-influenced fried egg baguette sandwich. "
        "Xoi xeo is sticky rice with mung bean and fried shallots. "
        "Com tam is broken rice with grilled pork. Use fish sauce, fresh herbs always.",
}

_SYSTEM = """You are a world-class culinary expert specialising in authentic home-style breakfast recipes
from every cuisine on earth.

Output rules (strict):
- ALWAYS respond with a JSON object with a single key "recipes" whose value is an array.
  Example: {"recipes": [{...recipe1...}, {...recipe2...}]}
- Quantities MUST use ONLY these three units: "g", "ml", or "count".
  Convert ALL volumes to ml: 1 tsp = 5 ml, 1 tbsp = 15 ml, 1 cup = 240 ml.
  Convert ALL weights to grams. Use "count" for things naturally counted.
- Every recipe MUST include the field: "meal_type": "breakfast"
- Use ingredient names a home cook in that specific region would actually use."""


def _build_prompt(dishes: List[Dict[str, str]], cuisine_tag: str, cat_key: str) -> str:
    dish_list = "\n".join(
        f'  - "{d["name"]}" (diet: {d["diet"]})' for d in dishes
    )
    hint = _BREAKFAST_HINTS.get(cat_key, "")
    hint_block = f"\nAuthenticity & breakfast notes:\n{hint}\n" if hint else ""

    return f"""Generate authentic home-style BREAKFAST recipes for EXACTLY these dishes:
{dish_list}
{hint_block}
Return a JSON object with a single key "recipes" containing an array of recipe objects.
Each recipe object must have EXACTLY these fields:
{{
  "name":           "<lowercase dish name>",
  "cuisine":        "{cuisine_tag}",
  "diet":           "<veg | eggtarian | non-veg>",
  "meal_type":      "breakfast",
  "prep_time_min":  <integer>,
  "cook_time_min":  <integer>,
  "ingredients": [
    {{"item": "<singular lowercase name>", "quantity": <positive number>, "unit": "<g|ml|count>"}}
  ],
  "steps": ["<step 1>", "<step 2>", ...]
}}

Rules:
- Generate exactly {len(dishes)} recipes, one per dish listed.
- Ingredients: 6–14 items per recipe. Only real ingredients — no "salt to taste", no "water as needed".
  Include actual quantities for salt (e.g. 5 g), water (e.g. 200 ml), oil (e.g. 30 ml).
- Steps: 4–8 steps. Each step is a single clear action sentence.
- prep_time_min + cook_time_min should reflect a realistic breakfast (5–30 min total is typical).
- meal_type must always be "breakfast" — do not omit it."""


def _call_gpt(dishes: List[Dict[str, str]], cuisine_tag: str, cat_key: str,
              model: str = "gpt-4o-mini") -> List[Dict[str, Any]]:
    prompt = _build_prompt(dishes, cuisine_tag, cat_key)
    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.4,
    )
    raw = resp.choices[0].message.content or ""
    data = json.loads(raw)

    # unwrap {"recipes": [...]}
    if isinstance(data, dict) and "recipes" in data:
        result = data["recipes"]
    elif isinstance(data, list):
        result = data
    else:
        result = [data]

    # ensure meal_type is set on every recipe
    for r in result:
        r.setdefault("meal_type", "breakfast")
    return result


def _validate(recipe: Dict[str, Any], cuisine_tag: str) -> List[str]:
    errors = []
    for field in ("name", "cuisine", "diet", "prep_time_min", "cook_time_min",
                  "ingredients", "steps", "meal_type"):
        if field not in recipe:
            errors.append(f"missing field: {field}")
    if recipe.get("meal_type") != "breakfast":
        errors.append("meal_type must be 'breakfast'")
    if recipe.get("cuisine") != cuisine_tag:
        errors.append(f"cuisine should be '{cuisine_tag}', got '{recipe.get('cuisine')}'")
    ings = recipe.get("ingredients", [])
    if not (6 <= len(ings) <= 20):
        errors.append(f"unusual ingredient count: {len(ings)}")
    for ing in ings:
        if ing.get("unit") not in ("g", "ml", "count"):
            errors.append(f"bad unit '{ing.get('unit')}' for '{ing.get('item')}'")
    return errors


def _generate_for(cat_key: str, dry_run: bool = False) -> List[Dict[str, Any]]:
    dishes      = BREAKFAST_CATALOGUE[cat_key]
    cuisine_tag = CUISINE_TAG[cat_key]

    if dry_run:
        print(f"  [dry-run] Would generate {len(dishes)} breakfast recipes for {cat_key}")
        return []

    print(f"  Calling GPT for {cat_key} ({len(dishes)} dishes)…", end=" ", flush=True)
    try:
        recipes = _call_gpt(dishes, cuisine_tag, cat_key)
    except Exception as e:
        print(f"ERROR: {e}")
        return []

    # Validate
    good = []
    for r in recipes:
        errs = _validate(r, cuisine_tag)
        if errs:
            print(f"\n    ⚠ '{r.get('name', '?')}' has issues: {errs}")
        else:
            good.append(r)

    print(f"✓ {len(good)}/{len(dishes)} valid")
    return good


def _load_existing() -> List[Dict[str, Any]]:
    if RECIPE_PATH.exists():
        with open(RECIPE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def _save(data: List[Dict[str, Any]]) -> None:
    with open(RECIPE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Generate breakfast recipes")
    parser.add_argument("--cuisine", help="Only generate for this cuisine key")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be generated without calling GPT")
    args = parser.parse_args()

    keys = list(BREAKFAST_CATALOGUE.keys())
    if args.cuisine:
        if args.cuisine not in BREAKFAST_CATALOGUE:
            print(f"Unknown cuisine '{args.cuisine}'. Valid: {', '.join(keys)}")
            sys.exit(1)
        keys = [args.cuisine]

    print(f"Generating breakfast recipes for: {', '.join(keys)}")
    print(f"Total dishes: {sum(len(BREAKFAST_CATALOGUE[k]) for k in keys)}\n")

    all_new: List[Dict[str, Any]] = []
    for key in keys:
        print(f"[{key}]")
        new = _generate_for(key, dry_run=args.dry_run)
        all_new.extend(new)
        if not args.dry_run and len(keys) > 1:
            time.sleep(0.5)  # be gentle on the API

    if args.dry_run:
        print(f"\n[dry-run] Would add {sum(len(BREAKFAST_CATALOGUE[k]) for k in keys)} breakfast recipes.")
        return

    if not all_new:
        print("No recipes generated.")
        return

    # Merge into recipe.json (skip exact name+cuisine duplicates)
    existing   = _load_existing()
    exist_keys = {(r["name"].lower(), r.get("cuisine","")) for r in existing}

    added = 0
    for r in all_new:
        key_pair = (r["name"].lower(), r.get("cuisine",""))
        if key_pair not in exist_keys:
            existing.append(r)
            exist_keys.add(key_pair)
            added += 1
        else:
            print(f"  skip duplicate: {r['name']}")

    _save(existing)
    breakfast_total = sum(1 for r in existing if r.get("meal_type") == "breakfast")
    print(f"\n✅ Added {added} breakfast recipes. Total in DB: {len(existing)} "
          f"({breakfast_total} breakfasts)")


if __name__ == "__main__":
    main()
