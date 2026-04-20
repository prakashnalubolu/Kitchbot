# agents/kitchen_agent.py
# LCEL-based agent — replaces legacy AgentExecutor.
#
# Architecture:
#   LLM.bind_tools(TOOLS) → async tool-call loop → final answer
#   History: InMemoryChatMessageHistory per session_id
#   Streaming: astream_agent() yields progress events + final tokens
from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator, AsyncIterator

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage, HumanMessage, SystemMessage, ToolMessage, BaseMessage,
)
from langchain_core.chat_history import InMemoryChatMessageHistory

load_dotenv()

# ── Tools ─────────────────────────────────────────────────────────────────────

from tools.pantry_tools import (
    list_pantry, add_to_pantry, remove_from_pantry, update_pantry,
)
from tools.cuisine_tools import find_recipes_by_items, list_recipes, get_recipe
from tools.manager_tools import missing_ingredients, suggest_substitutions
from tools.meal_plan_tools import (
    update_plan, get_shopping_list, get_constraints,
    set_constraints, auto_plan, save_plan, cook_meal,
)
from tools.history_tools import (
    get_cook_history, suggest_variety, rate_recipe,
    get_top_recipes, get_impact_stats,
)
from tools.expiry_tools import set_expiry, remove_expiry, get_expiring_soon

TOOLS = [
    list_pantry, add_to_pantry, remove_from_pantry, update_pantry,
    find_recipes_by_items, list_recipes, get_recipe,
    missing_ingredients, suggest_substitutions,
    update_plan, get_shopping_list, get_constraints, set_constraints,
    auto_plan, save_plan, cook_meal,
    get_cook_history, suggest_variety, rate_recipe, get_top_recipes, get_impact_stats,
    set_expiry, remove_expiry, get_expiring_soon,
]

TOOLS_BY_NAME: dict[str, object] = {t.name: t for t in TOOLS}

# ── LLM ───────────────────────────────────────────────────────────────────────

def _build_llm():
    """
    Build the LLM with tool calling support.
    Resolution: LLM_PROVIDER=ollama (default) → qwen3:8b via Ollama
                LLM_PROVIDER=openai           → gpt-4o-mini via OpenAI

    Ollama setup:
      ollama pull qwen3:8b          # best tool calling, 5.2 GB
      ollama pull qwen2.5vl:7b      # vision/OCR for receipts, 5.1 GB
    """
    provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
            model    = os.getenv("OLLAMA_MODEL", "qwen3:8b")
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            llm = ChatOllama(model=model, temperature=0.2, base_url=base_url, num_predict=2048)
            print(f"[KitchBot] LLM: Ollama {model} @ {base_url}")
            return llm
        except Exception as e:
            print(f"[KitchBot] Ollama unavailable ({e}), falling back to OpenAI")

    from langchain_openai import ChatOpenAI
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    print(f"[KitchBot] LLM: OpenAI {model}")
    return ChatOpenAI(model=model, temperature=0.2, api_key=os.getenv("OPENAI_API_KEY"))


_llm_instance = None

def get_llm():
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = _build_llm()
    return _llm_instance


def get_llm_with_tools():
    return get_llm().bind_tools(TOOLS)


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are **KitchBot** — a friendly home-cooking assistant. You manage pantries, find recipes, plan meals, build shopping lists, track cooking history, and help reduce food waste. You ONLY answer from tool results — never from general knowledge for factual queries about pantry, recipes, or plans.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 1 — GROUND RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
R1. LOOP GUARD — If you already have a tool result for a given tool+input, do NOT call it again.
R2. CRUD STOP RULE — For add/remove/update pantry: ONE tool call per item, then respond.
R3. Never invent recipe names, ingredient names, quantities, or plan data.
R4. After add/remove/update pantry: confirm and STOP. No follow-up tool calls.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2 — TOOL SCHEMAS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• add_to_pantry:         {{"item":"<singular lowercase>","quantity":<number>,"unit":"count|g|ml"}}
• remove_from_pantry:    {{"item":"<singular lowercase>","quantity":<number>,"unit":"count|g|ml"}}
• update_pantry:         {{"item":"<singular lowercase>","quantity":<number>,"unit":"count|g|ml"}}
• list_pantry:           {{}}
• get_recipe:            "<Dish Name>"
• list_recipes:          {{"cuisine":<str|null>,"max_time":<int|null>,"diet":<"veg"|"eggtarian"|"non-veg"|null>}}
• find_recipes_by_items: {{"items":[str],"cuisine":<str|null>,"max_time":<int|null>,"diet":<str|null>,"k":<int>}}
• missing_ingredients:   "<Dish Name>"
• suggest_substitutions: {{"dish":"...","deficits":[...],"pantry":[...],"constraints":{{}}}}
• update_plan:           {{"day":"Day1","meal":"Breakfast|Lunch|Dinner","recipe_name":"<Dish>","reason":"<why>"}}
• get_shopping_list:     {{}}
• save_plan:             {{"file_name":"<name>"}} or {{}}
• cook_meal:             {{"day":"...","meal":"..."}} OR {{"dish":"..."}}
• set_constraints:       {{"mode":"pantry-preferred"|"pantry-first-strict"|"freeform","allow_repeats":<bool>,"cuisine":<str|null>,"diet":<str|null>,"max_time":<int|null>,"strict_meal_types":<bool>,"household_size":<int>,"avoid_recent_days":<int>}}
• get_constraints:       {{}}
• auto_plan:             {{"days":<int>,"meals":["Breakfast","Lunch","Dinner"],"continue_plan":<bool>}}
• rate_recipe:           {{"recipe_name":"<Dish>","rating":"up"|"down"}}
• get_cook_history:      {{"days":<int>}}
• suggest_variety:       {{"days":<int>}}
• get_top_recipes:       {{"limit":<int>}}
• get_impact_stats:      {{}}
• set_expiry:            {{"item":"<ingredient>","expires":"YYYY-MM-DD"}}
• remove_expiry:         {{"item":"<ingredient>"}}
• get_expiring_soon:     {{"within_days":<int>}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 3 — INTENT ROUTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 USER SAYS                                           → GO TO
 ─────────────────────────────────────────────────────────────
 "hi", "hello", "what can you do", "help"           → §4  (Greeting)
 add/remove/update/set/how much/do I have …         → §5  (Pantry CRUD)
 show pantry / list what I have                     → §5  (list_pantry)
 recipe for X / how do I make X / steps for X       → §6A (Single recipe)
 show me [cuisine] recipes / list veg recipes       → §6B (Browse recipes)
 what can I cook / what can I make with my pantry   → §6C (Pantry-match)
 can I cook X / do I have everything for X          → §6D (Feasibility)
 substitute for X / I don't have X                  → §6E (Substitutions)
 plan meals / make a plan / weekly plan             → §7  (Meal planning)
 shopping list / what do I need to buy              → §8  (Shopping list)
 I cooked X / mark X as cooked                     → §9  (Mark cooked)
 save plan / export plan                            → §10 (Export)
 rate this / thumbs up / thumbs down / liked it    → §14 (Rate recipe)
 what have I cooked / cook history                 → §15 (Cook history)
 suggest something different / variety             → §15 (Variety)
 what's expiring / expiry / about to go bad        → §16 (Expiry)
 food waste / impact stats / how much saved        → §17 (Impact stats)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 4 — GREETING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
No tool calls. Reply warmly. Mention: pantry management, 200+ recipes, meal planning, shopping list, cook history, expiry alerts, food waste impact.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 5 — PANTRY CRUD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
One tool call → respond. No additional calls after a pantry mutation.
Normalize: kg→g (×1000), l→ml (×1000). Singularize. Lowercase.
Dispatch: add/remove/update/list.
Confirm (e.g. "✅ Added 3 eggs."). STOP.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 6 — RECIPES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
6A — get_recipe | 6B — list_recipes | 6C — list_pantry → find_recipes_by_items
6D — missing_ingredients | 6E — suggest_substitutions

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 7 — MEAL PLANNING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 1: set_constraints (only if changed). Step 2: auto_plan. Step 3: STOP.
Default mode: pantry-preferred. Planner auto-avoids recently cooked dishes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 8-17 — REMAINING FLOWS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
§8  Shopping: get_shopping_list. Quantities scaled for household size.
§9  Cook: cook_meal → confirm → invite rating.
§10 Export: save_plan.
§13 Unit math: answer directly, no tools.
§14 Ratings: rate_recipe("name","up"|"down"). get_top_recipes for top list.
§15 History: get_cook_history / suggest_variety.
§16 Expiry: set_expiry / get_expiring_soon / remove_expiry.
§17 Impact: get_impact_stats. Celebrate the environmental contribution.

TONE: Warm, brief, plain language. Lead with the answer. No jargon.
ERROR: Tool error → retry once. Not found → say so. Never invent.
"""

# ── Session history store ─────────────────────────────────────────────────────

_sessions: dict[str, InMemoryChatMessageHistory] = {}


def _get_history(session_id: str) -> InMemoryChatMessageHistory:
    if session_id not in _sessions:
        _sessions[session_id] = InMemoryChatMessageHistory()
    return _sessions[session_id]


def clear_history(session_id: str = "default") -> None:
    _sessions.pop(session_id, None)


# ── Core async agent loop ─────────────────────────────────────────────────────

async def _run_agent_loop(
    messages: list[BaseMessage],
    max_iterations: int = 12,
) -> str:
    """
    Execute the agent loop: LLM → tool calls → LLM → ... → final answer.
    Returns the final text response.
    """
    llm_with_tools = get_llm_with_tools()

    for _ in range(max_iterations):
        response: AIMessage = await llm_with_tools.ainvoke(messages)

        if not response.tool_calls:
            return response.content or ""

        messages = list(messages) + [response]
        for tc in response.tool_calls:
            tool = TOOLS_BY_NAME.get(tc["name"])
            try:
                result = await asyncio.get_running_loop().run_in_executor(
                    None, lambda t=tool, a=tc["args"]: t.invoke(a) if t else f"Unknown tool: {tc['name']}"
                )
            except Exception as e:
                result = f"Tool error: {e}"
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    return "I hit the step limit. Please try a more specific request."


async def arun_agent(message: str, session_id: str = "default") -> str:
    """Run the agent and return the full response string."""
    from tools.guardrails import validate_input, validate_output, rate_limiter

    rate_check = rate_limiter.check()
    if not rate_check:
        return rate_check.reason

    input_check = validate_input(message)
    if not input_check:
        return input_check.reason

    history = _get_history(session_id)
    messages = (
        [SystemMessage(content=SYSTEM_PROMPT)]
        + list(history.messages)
        + [HumanMessage(content=message)]
    )

    raw = await _run_agent_loop(messages)

    output_check = validate_output(raw)
    if output_check:
        safe = output_check.reason if output_check.reason else raw  # reason = truncated text
    else:
        safe = output_check.reason or "I encountered an issue. Please try again."

    history.add_user_message(message)
    history.add_ai_message(safe)
    return safe


async def astream_agent(
    message: str,
    session_id: str = "default",
) -> AsyncGenerator[dict, None]:
    """
    Async generator that yields progress events for the WebSocket.

    Event types:
      {"type": "tool_start",  "name": "<tool name>"}   — tool is being called
      {"type": "tool_end",    "name": "<tool name>", "result": "<summary>"}
      {"type": "token",       "text": "<token>"}        — final answer tokens
      {"type": "done",        "full": "<full answer>"}
      {"type": "error",       "message": "<reason>"}
    """
    from tools.guardrails import validate_input, validate_output, rate_limiter

    rate_check = rate_limiter.check()
    if not rate_check:
        yield {"type": "error", "message": rate_check.reason}
        return

    input_check = validate_input(message)
    if not input_check:
        yield {"type": "error", "message": input_check.reason}
        return

    history = _get_history(session_id)
    messages: list[BaseMessage] = (
        [SystemMessage(content=SYSTEM_PROMPT)]
        + list(history.messages)
        + [HumanMessage(content=message)]
    )

    llm_with_tools = get_llm_with_tools()
    full_response = ""

    try:
        for _ in range(12):
            response: AIMessage = await llm_with_tools.ainvoke(messages)

            if not response.tool_calls:
                # Stream the final answer word by word
                text = response.content or ""
                full_response = text
                for word in text.split(" "):
                    yield {"type": "token", "text": word + " "}
                    await asyncio.sleep(0)
                break

            # Notify client which tools are being called
            messages = list(messages) + [response]
            for tc in response.tool_calls:
                yield {"type": "tool_start", "name": tc["name"]}
                tool = TOOLS_BY_NAME.get(tc["name"])
                try:
                    result = await asyncio.get_running_loop().run_in_executor(
                        None,
                        lambda t=tool, a=tc["args"]: t.invoke(a) if t else f"Unknown tool: {tc['name']}"
                    )
                except Exception as e:
                    result = f"Tool error: {e}"
                yield {"type": "tool_end", "name": tc["name"],
                       "result": str(result)[:120] + ("…" if len(str(result)) > 120 else "")}
                messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

        output_check = validate_output(full_response)
        if output_check:
            safe = output_check.reason if output_check.reason else full_response
        else:
            safe = output_check.reason or "I encountered an issue. Please try again."

        history.add_user_message(message)
        history.add_ai_message(safe)
        yield {"type": "done", "full": safe}

    except Exception as e:
        yield {"type": "error", "message": f"Agent error: {e}"}


# ── Sync wrapper (for tests / scripts) ───────────────────────────────────────

def chat(message: str, session_id: str = "default") -> str:
    """Synchronous wrapper around arun_agent for tests and scripts."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, arun_agent(message, session_id))
                return future.result()
        return loop.run_until_complete(arun_agent(message, session_id))
    except RuntimeError:
        return asyncio.run(arun_agent(message, session_id))
