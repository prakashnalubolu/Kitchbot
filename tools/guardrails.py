# tools/guardrails.py
"""
Input/output safety layer for KitchBot.

Responsibilities:
  - Block off-topic or potentially harmful user inputs
  - Detect prompt-injection attempts
  - Prevent API key / system-prompt leakage in responses
  - Enforce a simple per-session rate limit
"""
from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional


# ── Constants ─────────────────────────────────────────────────────────────────

# Phrases that suggest the user is trying to jailbreak / hijack the agent.
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"forget\s+(everything|all\s+previous)", re.I),
    re.compile(r"you\s+are\s+now\s+(a\s+)?(different|new|another|unrestricted)", re.I),
    re.compile(r"act\s+as\s+(if\s+you\s+are|a)\s+(?!chef|kitchen|cook)", re.I),
    re.compile(r"pretend\s+you\s+(are|have\s+no)\s+restrictions?", re.I),
    re.compile(r"system\s*prompt", re.I),
    re.compile(r"reveal\s+(your\s+)?(instructions?|prompt|secret)", re.I),
    re.compile(r"print\s+(your\s+)?(system\s+prompt|instructions)", re.I),
    re.compile(r"what\s+(are\s+your|is\s+your)\s+(system\s+prompt|instructions?)", re.I),
    re.compile(r"jailbreak", re.I),
    re.compile(r"DAN\s*mode", re.I),
]

# Topics that are clearly outside cooking / food.
_OFF_TOPIC_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(write|generate|create)\s+(a\s+)?code\b", re.I),
    re.compile(r"\b(hack|exploit|malware|virus|payload|sql\s*injection)\b", re.I),
    re.compile(r"\b(sex|porn|adult\s+content|nsfw)\b", re.I),
    re.compile(r"\b(political|politics|election|president|government)\b", re.I),
    re.compile(r"\b(stock\s+(market|tips?)|cryptocurrency|bitcoin|nft)\b", re.I),
    re.compile(r"\b(write\s+(an?\s+)?essay|homework)\b", re.I),
    re.compile(r"\b(translate\s+this\s+paragraph)\b", re.I),
    re.compile(r"\b(medical\s+diagnosis|diagnose\s+me|am\s+i\s+sick)\b", re.I),
    re.compile(r"\b(legal\s+advice|is\s+it\s+legal)\b", re.I),
]

# Patterns that look like sensitive data the model should never echo back.
_LEAKAGE_PATTERNS: list[re.Pattern] = [
    re.compile(r"sk-[A-Za-z0-9\-_]{20,}", re.I),        # OpenAI keys
    re.compile(r"OPENAI_API_KEY\s*=", re.I),
    re.compile(r"Bearer\s+[A-Za-z0-9\-_.~+/]+=*", re.I),  # Auth tokens
]

# Hard length limits.
MAX_INPUT_CHARS = 2000
MAX_OUTPUT_CHARS = 8000

# Rate limit: at most N messages per WINDOW_SECONDS.
RATE_LIMIT_N = 20
RATE_WINDOW_SECONDS = 60


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class GuardResult:
    allowed: bool
    reason: Optional[str] = None          # human-facing message on block
    category: Optional[str] = None        # "injection" | "off_topic" | "length" | "rate_limit"

    def __bool__(self) -> bool:
        return self.allowed


@dataclass
class RateLimiter:
    """Sliding-window rate limiter (in-memory, single-session)."""
    n: int = RATE_LIMIT_N
    window: float = RATE_WINDOW_SECONDS
    _timestamps: Deque[float] = field(default_factory=deque)

    def check(self) -> GuardResult:
        now = time.monotonic()
        # Evict old timestamps outside the window.
        while self._timestamps and now - self._timestamps[0] > self.window:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.n:
            return GuardResult(
                allowed=False,
                reason=f"Slow down! You've sent {self.n} messages in the last {int(self.window)}s. Please wait a moment.",
                category="rate_limit",
            )
        self._timestamps.append(now)
        return GuardResult(allowed=True)

    def reset(self) -> None:
        self._timestamps.clear()


# ── Validators ────────────────────────────────────────────────────────────────

def validate_input(message: str) -> GuardResult:
    """
    Check a user message before it reaches the agent.
    Returns GuardResult(allowed=True) if safe, or GuardResult(allowed=False) with a
    human-readable reason.
    """
    if not isinstance(message, str):
        return GuardResult(False, "Invalid input type.", "validation")

    msg = message.strip()

    if not msg:
        return GuardResult(False, "Please type a message.", "empty")

    if len(msg) > MAX_INPUT_CHARS:
        return GuardResult(
            False,
            f"Your message is too long ({len(msg)} chars). Please keep it under {MAX_INPUT_CHARS} characters.",
            "length",
        )

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(msg):
            return GuardResult(
                False,
                "I'm KitchBot — a cooking assistant. I can't help with that kind of request.",
                "injection",
            )

    for pattern in _OFF_TOPIC_PATTERNS:
        if pattern.search(msg):
            return GuardResult(
                False,
                "I'm only set up to help with cooking, pantry management, and meal planning. Try asking me about recipes or ingredients!",
                "off_topic",
            )

    return GuardResult(allowed=True)


def validate_output(response: str) -> GuardResult:
    """
    Scrub agent output before it is shown to the user.
    Returns GuardResult(allowed=True) with cleaned text in .reason if no issue,
    or GuardResult(allowed=False) if the output should be replaced entirely.
    """
    if not isinstance(response, str):
        return GuardResult(False, "Internal error — empty response.", "type_error")

    for pattern in _LEAKAGE_PATTERNS:
        if pattern.search(response):
            return GuardResult(
                False,
                "I encountered an internal issue. Please try again.",
                "leakage",
            )

    if len(response) > MAX_OUTPUT_CHARS:
        # Truncate gracefully rather than block.
        truncated = response[:MAX_OUTPUT_CHARS] + "\n\n*(Response truncated — ask me to continue if needed.)*"
        return GuardResult(allowed=True, reason=truncated)

    return GuardResult(allowed=True)


# Module-level rate limiter instance shared across the session.
rate_limiter = RateLimiter()
