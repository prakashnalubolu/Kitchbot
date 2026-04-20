# backend/routers/chat.py
from __future__ import annotations
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.models import ChatMessageIn, TextResponse

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

router = APIRouter(prefix="/chat", tags=["chat"])


# ── REST (full response) ──────────────────────────────────────────────────────

@router.post("/", response_model=TextResponse)
async def chat_sync(body: ChatMessageIn):
    from agents.kitchen_agent import arun_agent
    result = await arun_agent(body.message, session_id=body.session_id)
    return TextResponse(result=result)


# ── WebSocket (streaming with tool progress) ──────────────────────────────────

@router.websocket("/ws")
async def chat_stream(websocket: WebSocket):
    """
    WebSocket chat with tool-call progress + final answer streaming.

    Client sends:   {"message": "...", "session_id": "default"}
    Server yields:
      {"type": "tool_start",  "name": "..."}
      {"type": "tool_end",    "name": "...", "result": "..."}
      {"type": "token",       "text": "..."}
      {"type": "done",        "full": "..."}
      {"type": "error",       "message": "..."}
    """
    await websocket.accept()
    from agents.kitchen_agent import astream_agent

    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload    = json.loads(data)
                message    = payload.get("message", "").strip()
                session_id = payload.get("session_id", "default")
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            if not message:
                await websocket.send_json({"type": "error", "message": "Empty message"})
                continue

            async for event in astream_agent(message, session_id):
                await websocket.send_json(event)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": f"Server error: {e}"})
        except Exception:
            pass
