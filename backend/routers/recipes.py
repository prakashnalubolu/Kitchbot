# backend/routers/recipes.py
from fastapi import APIRouter
from backend.models import RecipeSearchIn, RecipeMatchIn, TextResponse

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from tools.cuisine_tools import find_recipes_by_items, list_recipes, get_recipe
from tools.manager_tools import missing_ingredients, suggest_substitutions

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.get("/", response_model=TextResponse)
def browse_recipes(cuisine: str = None, max_time: int = None, diet: str = None):
    return TextResponse(result=list_recipes.invoke({
        "cuisine": cuisine,
        "max_time": max_time,
        "diet": diet,
    }))


@router.get("/{dish_name}", response_model=TextResponse)
def get_single_recipe(dish_name: str):
    return TextResponse(result=get_recipe.invoke(dish_name))


@router.post("/match", response_model=TextResponse)
def match_recipes(body: RecipeMatchIn):
    return TextResponse(result=find_recipes_by_items.invoke({
        "items": body.items,
        "cuisine": body.cuisine,
        "max_time": body.max_time,
        "diet": body.diet,
        "k": body.k,
    }))


@router.get("/{dish_name}/missing", response_model=TextResponse)
def get_missing(dish_name: str):
    return TextResponse(result=missing_ingredients.invoke(dish_name))
