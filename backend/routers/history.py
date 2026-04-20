# backend/routers/history.py
from fastapi import APIRouter
from backend.models import (
    RateRecipeIn, HistoryQueryIn, VarietyQueryIn, TopRecipesIn, TextResponse,
)

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from tools.history_tools import (
    get_cook_history, suggest_variety, rate_recipe,
    get_top_recipes, get_impact_stats,
)

router = APIRouter(prefix="/history", tags=["history"])


@router.get("/", response_model=TextResponse)
def cook_history(days: int = 30):
    return TextResponse(result=get_cook_history.invoke({"days": days}))


@router.get("/variety", response_model=TextResponse)
def variety_suggestions(days: int = 7):
    return TextResponse(result=suggest_variety.invoke({"days": days}))


@router.get("/top", response_model=TextResponse)
def top_recipes(limit: int = 10):
    return TextResponse(result=get_top_recipes.invoke({"limit": limit}))


@router.get("/impact", response_model=TextResponse)
def impact_stats():
    return TextResponse(result=get_impact_stats.invoke({}))


@router.post("/rate", response_model=TextResponse)
def rate(body: RateRecipeIn):
    return TextResponse(result=rate_recipe.invoke({
        "recipe_name": body.recipe_name,
        "rating": body.rating,
    }))
