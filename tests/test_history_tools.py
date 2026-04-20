# tests/test_history_tools.py
# Unit tests for meal history, recipe ratings, food waste impact, and expiry tracking.

import os, sys, json, datetime, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── history ───────────────────────────────────────────────────────────────────

def test_log_meal_creates_record(tmp_path, monkeypatch):
    from tools import history_tools as ht
    monkeypatch.setattr(ht, "HISTORY_PATH", str(tmp_path / "history.json"))
    monkeypatch.setattr(ht, "IMPACT_PATH",  str(tmp_path / "impact.json"))

    ht.log_meal_to_history("Palak Paneer", day="Day1", meal="Lunch",
                            ingredients_consumed=[{"item": "spinach", "qty": 500, "unit": "g"}],
                            household_size=2)

    history = json.loads(open(str(tmp_path / "history.json")).read())
    assert len(history) == 1
    assert history[0]["dish"] == "Palak Paneer"
    assert history[0]["household_size"] == 2
    assert history[0]["waste_saved_g"] == 500


def test_recently_cooked_within_window(tmp_path, monkeypatch):
    from tools import history_tools as ht
    monkeypatch.setattr(ht, "HISTORY_PATH", str(tmp_path / "history.json"))
    monkeypatch.setattr(ht, "IMPACT_PATH",  str(tmp_path / "impact.json"))

    ht.log_meal_to_history("Dal Tadka")
    recent = ht.recently_cooked_dishes(within_days=7)
    assert "dal tadka" in recent


def test_recently_cooked_outside_window(tmp_path, monkeypatch):
    from tools import history_tools as ht
    monkeypatch.setattr(ht, "HISTORY_PATH", str(tmp_path / "history.json"))
    monkeypatch.setattr(ht, "IMPACT_PATH",  str(tmp_path / "impact.json"))

    old_record = {
        "dish": "Butter Chicken",
        "cooked_at": (datetime.datetime.now() - datetime.timedelta(days=10)).isoformat(),
        "day": "", "meal": "", "ingredients_consumed": [], "household_size": 1, "waste_saved_g": 0,
    }
    with open(str(tmp_path / "history.json"), "w") as f:
        json.dump([old_record], f)

    recent = ht.recently_cooked_dishes(within_days=7)
    assert "butter chicken" not in recent


# ── ratings ───────────────────────────────────────────────────────────────────

def test_rate_recipe_up(tmp_path, monkeypatch):
    from tools import history_tools as ht
    monkeypatch.setattr(ht, "FEEDBACK_PATH", str(tmp_path / "feedback.json"))

    result = ht.rate_recipe.invoke({"recipe_name": "Palak Paneer", "rating": "up"})
    assert "👍" in result

    fb = json.loads(open(str(tmp_path / "feedback.json")).read())
    assert fb["palak paneer"]["thumbs_up"] == 1
    assert fb["palak paneer"]["last_rating"] == "up"


def test_rate_recipe_down(tmp_path, monkeypatch):
    from tools import history_tools as ht
    monkeypatch.setattr(ht, "FEEDBACK_PATH", str(tmp_path / "feedback.json"))

    ht.rate_recipe.invoke({"recipe_name": "Mystery Dish", "rating": "down"})
    fb = json.loads(open(str(tmp_path / "feedback.json")).read())
    assert fb["mystery dish"]["thumbs_down"] == 1
    assert fb["mystery dish"]["last_rating"] == "down"


def test_rate_recipe_invalid(tmp_path, monkeypatch):
    from tools import history_tools as ht
    monkeypatch.setattr(ht, "FEEDBACK_PATH", str(tmp_path / "feedback.json"))

    result = ht.rate_recipe.invoke({"recipe_name": "Dal", "rating": "meh"})
    assert "⚠️" in result


def test_rate_recipe_accumulates(tmp_path, monkeypatch):
    from tools import history_tools as ht
    monkeypatch.setattr(ht, "FEEDBACK_PATH", str(tmp_path / "feedback.json"))

    ht.rate_recipe.invoke({"recipe_name": "Poha", "rating": "up"})
    ht.rate_recipe.invoke({"recipe_name": "Poha", "rating": "up"})
    ht.rate_recipe.invoke({"recipe_name": "Poha", "rating": "down"})

    fb = json.loads(open(str(tmp_path / "feedback.json")).read())
    assert fb["poha"]["thumbs_up"] == 2
    assert fb["poha"]["thumbs_down"] == 1


# ── impact ────────────────────────────────────────────────────────────────────

def test_impact_updates_on_log(tmp_path, monkeypatch):
    from tools import history_tools as ht
    monkeypatch.setattr(ht, "HISTORY_PATH", str(tmp_path / "history.json"))
    monkeypatch.setattr(ht, "IMPACT_PATH",  str(tmp_path / "impact.json"))

    ht.log_meal_to_history("Rice", ingredients_consumed=[
        {"item": "rice", "qty": 200, "unit": "g"},
        {"item": "water", "qty": 400, "unit": "ml"},  # ml not counted
    ])
    impact = json.loads(open(str(tmp_path / "impact.json")).read())
    assert impact["total_meals_cooked"] == 1
    assert impact["total_waste_saved_g"] == 200  # only g counted


# ── expiry ────────────────────────────────────────────────────────────────────

def test_set_expiry_stores_date(tmp_path, monkeypatch):
    from tools import expiry_tools as et
    monkeypatch.setattr(et, "EXPIRY_PATH", str(tmp_path / "expiry.json"))

    future = str(datetime.date.today() + datetime.timedelta(days=5))
    result = et.set_expiry.invoke({"item": "milk", "expires": future})
    assert "✅" in result

    data = json.loads(open(str(tmp_path / "expiry.json")).read())
    assert "milk" in data
    assert data["milk"]["expires"] == future


def test_get_expiring_items_filters(tmp_path, monkeypatch):
    from tools import expiry_tools as et
    monkeypatch.setattr(et, "EXPIRY_PATH", str(tmp_path / "expiry.json"))

    today = datetime.date.today()
    data = {
        "milk":    {"expires": str(today + datetime.timedelta(days=2))},  # expiring
        "chicken": {"expires": str(today + datetime.timedelta(days=10))}, # not expiring
    }
    with open(str(tmp_path / "expiry.json"), "w") as f:
        json.dump(data, f)

    items = et.get_expiring_items(within_days=3)
    names = [i["item"] for i in items]
    assert "milk" in names
    assert "chicken" not in names


def test_remove_expiry(tmp_path, monkeypatch):
    from tools import expiry_tools as et
    monkeypatch.setattr(et, "EXPIRY_PATH", str(tmp_path / "expiry.json"))

    future = str(datetime.date.today() + datetime.timedelta(days=3))
    et.set_expiry.invoke({"item": "egg", "expires": future})
    et.remove_expiry.invoke({"item": "egg"})

    data = json.loads(open(str(tmp_path / "expiry.json")).read())
    assert "egg" not in data
