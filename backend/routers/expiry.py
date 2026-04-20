# backend/routers/expiry.py
from fastapi import APIRouter
from backend.models import SetExpiryIn, RemoveExpiryIn, TextResponse

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from tools.expiry_tools import set_expiry, remove_expiry, get_expiring_soon

router = APIRouter(prefix="/expiry", tags=["expiry"])


@router.get("/", response_model=TextResponse)
def expiring_soon(within_days: int = 3):
    return TextResponse(result=get_expiring_soon.invoke({"within_days": within_days}))


@router.post("/", response_model=TextResponse)
def set_item_expiry(body: SetExpiryIn):
    return TextResponse(result=set_expiry.invoke({
        "item": body.item,
        "expires": body.expires,
    }))


@router.delete("/{item}", response_model=TextResponse)
def delete_expiry(item: str):
    return TextResponse(result=remove_expiry.invoke({"item": item}))
