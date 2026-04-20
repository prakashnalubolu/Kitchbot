# backend/routers/meal_plan.py
from fastapi import APIRouter
from fastapi.responses import Response
from backend.models import (
    ConstraintsIn, AutoPlanIn, UpdateSlotIn, CookMealIn,
    SavePlanIn, TextResponse,
)

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from tools.meal_plan_tools import (
    update_plan, get_shopping_list, get_constraints,
    set_constraints, auto_plan, save_plan, cook_meal,
)

router = APIRouter(prefix="/plan", tags=["meal_plan"])


@router.get("/", response_model=TextResponse)
def current_plan():
    return TextResponse(result=get_constraints.invoke({}))


@router.get("/constraints", response_model=TextResponse)
def fetch_constraints():
    return TextResponse(result=get_constraints.invoke({}))


@router.post("/constraints", response_model=TextResponse)
def update_constraints(body: ConstraintsIn):
    return TextResponse(result=set_constraints.invoke(body.model_dump()))


@router.post("/auto", response_model=TextResponse)
def run_auto_plan(body: AutoPlanIn):
    return TextResponse(result=auto_plan.invoke(body.model_dump()))


@router.post("/slot", response_model=TextResponse)
def update_slot(body: UpdateSlotIn):
    return TextResponse(result=update_plan.invoke(body.model_dump()))


@router.get("/shopping", response_model=TextResponse)
def shopping_list():
    return TextResponse(result=get_shopping_list.invoke({}))


@router.post("/cook", response_model=TextResponse)
def mark_cooked(body: CookMealIn):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    return TextResponse(result=cook_meal.invoke(payload))


@router.post("/save", response_model=TextResponse)
def export_plan(body: SavePlanIn):
    payload = {}
    if body.file_name:
        payload["file_name"] = body.file_name
    return TextResponse(result=save_plan.invoke(payload))


@router.get("/pdf")
def download_pdf():
    """Return meal plan as a downloadable PDF."""
    import json
    from tools.meal_plan_tools import memory as planner_memory

    plan = planner_memory.memories.get("plan", {})
    if not plan:
        return Response(content="No plan found.", media_type="text/plain", status_code=404)

    from tools.meal_plan_tools import get_shopping_list
    shopping_text = get_shopping_list.invoke({})

    pdf_bytes = _build_pdf(plan, shopping_text)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=kitchbot_plan.pdf"},
    )


def _build_pdf(plan: dict, shopping_text: str) -> bytes:
    from fpdf import FPDF
    import io

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "KitchBot Meal Plan", ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    for day, slots in plan.items():
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(0, 8, day, ln=True, fill=True)
        pdf.set_font("Helvetica", "", 10)
        for meal, dish in slots.items():
            pdf.cell(10)
            pdf.cell(0, 7, f"{meal}: {dish}", ln=True)
        pdf.set_font("Helvetica", "B", 11)
        pdf.ln(2)

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Shopping List", ln=True)
    pdf.set_font("Helvetica", "", 10)
    for line in shopping_text.splitlines():
        pdf.multi_cell(0, 7, line)

    return bytes(pdf.output())
