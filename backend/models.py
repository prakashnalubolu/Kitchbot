# backend/models.py
# Pydantic request/response models shared across routers.
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field


# ── Pantry ────────────────────────────────────────────────────────────────────

class PantryItemIn(BaseModel):
    item: str
    quantity: float
    unit: str

class PantryUpdateIn(BaseModel):
    item: str
    quantity: float
    unit: str

class PantryRemoveIn(BaseModel):
    item: str
    quantity: Optional[float] = None
    unit: str


# ── Recipes ───────────────────────────────────────────────────────────────────

class RecipeSearchIn(BaseModel):
    cuisine: Optional[str] = None
    max_time: Optional[int] = None
    diet: Optional[str] = None

class RecipeMatchIn(BaseModel):
    items: List[str]
    cuisine: Optional[str] = None
    max_time: Optional[int] = None
    diet: Optional[str] = None
    k: int = 5


# ── Meal Plan ─────────────────────────────────────────────────────────────────

class ConstraintsIn(BaseModel):
    mode: str = "pantry-preferred"
    allow_repeats: bool = False
    cuisine: Optional[str] = None
    diet: Optional[str] = None
    max_time: Optional[int] = None
    strict_meal_types: bool = False
    household_size: int = 1
    avoid_recent_days: int = 7

class AutoPlanIn(BaseModel):
    days: int = 7
    meals: List[str] = ["Breakfast", "Lunch", "Dinner"]
    continue_plan: bool = False

class UpdateSlotIn(BaseModel):
    day: str
    meal: str
    recipe_name: str
    reason: str = ""

class CookMealIn(BaseModel):
    day: Optional[str] = None
    meal: Optional[str] = None
    dish: Optional[str] = None

class SavePlanIn(BaseModel):
    file_name: Optional[str] = None


# ── History / Ratings ─────────────────────────────────────────────────────────

class RateRecipeIn(BaseModel):
    recipe_name: str
    rating: str  # "up" | "down"

class HistoryQueryIn(BaseModel):
    days: int = 30

class VarietyQueryIn(BaseModel):
    days: int = 7

class TopRecipesIn(BaseModel):
    limit: int = 10


# ── Expiry ────────────────────────────────────────────────────────────────────

class SetExpiryIn(BaseModel):
    item: str
    expires: str  # YYYY-MM-DD

class RemoveExpiryIn(BaseModel):
    item: str

class ExpiringSoonIn(BaseModel):
    within_days: int = 3


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatMessageIn(BaseModel):
    message: str
    session_id: str = "default"


# ── Vision / Receipt ─────────────────────────────────────────────────────────

class ReceiptScanResult(BaseModel):
    items: List[dict] = Field(default_factory=list)  # [{item, quantity, unit}]
    raw_text: str = ""
    confidence: str = "high"  # high | medium | low


# ── Generic response ─────────────────────────────────────────────────────────

class TextResponse(BaseModel):
    result: str
