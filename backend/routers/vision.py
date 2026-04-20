# backend/routers/vision.py
# Receipt / slip scanning — upload image or PDF, get pantry items back.
# Uses qwen2.5vl:7b via Ollama (open-source, local) with GPT-4o fallback.
from __future__ import annotations

import base64
import json
import os
import re
import sys
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException
from backend.models import ReceiptScanResult

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

router = APIRouter(prefix="/vision", tags=["vision"])

_RECEIPT_PROMPT = """
You are a receipt parser. Extract all food/grocery items from this receipt image.

Return ONLY a JSON object in this exact format — no explanation, no markdown:
{
  "items": [
    {"item": "<lowercase singular item name>", "quantity": <number>, "unit": "<count|g|ml|kg|l|pack>"},
    ...
  ],
  "confidence": "<high|medium|low>"
}

Rules:
- Only include food/grocery items. Skip non-food like cleaning supplies, electronics.
- Normalize units: oz → g (×28.35), lb → g (×453.6), fl oz → ml (×29.57)
- If quantity is unclear, use 1 count.
- Item names: singular, lowercase. "eggs" → "egg", "tomatoes" → "tomato"
- If you cannot read the receipt clearly, set confidence to "low".
"""


def _image_to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def _parse_llm_json(text: str) -> dict:
    """Extract JSON from LLM response even if it has extra text."""
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find first {...} block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"items": [], "confidence": "low"}


def _scan_with_ollama(image_b64: str, mime: str) -> dict:
    import httpx
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_VISION_MODEL", "qwen2.5vl:7b")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": _RECEIPT_PROMPT,
                "images": [image_b64],
            }
        ],
        "stream": False,
        "options": {"temperature": 0},
    }

    resp = httpx.post(f"{base_url}/api/chat", json=payload, timeout=60)
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    return _parse_llm_json(content)


def _scan_with_openai(image_b64: str, mime: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _RECEIPT_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                    },
                ],
            }
        ],
        max_tokens=1024,
        temperature=0,
    )
    return _parse_llm_json(resp.choices[0].message.content)


def _pdf_to_image_b64(pdf_bytes: bytes) -> str:
    """Convert first page of PDF to a base64 PNG for vision model."""
    try:
        import fitz  # pymupdf
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        mat = fitz.Matrix(2, 2)  # 2x zoom for better OCR
        pix = page.get_pixmap(matrix=mat)
        return base64.b64encode(pix.tobytes("png")).decode("utf-8")
    except ImportError:
        raise HTTPException(
            status_code=422,
            detail="PDF support requires pymupdf. Run: pip install pymupdf",
        )


@router.post("/receipt", response_model=ReceiptScanResult)
async def scan_receipt(file: UploadFile = File(...)):
    """
    Upload a receipt image (JPG/PNG) or PDF.
    Returns parsed grocery items ready to add to pantry.
    """
    content_type = file.content_type or ""
    data = await file.read()

    if len(data) > 10 * 1024 * 1024:  # 10 MB hard limit
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")

    if content_type == "application/pdf" or file.filename.endswith(".pdf"):
        image_b64 = _pdf_to_image_b64(data)
        mime = "image/png"
    elif content_type.startswith("image/"):
        image_b64 = _image_to_base64(data)
        mime = content_type
    else:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Upload a JPG, PNG, or PDF.",
        )

    provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
    try:
        if provider == "ollama":
            parsed = _scan_with_ollama(image_b64, mime)
        else:
            parsed = _scan_with_openai(image_b64, mime)
    except Exception:
        # Fallback to OpenAI if Ollama fails
        try:
            parsed = _scan_with_openai(image_b64, mime)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Vision model error: {e}")

    return ReceiptScanResult(
        items=parsed.get("items", []),
        confidence=parsed.get("confidence", "medium"),
    )


@router.post("/receipt/apply", response_model=dict)
async def scan_and_apply(file: UploadFile = File(...)):
    """
    Scan receipt AND automatically add all items to pantry.
    Returns list of added items + any failures.
    """
    scan_result = await scan_receipt(file)

    from tools.pantry_tools import add_to_pantry

    added = []
    failed = []
    for entry in scan_result.items:
        try:
            result = add_to_pantry.invoke({
                "item": entry["item"],
                "quantity": entry["quantity"],
                "unit": entry["unit"],
            })
            added.append({**entry, "result": result})
        except Exception as e:
            failed.append({**entry, "error": str(e)})

    return {
        "scanned": len(scan_result.items),
        "added": added,
        "failed": failed,
        "confidence": scan_result.confidence,
    }
