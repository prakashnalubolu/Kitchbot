# backend/routers/pantry.py
from fastapi import APIRouter
from backend.models import PantryItemIn, PantryRemoveIn, PantryUpdateIn, TextResponse

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from tools.pantry_tools import add_to_pantry, remove_from_pantry, update_pantry, list_pantry

router = APIRouter(prefix="/pantry", tags=["pantry"])


@router.get("/", response_model=TextResponse)
def get_pantry():
    return TextResponse(result=list_pantry.invoke({}))


@router.post("/add", response_model=TextResponse)
def add_item(body: PantryItemIn):
    return TextResponse(result=add_to_pantry.invoke({
        "item": body.item,
        "quantity": body.quantity,
        "unit": body.unit,
    }))


@router.post("/remove", response_model=TextResponse)
def remove_item(body: PantryRemoveIn):
    return TextResponse(result=remove_from_pantry.invoke({
        "item": body.item,
        "quantity": body.quantity,
        "unit": body.unit,
    }))


@router.post("/update", response_model=TextResponse)
def update_item(body: PantryUpdateIn):
    return TextResponse(result=update_pantry.invoke({
        "item": body.item,
        "quantity": body.quantity,
        "unit": body.unit,
    }))
