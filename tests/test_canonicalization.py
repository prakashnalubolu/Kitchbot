"""
Regression tests for tools/textnorm.py canonical_key().

Run with:  python -m pytest tests/test_canonicalization.py -v
       or:  python tests/test_canonicalization.py

PURPOSE: Catch spaCy mis-parses or alias regressions before they reach users.
The USP of KitchBot is "cook with what you have" — ingredient matching is critical.
Add a case here any time a new ingredient bug is found and fixed.
"""

from tools.textnorm import canonical_key

CASES = {
    # ── Garlic forms ────────────────────────────────────────────────────────
    # spaCy singular mis-parse: "garlic clove" → "clove" (drops "garlic")
    "garlic clove":           "garlic",
    "garlic cloves":          "garlic",
    "garlic":                 "garlic",
    "garlic paste":           "garlic paste",   # paste ≠ raw garlic

    # ── Oils — must stay distinct, never collapse to "oil" ──────────────────
    "sesame oil":             "sesame oil",
    "olive oil":              "olive oil",
    "chili oil":              "chili oil",
    "coconut oil":            "coconut oil",
    "mustard oil":            "mustard oil",
    "extra virgin olive oil": "olive oil",      # drops "extra virgin" (descriptors)
    "vegetable oil":          "oil",            # generic, collapsing is fine

    # ── Vinegars — must stay distinct ───────────────────────────────────────
    "balsamic vinegar":       "balsamic vinegar",
    "rice vinegar":           "rice vinegar",

    # ── Dairy — condensed milk ≠ milk ───────────────────────────────────────
    "condensed milk":         "condensed milk",
    "coconut milk":           "coconut milk",
    "almond milk":            "almond milk",

    # ── Rice variants — glutinous ≠ regular rice ────────────────────────────
    "glutinous rice":         "glutinous rice",
    "basmati rice":           "basmati rice",

    # ── Gourds — bitter ≠ bottle ────────────────────────────────────────────
    "bitter gourd":           "bitter gourd",
    "bottle gourd":           "bottle gourd",

    # ── Cheese identity ─────────────────────────────────────────────────────
    "feta cheese":            "feta cheese",

    # ── Leaf plurals — recipe "bay leaves" must match pantry "bay leaf" ─────
    "bay leaf":               "bay leaf",
    "bay leaves":             "bay leaf",
    "curry leaf":             "curry leaf",
    "curry leaves":           "curry leaf",
    "kaffir lime leaf":       "kaffir lime leaf",
    "kaffir lime leaves":     "kaffir lime leaf",

    # ── Leaf plurals that correctly strip to base (matches pantry name) ─────
    "basil leaves":           "basil",
    "coriander leaves":       "coriander",
    "mint leaves":            "mint",
    "thai basil leaves":      "thai basil",

    # ── Plant-part suffixes (first word IS the pantry ingredient) ───────────
    "cardamom pod":           "cardamom",
    "cardamom pods":          "cardamom",
    "cashew nut":             "cashew",
    "cashew nuts":            "cashew",
    "corn on the cob":        "corn",

    # ── Paste identity — different pastes must stay distinct ────────────────
    "ginger paste":           "ginger paste",
    "tomato paste":           "tomato paste",

    # ── Prep-modifier stripping (intentional — base ingredient preserved) ───
    "boneless chicken":       "chicken",
    "fresh ginger":           "ginger",
    "dried oregano":          "oregano",
    "canned tomatoes":        "tomato",
    "minced pork":            "pork",

    # ── Chili normalization ─────────────────────────────────────────────────
    "chilli":                 "chili",
    "green chilli":           "green chili",
    "red chilli":             "red chili",
    "green chili":            "green chili",
    "red chili":              "red chili",

    # ── Compound atomics — must NOT be covered by single-word pantry items ──
    # (these are tested in _fuzzy_covers, but canonical should preserve them)
    "soy sauce":              "soy sauce",
    "fish sauce":             "fish sauce",
    "oyster sauce":           "oyster sauce",

    # ── Common single-word pantry items ─────────────────────────────────────
    "chicken":                "chicken",
    "onion":                  "onion",
    "tomato":                 "tomato",
    "spinach":                "spinach",
    "ginger":                 "ginger",
    "paneer":                 "paneer",
    "egg":                    "egg",
    "rice":                   "rice",
    "flour":                  "flour",
}


def run_tests() -> None:
    failures = []
    for phrase, expected in CASES.items():
        got = canonical_key(phrase)
        if got != expected:
            failures.append((phrase, expected, got))

    total = len(CASES)
    passed = total - len(failures)
    print(f"\ncanonical_key regression: {passed}/{total} passed")

    if failures:
        print("\nFAILURES:")
        for phrase, expected, got in failures:
            print(f"  {phrase!r:<30} expected {expected!r}, got {got!r}")
        raise AssertionError(f"{len(failures)} test(s) failed")
    else:
        print("All passed.")


# pytest-compatible individual test
def test_canonical_key():
    run_tests()


if __name__ == "__main__":
    run_tests()
