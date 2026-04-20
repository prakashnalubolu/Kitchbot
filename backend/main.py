# backend/main.py
# FastAPI entry point for KitchBot backend.
# Run with:  uvicorn backend.main:app --reload --port 8000
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import pantry, recipes, meal_plan, history, expiry, chat, vision

app = FastAPI(
    title="KitchBot API",
    description="Open-source meal planning assistant backend.",
    version="1.5.0",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# CORS_ORIGINS env var (comma-separated) overrides the defaults for production.
_default_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
_cors_env = os.getenv("CORS_ORIGINS", "")
_allowed_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] or _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(pantry.router)
app.include_router(recipes.router)
app.include_router(meal_plan.router)
app.include_router(history.router)
app.include_router(expiry.router)
app.include_router(chat.router)
app.include_router(vision.router)


# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "version": app.version}


# ── API index — list all routes for debugging ─────────────────────────────────
@app.get("/routes")
def list_routes():
    return [{"path": r.path, "methods": list(r.methods)} for r in app.routes]
