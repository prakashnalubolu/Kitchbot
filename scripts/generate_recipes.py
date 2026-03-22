"""
scripts/generate_recipes.py
────────────────────────────
Batch-generate + auto-review authentic global recipes using GPT-4o-mini.
Uses the LLM-as-judge pattern: one call generates, a second call reviews & fixes.
No human review needed — bad recipes are corrected or dropped automatically.

Usage:
    python scripts/generate_recipes.py                     # generate all cuisines
    python scripts/generate_recipes.py --cuisine south_indian
    python scripts/generate_recipes.py --merge             # merge staged → recipe.json
    python scripts/generate_recipes.py --no-review         # skip LLM review step

Pipeline per batch:
    Generate (GPT-4o-mini) → Programmatic checks → LLM Review & Fix → Stage

Cost estimate: ~380 recipes
    Generation:  ~127 calls  × gpt-4o       ≈ $1.00–$1.50
    Review:      ~64  calls  × gpt-4o-mini  ≈ $0.05
    Total:                                   ≈ $1.00–$1.50
"""

from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path
from typing import List, Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ─── Paths ───────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent
DATA_DIR   = ROOT / "data"
RECIPE_PATH  = DATA_DIR / "recipe.json"
STAGED_PATH  = DATA_DIR / "recipes_staged.json"

# ─── OpenAI client ───────────────────────────────────────────────────────────
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─────────────────────────────────────────────────────────────────────────────
# DISH CATALOGUE  —  edit / extend this list freely
# ─────────────────────────────────────────────────────────────────────────────
DISH_CATALOGUE: Dict[str, List[Dict[str, str]]] = {

    "north_indian": [
        {"name": "dal tadka",              "diet": "veg"},
        {"name": "paneer butter masala",   "diet": "veg"},
        {"name": "chana masala",           "diet": "veg"},
        {"name": "aloo gobi",              "diet": "veg"},
        {"name": "palak paneer",           "diet": "veg"},
        {"name": "rajma",                  "diet": "veg"},
        {"name": "kadai paneer",           "diet": "veg"},
        {"name": "jeera rice",             "diet": "veg"},
        {"name": "matar paneer",           "diet": "veg"},
        {"name": "shahi paneer",           "diet": "veg"},
        {"name": "aloo paratha",           "diet": "veg"},
        {"name": "puri bhaji",             "diet": "veg"},
        {"name": "baingan bharta",         "diet": "veg"},
        {"name": "dal makhani",            "diet": "veg"},
        {"name": "mix veg curry",          "diet": "veg"},
        {"name": "butter chicken",         "diet": "non-veg"},
        {"name": "chicken tikka masala",   "diet": "non-veg"},
        {"name": "mutton rogan josh",      "diet": "non-veg"},
        {"name": "chicken biryani",        "diet": "non-veg"},
        {"name": "seekh kebab",            "diet": "non-veg"},
        {"name": "chicken korma",          "diet": "non-veg"},
        {"name": "keema matar",            "diet": "non-veg"},
        {"name": "tandoori chicken",       "diet": "non-veg"},
        {"name": "achari chicken",         "diet": "non-veg"},
        {"name": "egg curry",              "diet": "eggtarian"},
        {"name": "anda bhurji",            "diet": "eggtarian"},
        {"name": "naan",                   "diet": "veg"},
        {"name": "laccha paratha",         "diet": "veg"},
        {"name": "samosa",                 "diet": "veg"},
        {"name": "chole bhature",          "diet": "veg"},
    ],

    "south_indian": [
        {"name": "masala dosa",            "diet": "veg"},
        {"name": "idli sambar",            "diet": "veg"},
        {"name": "upma",                   "diet": "veg"},
        {"name": "rasam",                  "diet": "veg"},
        {"name": "avial",                  "diet": "veg"},
        {"name": "sambar",                 "diet": "veg"},
        {"name": "coconut chutney",        "diet": "veg"},
        {"name": "pongal",                 "diet": "veg"},
        {"name": "curd rice",              "diet": "veg"},
        {"name": "bisi bele bath",         "diet": "veg"},
        {"name": "medu vada",              "diet": "veg"},
        {"name": "appam with stew",        "diet": "veg"},
        {"name": "pesarattu",              "diet": "veg"},
        {"name": "kootu",                  "diet": "veg"},
        {"name": "thayir sadam",           "diet": "veg"},
        {"name": "kerala fish curry",      "diet": "non-veg"},
        {"name": "chettinad chicken curry","diet": "non-veg"},
        {"name": "prawn masala",           "diet": "non-veg"},
        {"name": "fish fry",               "diet": "non-veg"},
        {"name": "egg thokku",             "diet": "eggtarian"},
        {"name": "tomato rice",            "diet": "veg"},
        {"name": "lemon rice",             "diet": "veg"},
        {"name": "tamarind rice",          "diet": "veg"},
    ],

    "east_indian": [
        {"name": "machher jhol",           "diet": "non-veg"},
        {"name": "shorshe ilish",          "diet": "non-veg"},
        {"name": "kosha mangsho",          "diet": "non-veg"},
        {"name": "chingri malai curry",    "diet": "non-veg"},
        {"name": "aloo posto",             "diet": "veg"},
        {"name": "shukto",                 "diet": "veg"},
        {"name": "mishti doi",             "diet": "veg"},
        {"name": "cholar dal",             "diet": "veg"},
        {"name": "doi maach",              "diet": "non-veg"},
        {"name": "luchi torkari",          "diet": "veg"},
        {"name": "begun bhaja",            "diet": "veg"},
        {"name": "panch phoron dal",       "diet": "veg"},
    ],

    "indian_street_food": [
        {"name": "pav bhaji",              "diet": "veg"},
        {"name": "vada pav",               "diet": "veg"},
        {"name": "bhel puri",              "diet": "veg"},
        {"name": "pani puri",              "diet": "veg"},
        {"name": "dahi puri",              "diet": "veg"},
        {"name": "aloo tikki chaat",       "diet": "veg"},
        {"name": "kathi roll",             "diet": "non-veg"},
        {"name": "papdi chaat",            "diet": "veg"},
        {"name": "masala chai",            "diet": "veg"},
        {"name": "mango lassi",            "diet": "veg"},
    ],

    "chinese": [
        {"name": "kung pao chicken",       "diet": "non-veg"},
        {"name": "mapo tofu",              "diet": "veg"},
        {"name": "fried rice",             "diet": "eggtarian"},
        {"name": "beef and broccoli",      "diet": "non-veg"},
        {"name": "spring rolls",           "diet": "veg"},
        {"name": "dim sum dumplings",      "diet": "non-veg"},
        {"name": "sweet and sour pork",    "diet": "non-veg"},
        {"name": "hot and sour soup",      "diet": "non-veg"},
        {"name": "chow mein",              "diet": "non-veg"},
        {"name": "peking duck",            "diet": "non-veg"},
        {"name": "dan dan noodles",        "diet": "non-veg"},
        {"name": "char siu pork",          "diet": "non-veg"},
        {"name": "wonton soup",            "diet": "non-veg"},
        {"name": "stir fried vegetables",  "diet": "veg"},
        {"name": "steamed fish with ginger","diet": "non-veg"},
        {"name": "red braised pork belly", "diet": "non-veg"},
        {"name": "egg drop soup",          "diet": "eggtarian"},
        {"name": "ma po tofu",             "diet": "veg"},
        {"name": "scallion pancakes",      "diet": "veg"},
        {"name": "congee",                 "diet": "non-veg"},
    ],

    "japanese": [
        {"name": "chicken teriyaki",       "diet": "non-veg"},
        {"name": "miso soup",              "diet": "veg"},
        {"name": "tonkatsu",               "diet": "non-veg"},
        {"name": "gyudon beef bowl",       "diet": "non-veg"},
        {"name": "oyakodon",               "diet": "non-veg"},
        {"name": "yakitori",               "diet": "non-veg"},
        {"name": "ramen",                  "diet": "non-veg"},
        {"name": "onigiri",                "diet": "non-veg"},
        {"name": "takoyaki",               "diet": "non-veg"},
        {"name": "agedashi tofu",          "diet": "veg"},
        {"name": "katsu curry",            "diet": "non-veg"},
        {"name": "chawanmushi",            "diet": "eggtarian"},
        {"name": "tamagoyaki",             "diet": "eggtarian"},
        {"name": "okonomiyaki",            "diet": "eggtarian"},
        {"name": "nikujaga",               "diet": "non-veg"},
        {"name": "dashi broth",            "diet": "non-veg"},
        {"name": "edamame",                "diet": "veg"},
        {"name": "karaage chicken",        "diet": "non-veg"},
    ],

    "thai": [
        {"name": "pad thai",               "diet": "non-veg"},
        {"name": "green curry",            "diet": "non-veg"},
        {"name": "tom yum soup",           "diet": "non-veg"},
        {"name": "massaman curry",         "diet": "non-veg"},
        {"name": "pad see ew",             "diet": "non-veg"},
        {"name": "som tum",                "diet": "veg"},
        {"name": "khao pad",               "diet": "eggtarian"},
        {"name": "panang curry",           "diet": "non-veg"},
        {"name": "tom kha gai",            "diet": "non-veg"},
        {"name": "larb moo",               "diet": "non-veg"},
        {"name": "mango sticky rice",      "diet": "veg"},
        {"name": "thai basil chicken",     "diet": "non-veg"},
        {"name": "satay chicken",          "diet": "non-veg"},
        {"name": "red curry",              "diet": "non-veg"},
        {"name": "thai fried rice",        "diet": "eggtarian"},
    ],

    "italian": [
        {"name": "spaghetti carbonara",    "diet": "non-veg"},
        {"name": "pasta pomodoro",         "diet": "veg"},
        {"name": "risotto milanese",       "diet": "veg"},
        {"name": "osso buco",              "diet": "non-veg"},
        {"name": "chicken parmigiana",     "diet": "non-veg"},
        {"name": "bruschetta",             "diet": "veg"},
        {"name": "minestrone soup",        "diet": "veg"},
        {"name": "lasagna",                "diet": "non-veg"},
        {"name": "cacio e pepe",           "diet": "veg"},
        {"name": "arancini",               "diet": "veg"},
        {"name": "tiramisu",               "diet": "eggtarian"},
        {"name": "pesto pasta",            "diet": "veg"},
        {"name": "saltimbocca",            "diet": "non-veg"},
        {"name": "ribollita",              "diet": "veg"},
        {"name": "pasta e fagioli",        "diet": "non-veg"},
    ],

    "american": [
        {"name": "classic beef burger",    "diet": "non-veg"},
        {"name": "bbq pulled pork",        "diet": "non-veg"},
        {"name": "mac and cheese",         "diet": "veg"},
        {"name": "clam chowder",           "diet": "non-veg"},
        {"name": "buffalo chicken wings",  "diet": "non-veg"},
        {"name": "cornbread",              "diet": "veg"},
        {"name": "coleslaw",               "diet": "veg"},
        {"name": "pancakes",               "diet": "eggtarian"},
        {"name": "grilled cheese sandwich","diet": "veg"},
        {"name": "chicken pot pie",        "diet": "non-veg"},
        {"name": "beef chili",             "diet": "non-veg"},
        {"name": "banana bread",           "diet": "eggtarian"},
        {"name": "caesar salad",           "diet": "veg"},
        {"name": "baked potato soup",      "diet": "veg"},
        {"name": "sloppy joe",             "diet": "non-veg"},
    ],

    "mexican": [
        {"name": "chicken tacos",          "diet": "non-veg"},
        {"name": "beef enchiladas",        "diet": "non-veg"},
        {"name": "guacamole",              "diet": "veg"},
        {"name": "black bean soup",        "diet": "veg"},
        {"name": "chicken quesadilla",     "diet": "non-veg"},
        {"name": "pozole",                 "diet": "non-veg"},
        {"name": "chiles rellenos",        "diet": "eggtarian"},
        {"name": "elote",                  "diet": "veg"},
        {"name": "tamales",                "diet": "non-veg"},
        {"name": "carne asada",            "diet": "non-veg"},
        {"name": "refried beans",          "diet": "veg"},
        {"name": "tortilla soup",          "diet": "non-veg"},
        {"name": "salsa verde",            "diet": "veg"},
        {"name": "huevos rancheros",       "diet": "eggtarian"},
        {"name": "carnitas",               "diet": "non-veg"},
    ],

    "korean": [
        {"name": "bibimbap",               "diet": "eggtarian"},
        {"name": "kimchi jjigae",          "diet": "non-veg"},
        {"name": "bulgogi",                "diet": "non-veg"},
        {"name": "japchae",                "diet": "non-veg"},
        {"name": "tteokbokki",             "diet": "veg"},
        {"name": "doenjang jjigae",        "diet": "non-veg"},
        {"name": "galbi",                  "diet": "non-veg"},
        {"name": "sundubu jjigae",         "diet": "non-veg"},
        {"name": "korean fried chicken",   "diet": "non-veg"},
        {"name": "pajeon",                 "diet": "eggtarian"},
        {"name": "kongnamul",              "diet": "veg"},
        {"name": "samgyeopsal",            "diet": "non-veg"},
        {"name": "kimbap",                 "diet": "non-veg"},
        {"name": "yukgaejang",             "diet": "non-veg"},
    ],

    "mediterranean": [
        {"name": "hummus",                 "diet": "veg"},
        {"name": "falafel",                "diet": "veg"},
        {"name": "greek salad",            "diet": "veg"},
        {"name": "moussaka",               "diet": "non-veg"},
        {"name": "spanakopita",            "diet": "veg"},
        {"name": "tzatziki",               "diet": "veg"},
        {"name": "shakshuka",              "diet": "eggtarian"},
        {"name": "tabbouleh",              "diet": "veg"},
        {"name": "lamb kebab",             "diet": "non-veg"},
        {"name": "pita bread",             "diet": "veg"},
        {"name": "lentil soup",            "diet": "veg"},
        {"name": "baba ganoush",           "diet": "veg"},
        {"name": "chicken shawarma",       "diet": "non-veg"},
        {"name": "fattoush salad",         "diet": "veg"},
    ],

    "vietnamese": [
        {"name": "pho bo",                 "diet": "non-veg"},
        {"name": "banh mi",                "diet": "non-veg"},
        {"name": "bun bo hue",             "diet": "non-veg"},
        {"name": "goi cuon",               "diet": "non-veg"},
        {"name": "com tam",                "diet": "non-veg"},
        {"name": "ca kho to",              "diet": "non-veg"},
        {"name": "bun cha",                "diet": "non-veg"},
        {"name": "banh xeo",               "diet": "non-veg"},
        {"name": "che ba mau",             "diet": "veg"},
        {"name": "rau muong xao toi",      "diet": "veg"},
    ],
}

# Canonical cuisine tag for each catalogue key
CUISINE_TAG = {
    "north_indian":        "indian",
    "south_indian":        "indian",
    "east_indian":         "indian",
    "indian_street_food":  "indian",
    "chinese":             "chinese",
    "japanese":            "japanese",
    "thai":                "thai",
    "italian":             "italian",
    "american":            "american",
    "mexican":             "mexican",
    "korean":              "korean",
    "mediterranean":       "mediterranean",
    "vietnamese":          "vietnamese",
}

# ─────────────────────────────────────────────────────────────────────────────
# Prompt builder
# ─────────────────────────────────────────────────────────────────────────────
_SYSTEM = """You are a world-class culinary expert with deep knowledge of authentic,
home-style cooking from every cuisine and region on earth.
You generate recipes exactly as a home cook in that region would make them —
not restaurant versions, not Westernized versions, not fusion.

Output rules (strict):
- ALWAYS respond with a JSON object with a single key "recipes" whose value is an array.
  Example: {"recipes": [{...recipe1...}, {...recipe2...}]}
  Even for a single recipe, wrap it: {"recipes": [{...}]}
- Quantities MUST use ONLY these three units: "g", "ml", or "count".
  Convert ALL volumes to ml: 1 tsp = 5 ml, 1 tbsp = 15 ml, 1 cup = 240 ml.
  Convert ALL weights to grams.
  Use "count" for things naturally counted: eggs, garlic cloves, onions, chilies,
  bay leaves, cardamom pods, cinnamon sticks, etc.
- Use the ingredient names a home cook in that specific region would actually use.
  Do NOT Westernize or Americanize ingredient names for non-American cuisines."""

# Authenticity hints per catalogue key — tells the model exactly what a
# home cook in that region uses, avoiding generic/Westernized substitutes
_CUISINE_HINTS: Dict[str, str] = {
    "north_indian": (
        "Use ghee or mustard oil, not butter or olive oil. "
        "Use coriander (not cilantro), capsicum (not bell pepper), "
        "green chili (not jalapeño), garam masala, cumin, coriander powder, turmeric. "
        "Tomatoes and onions form the base. Garlic and ginger are always fresh, not powdered. "
        "Dal recipes must use the specific lentil (toor, chana, urad, moong) — not generic 'lentils'."
    ),
    "south_indian": (
        "Use coconut oil as the primary fat, not vegetable oil. "
        "Tempering (tadka) uses mustard seeds, curry leaves, dried red chili, urad dal. "
        "Use tamarind for sourness, not lemon. Use coconut — fresh or desiccated — liberally. "
        "Rice-based dishes use short-grain or parboiled rice. "
        "Use 'coriander leaves' not cilantro. Use asafoetida (hing) in lentil dishes."
    ),
    "east_indian": (
        "Bengali cuisine uses mustard oil and panch phoron (five-spice blend: "
        "fenugreek, nigella, cumin, black mustard, fennel seeds). "
        "Fish is always fresh — hilsa, rohu, katla. Use turmeric generously. "
        "Sweets use khoya/mawa and chhena (fresh cottage cheese). "
        "Use green chili not red for heat in most dishes."
    ),
    "indian_street_food": (
        "Use chaat masala, tamarind chutney, green chutney (coriander + mint). "
        "Pav is soft white dinner rolls. Use fine sev (chickpea flour vermicelli). "
        "Chutneys are essential — don't omit them. "
        "Use black salt (kala namak) for chaat dishes."
    ),
    "chinese": (
        "Use Shaoxing rice wine, not dry sherry. Use dark soy sauce AND light soy sauce — they are different. "
        "Use sesame oil only as a finishing oil, not for cooking. "
        "Use doubanjiang (fermented broad bean paste) for Sichuan dishes. "
        "Use rice vinegar, not white vinegar. "
        "Wok hei (high heat) technique is essential — describe it in steps. "
        "Fresh ginger and garlic, not powdered. Chinese five-spice where appropriate."
    ),
    "japanese": (
        "Use dashi (kombu + katsuobushi) as the base stock — not chicken stock. "
        "Use mirin and sake in marinades and sauces. "
        "Use Japanese soy sauce (shoyu), not Chinese soy sauce. "
        "Use Japanese short-grain rice. Use miso paste (white/red depending on dish). "
        "Use rice vinegar seasoned with sugar and salt for sushi rice. "
        "Togarashi for heat. Bonito flakes as garnish."
    ),
    "thai": (
        "Use fish sauce (nam pla) as the primary salt. Use palm sugar, not white sugar. "
        "Use Thai basil, not Italian basil — they taste completely different. "
        "Use galangal not ginger for curries. Use kaffir lime leaves and lemongrass. "
        "Use coconut milk for curries, coconut cream for richer dishes. "
        "Use tamarind paste for sour notes. Bird's eye chilies for heat."
    ),
    "italian": (
        "Use extra virgin olive oil. Use Parmigiano-Reggiano, not generic parmesan. "
        "Use San Marzano tomatoes for sauces. Use guanciale for carbonara, not bacon. "
        "Fresh pasta where traditional, dried pasta where traditional. "
        "Use pecorino romano for Roman dishes. Use proper Italian herbs: basil, oregano, rosemary. "
        "Do not use cream in carbonara — it is eggs, guanciale, pecorino, black pepper only."
    ),
    "american": (
        "Use buttermilk for fried chicken and biscuits. Use smoked paprika. "
        "BBQ sauce should have a tomato-vinegar-molasses base. "
        "Use sharp cheddar for mac and cheese. Butter generously. "
        "Use Worcestershire sauce for depth in meat dishes."
    ),
    "mexican": (
        "Use lard or neutral oil, not olive oil. Use dried chilies: ancho, pasilla, guajillo, chipotle. "
        "Use epazote in bean dishes. Use Mexican oregano, not Mediterranean oregano. "
        "Use masa harina for tortillas and tamales. Use cilantro generously as a garnish. "
        "Use queso fresco or cotija, not cheddar. Use crema not sour cream."
    ),
    "korean": (
        "Use gochujang (fermented red pepper paste) and gochugaru (red pepper flakes) — not generic chili. "
        "Use doenjang (fermented soybean paste) not miso. Use sesame oil as a finishing oil. "
        "Use fish sauce, salted shrimp (saewujeot) for fermented depth. "
        "Use short-grain Korean rice. Use perilla leaves, Korean green onion."
    ),
    "mediterranean": (
        "Use extra virgin olive oil generously. Use dried oregano, thyme, sumac, za'atar. "
        "Use tahini (sesame paste) for dips and sauces. Use pomegranate molasses for depth. "
        "Use Greek yogurt (strained, thick). Use feta in brine. "
        "Use flat-leaf parsley, not curly. Use lemon juice generously."
    ),
    "vietnamese": (
        "Use fish sauce (nuoc mam) as the primary seasoning. Use rice noodles — specify the type. "
        "Use fresh herbs at the table: mint, perilla, bean sprouts, Thai basil. "
        "Use lemongrass, galangal, shrimp paste. Nuoc cham dipping sauce is essential. "
        "Use rice paper for rolls. Caramelized fish sauce in clay pots for ca kho to."
    ),
}

def _build_prompt(dishes: List[Dict[str, str]], cuisine_tag: str,
                  cat_key: str = "") -> str:
    dish_list = "\n".join(
        f'  - "{d["name"]}" (diet: {d["diet"]})' for d in dishes
    )
    hint = _CUISINE_HINTS.get(cat_key, "")
    hint_block = f"\nAuthenticity notes for this cuisine:\n{hint}\n" if hint else ""

    return f"""Generate authentic home-style recipes for EXACTLY these dishes:
{dish_list}
{hint_block}
Return a JSON object with a single key "recipes" containing an array of recipe objects.
Each recipe object must have EXACTLY these fields:
{{
  "name":           "<lowercase dish name>",
  "cuisine":        "{cuisine_tag}",
  "diet":           "<veg | eggtarian | non-veg>",
  "prep_time_min":  <integer>,
  "cook_time_min":  <integer>,
  "ingredients": [
    {{"item": "<singular lowercase name>", "quantity": <positive number>, "unit": "<g|ml|count>"}}
  ],
  "steps": ["<step 1>", "<step 2>", ...]
}}

Rules:
- Generate ONE recipe per dish listed above. Output {len(dishes)} recipes total.
- Minimum 5 ingredients, minimum 4 steps per recipe.
- All quantities must be positive numbers (integers preferred).
- Units MUST be exactly "g", "ml", or "count" — nothing else.
- Steps must be detailed enough for a home cook to follow without guessing.
- Wrap ALL recipes in {{"recipes": [...]}} — never return a bare array or single object."""

# ─────────────────────────────────────────────────────────────────────────────
# Schema validator
# ─────────────────────────────────────────────────────────────────────────────
VALID_UNITS = {"g", "ml", "count"}
VALID_DIETS = {"veg", "eggtarian", "non-veg"}

def _validate(recipe: dict, context: str = "") -> List[str]:
    errors = []
    for field in ("name", "cuisine", "diet", "prep_time_min", "cook_time_min",
                  "ingredients", "steps"):
        if field not in recipe:
            errors.append(f"missing field '{field}'")
    if errors:
        return errors
    if recipe["diet"] not in VALID_DIETS:
        errors.append(f"invalid diet '{recipe['diet']}'")
    if not isinstance(recipe["ingredients"], list) or len(recipe["ingredients"]) < 2:
        errors.append("need at least 2 ingredients")
    for i, ing in enumerate(recipe.get("ingredients", [])):
        if not isinstance(ing, dict):
            errors.append(f"ingredient[{i}] not a dict")
            continue
        if "item" not in ing or "quantity" not in ing or "unit" not in ing:
            errors.append(f"ingredient[{i}] missing item/quantity/unit")
            continue
        if ing["unit"] not in VALID_UNITS:
            errors.append(f"ingredient[{i}] bad unit '{ing['unit']}'")
        try:
            qty = float(ing["quantity"])
            if qty <= 0:
                errors.append(f"ingredient[{i}] quantity must be > 0")
        except (TypeError, ValueError):
            errors.append(f"ingredient[{i}] quantity not a number")
    if not isinstance(recipe.get("steps"), list) or len(recipe.get("steps", [])) < 2:
        errors.append("need at least 2 steps")
    return errors

# ─────────────────────────────────────────────────────────────────────────────
# Programmatic sanity checks (fast, free — runs before LLM review)
# ─────────────────────────────────────────────────────────────────────────────

# Ingredients that should never appear in veg/eggtarian recipes
_NON_VEG_INGREDIENTS = {
    "chicken", "beef", "pork", "lamb", "mutton", "fish", "prawn", "shrimp",
    "crab", "lobster", "anchovy", "anchovies", "bacon", "ham", "salami",
    "pepperoni", "turkey", "duck", "venison", "lard", "gelatin",
    "fish sauce", "oyster sauce", "worcestershire sauce",
}
_EGG_INGREDIENTS = {"egg", "eggs", "egg yolk", "egg white"}

# Reasonable quantity bounds per unit (flag extreme outliers for LLM to fix)
_QTY_BOUNDS = {
    "g":     (1,   2000),   # 1g–2kg per ingredient is sane
    "ml":    (1,   1000),   # 1ml–1L per ingredient
    "count": (1,   50),     # 1–50 items
}

def _programmatic_issues(recipe: dict) -> List[str]:
    """Fast rule-based checks. Returns list of issue strings (empty = clean)."""
    issues = []
    diet    = recipe.get("diet", "")
    ing_names = {(i.get("item") or "").lower().strip()
                 for i in recipe.get("ingredients", [])}

    # Diet mismatch
    if diet == "veg":
        bad = ing_names & (_NON_VEG_INGREDIENTS | _EGG_INGREDIENTS)
        if bad: issues.append(f"diet=veg but contains: {bad}")
    if diet == "eggtarian":
        bad = ing_names & _NON_VEG_INGREDIENTS
        if bad: issues.append(f"diet=eggtarian but contains: {bad}")

    # Quantity outliers
    for ing in recipe.get("ingredients", []):
        try:
            qty  = float(ing.get("quantity", 0))
            unit = ing.get("unit", "")
            lo, hi = _QTY_BOUNDS.get(unit, (1, 9999))
            if qty < lo or qty > hi:
                issues.append(
                    f"'{ing['item']}': {qty} {unit} is outside sane range "
                    f"[{lo}–{hi}]"
                )
        except Exception:
            pass

    return issues

# ─────────────────────────────────────────────────────────────────────────────
# LLM-as-judge reviewer
# ─────────────────────────────────────────────────────────────────────────────

_REVIEW_SYSTEM = """You are a strict culinary quality reviewer for a global recipe app.
You receive a JSON array of recipes with optional known issues flagged.
Fix every recipe and return a cleaned JSON array. Be thorough — this is the last
quality gate before these recipes go live to users.

Fix these issues in every recipe:

1. INGREDIENT NAMES — make them pantry-friendly (what a home cook would buy/label):
   - "freshly squeezed lime juice"  → item:"lime", unit:"count"
   - "toasted sesame seeds"         → item:"sesame seed", unit:"g"
   - "cilantro"                     → item:"coriander" for Indian/Asian recipes
   - "bell pepper"                  → item:"capsicum" for Indian recipes
   - "scallion" or "green onion"    → item:"spring onion"
   - "all-purpose flour"            → item:"flour", unit:"g"
   - Any "X sauce" should stay as "X sauce" (do not reduce to just "sauce")
   - Any "X oil" should stay as "X oil" unless it's "vegetable oil" or "cooking oil"

2. QUANTITIES — fix unrealistic amounts:
   - Garlic: typically 5–30g total per dish, not 500g
   - Salt: 3–15g per dish, not 200g
   - Spices (cumin, coriander powder etc): 2–15g each
   - Main protein: 300–800g for a dish serving 2–4 people
   - If a quantity looks like it was meant for 100 servings, scale it to 4 servings

3. DIET TAG — fix if wrong:
   - "veg" recipes must not contain meat, fish, seafood, or eggs
   - "eggtarian" recipes must not contain meat or fish
   - "non-veg" is fine with anything

4. UNITS — fix anything that is not exactly "g", "ml", or "count"

5. REJECT a recipe only if it is fundamentally broken in a way you cannot fix:
   - Completely wrong dish (generated a different dish entirely)
   - Fewer than 4 ingredients after fixing
   - Incoherent or missing steps
   Set "REJECT":true and "REJECT_REASON":"..." on the recipe object.

Return ONLY a JSON object with key "recipes" containing the fixed array.
Example: {"recipes": [{...recipe1...}, {...recipe2...}]}
No markdown, no extra text."""

def _review_batch(recipes: List[dict], issues_map: Dict[str, List[str]]) -> List[dict]:
    """
    Send a batch of recipes to GPT-4o-mini for quality review and fixing.
    Returns the corrected list (rejected recipes are dropped).
    """
    # Attach known issues as a hint to the reviewer
    annotated = []
    for r in recipes:
        r_copy = dict(r)
        known = issues_map.get(r.get("name", ""), [])
        if known:
            r_copy["_KNOWN_ISSUES"] = known
        annotated.append(r_copy)

    prompt = (
        "Review and fix this recipe batch. "
        "Return the corrected JSON array (drop any with REJECT:true):\n\n"
        + json.dumps(annotated, ensure_ascii=False, indent=2)
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _REVIEW_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.1,       # low temperature — we want deterministic fixes
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        parsed = json.loads(raw)

        # Expected: {"recipes": [...]}
        if isinstance(parsed, dict) and "recipes" in parsed:
            result = parsed["recipes"]
        elif isinstance(parsed, list):
            result = parsed
        else:
            result = []
            for k in parsed:
                val = parsed[k]
                if (isinstance(val, list) and val and
                        isinstance(val[0], dict) and
                        "name" in val[0] and "ingredients" in val[0]):
                    result = val
                    break

        # Strip internal annotation keys and rejected recipes
        cleaned = []
        for r in result:
            if not isinstance(r, dict):
                continue
            if r.get("REJECT"):
                print(f"  [FAIL]  Reviewer rejected '{r.get('name')}': "
                      f"{r.get('REJECT_REASON','no reason given')}")
                continue
            r.pop("_KNOWN_ISSUES",  None)
            r.pop("REJECT",         None)
            r.pop("REJECT_REASON",  None)
            cleaned.append(r)
        return cleaned

    except Exception as e:
        print(f"  [WARN]  Review call failed: {e} — keeping original recipes")
        return recipes   # fall back to unreviewed if review errors

# ─────────────────────────────────────────────────────────────────────────────
# GPT call
# ─────────────────────────────────────────────────────────────────────────────
def _call_gpt(dishes: List[Dict[str, str]], cuisine_tag: str,
              cat_key: str = "", retries: int = 2) -> List[dict]:
    prompt = _build_prompt(dishes, cuisine_tag, cat_key)
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",          # higher quality for authentic generation
                messages=[
                    {"role": "system",  "content": _SYSTEM},
                    {"role": "user",    "content": prompt},
                ],
                temperature=0.3,         # slightly lower = more consistent quality
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content.strip()
            parsed = json.loads(raw)
            # Expected: {"recipes": [...]}
            if isinstance(parsed, dict) and "recipes" in parsed:
                return parsed["recipes"]
            # Fallback: bare list
            if isinstance(parsed, list):
                return parsed
            # Fallback: single recipe object returned instead of wrapped array
            if (isinstance(parsed, dict) and
                    "name" in parsed and "ingredients" in parsed and "steps" in parsed):
                return [parsed]
            # Last resort: find any list of recipe dicts
            for key in parsed:
                val = parsed[key]
                if (isinstance(val, list) and val and
                        isinstance(val[0], dict) and
                        "name" in val[0] and "ingredients" in val[0]):
                    return val
            print(f"  [WARN]  Unexpected JSON shape: {list(parsed.keys())}")
            return []
        except json.JSONDecodeError as e:
            print(f"  [WARN]  JSON parse error (attempt {attempt+1}): {e}")
            if attempt == retries:
                return []
            time.sleep(2)
        except Exception as e:
            print(f"  [WARN]  API error (attempt {attempt+1}): {e}")
            if attempt == retries:
                return []
            time.sleep(3)
    return []

# ─────────────────────────────────────────────────────────────────────────────
# Load / save helpers
# ─────────────────────────────────────────────────────────────────────────────
def _load_json(path: Path) -> list:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []

def _save_json(path: Path, data: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ─────────────────────────────────────────────────────────────────────────────
# Generation
# ─────────────────────────────────────────────────────────────────────────────
def generate(cuisine_filter: str | None = None,
             batch_size: int = 5,
             skip_review: bool = False) -> None:
    staged      = _load_json(STAGED_PATH)
    existing    = _load_json(RECIPE_PATH)
    known_names = {r["name"].lower().strip()
                   for r in (staged + existing) if isinstance(r, dict)}

    catalogues = {k: v for k, v in DISH_CATALOGUE.items()
                  if (cuisine_filter is None or
                      k == cuisine_filter or
                      CUISINE_TAG.get(k, "") == cuisine_filter)}

    if not catalogues:
        print(f"No catalogue found for '{cuisine_filter}'.")
        print(f"Available keys: {list(DISH_CATALOGUE.keys())}")
        return

    total_new      = 0
    total_skipped  = 0
    total_errors   = 0
    total_rejected = 0

    for cat_key, dishes in catalogues.items():
        cuisine_tag = CUISINE_TAG[cat_key]
        to_generate = [d for d in dishes if d["name"].lower() not in known_names]
        if not to_generate:
            print(f"[{cat_key}] All dishes already staged/existing — skipping.")
            continue

        print(f"\n[{cat_key}] Generating {len(to_generate)} dishes "
              f"(cuisine: {cuisine_tag}, batch size: {batch_size})")

        for i in range(0, len(to_generate), batch_size):
            batch = to_generate[i : i + batch_size]
            names = [d["name"] for d in batch]
            print(f"  Batch {i//batch_size + 1}: {names}")

            # ── Step 1: Generate ──────────────────────────────────────────────
            recipes = _call_gpt(batch, cuisine_tag, cat_key=cat_key)
            if not recipes:
                print(f"  [FAIL]  No recipes returned.")
                total_errors += len(batch)
                continue

            # Normalise names + quantities
            for r in recipes:
                if not isinstance(r, dict): continue
                r["name"] = str(r.get("name","")).lower().strip()
                for ing in r.get("ingredients", []):
                    try:
                        q = float(ing["quantity"])
                        ing["quantity"] = int(q) if q == int(q) else round(q, 1)
                    except Exception:
                        pass

            # ── Step 2: Programmatic sanity checks ────────────────────────────
            issues_map: Dict[str, List[str]] = {}
            for r in recipes:
                if not isinstance(r, dict): continue
                issues = _programmatic_issues(r)
                if issues:
                    print(f"  [WARN]  '{r.get('name')}' has issues: {issues}")
                    issues_map[r.get("name","")] = issues

            # ── Step 3: LLM review & fix (every 2 gen-batches = 10 recipes) ───
            if not skip_review:
                print(f"  Reviewing {len(recipes)} recipes with LLM judge...")
                before = len(recipes)
                recipes = _review_batch(recipes, issues_map)
                rejected = before - len(recipes)
                if rejected:
                    total_rejected += rejected
                    print(f"  LLM rejected {rejected} recipe(s).")
                time.sleep(0.5)

            # ── Step 4: Final schema validation + stage ───────────────────────
            added_this_batch = 0
            for r in recipes:
                if not isinstance(r, dict): continue
                errors = _validate(r)
                if errors:
                    print(f"  [FAIL]  '{r.get('name')}' still fails validation after review: {errors}")
                    total_errors += 1
                    continue
                if r["name"] in known_names:
                    total_skipped += 1
                    continue
                staged.append(r)
                known_names.add(r["name"])
                added_this_batch += 1
                total_new += 1

            print(f"  [OK]  Staged {added_this_batch}/{len(batch)}")
            _save_json(STAGED_PATH, staged)
            time.sleep(0.5)

    print(f"\n{'-'*50}")
    print(f"Done.  Staged: {total_new}  |  Skipped: {total_skipped}  "
          f"|  Rejected by LLM: {total_rejected}  |  Errors: {total_errors}")
    print(f"Recipes saved to: {STAGED_PATH}")
    print(f"Run:  python scripts/generate_recipes.py --merge  to publish")

# ─────────────────────────────────────────────────────────────────────────────
# Merge staged → recipe.json
# ─────────────────────────────────────────────────────────────────────────────
def merge() -> None:
    staged   = _load_json(STAGED_PATH)
    existing = _load_json(RECIPE_PATH)
    if not staged:
        print("Nothing staged. Run generation first.")
        return

    existing_names = {r["name"].lower().strip() for r in existing if isinstance(r, dict)}
    new_recipes = [r for r in staged
                   if isinstance(r, dict) and r.get("name","").lower().strip()
                   not in existing_names]

    print(f"Staged:   {len(staged)} recipes")
    print(f"Existing: {len(existing)} recipes")
    print(f"New to add: {len(new_recipes)}")

    if not new_recipes:
        print("Nothing new to merge.")
        return

    merged = existing + new_recipes
    _save_json(RECIPE_PATH, merged)
    # Clear staged after merge
    _save_json(STAGED_PATH, [])
    print(f"Merged! recipe.json now has {len(merged)} recipes.")
    print("Staged file cleared.")

# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KitchBot recipe generator")
    parser.add_argument("--cuisine", type=str, default=None,
                        help="Generate only this cuisine key (e.g. south_indian, japanese)")
    parser.add_argument("--merge",   action="store_true",
                        help="Merge staged recipes into recipe.json")
    parser.add_argument("--batch",     type=int,  default=5,
                        help="Dishes per API call (default 5)")
    parser.add_argument("--no-review", action="store_true",
                        help="Skip LLM review step (faster, less quality control)")
    args = parser.parse_args()

    if args.merge:
        merge()
    else:
        generate(cuisine_filter=args.cuisine,
                 batch_size=args.batch,
                 skip_review=args.no_review)
