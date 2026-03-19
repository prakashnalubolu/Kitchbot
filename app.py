# Run with:  streamlit run app.py
from __future__ import annotations
import os, json, re, datetime
from typing import Any, Dict, List, Tuple
import pandas as pd
import streamlit as st

from tools.meal_plan_tools import DEFAULT_CONSTRAINTS as PLANNER_DEFAULTS
from agents.kitchen_agent import chat as kitchen_chat
from tools.meal_plan_tools import (
    memory as planner_memory,
    update_plan, cook_meal,
    get_shopping_list, save_plan,
)
from tools.pantry_tools import (
    add_to_pantry as _tool_add,
    remove_from_pantry as _tool_remove,
    update_pantry as _tool_update,
)

if "constraints" not in planner_memory.memories:
    planner_memory.memories["constraints"] = dict(PLANNER_DEFAULTS)

try:
    from tools.manager_tools import memory as slot_memory
except Exception:
    slot_memory = None

from tools.cuisine_tools import _load as cuisine_load
from tools.cuisine_tools import diet_ok as cuisine_diet_ok

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="KitchBot — Your Smart Kitchen Assistant",
    page_icon="🍳",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────────────────────
# Design system — amber palette
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base ── */
[data-testid="stAppViewContainer"] { background: #FAFAF9; }
[data-testid="stHeader"] { background: transparent; border-bottom: none; }
section[data-testid="stSidebar"] { display: none !important; }
.block-container { padding-top: 0 !important; max-width: 1200px !important; }

/* ── Brand header ── */
.kb-brand {
    display: flex; align-items: center; gap: 12px;
    padding: 20px 0 14px 0;
    border-bottom: 2px solid #F59E0B;
    margin-bottom: 6px;
}
.kb-brand .logo { font-size: 30px; line-height: 1; }
.kb-brand .name { font-size: 24px; font-weight: 800; color: #111827; letter-spacing: -0.5px; }
.kb-brand .dot  { color: #F59E0B; }
.kb-brand .tag  { font-size: 13px; color: #9CA3AF; font-weight: 400; margin-left: 2px; }

/* ── Tabs ── */
[data-testid="stTabs"] > div:first-child { gap: 0; border-bottom: 2px solid #E5E7EB; }
button[data-baseweb="tab"] {
    font-size: 14px !important; font-weight: 600 !important;
    padding: 12px 24px !important; color: #6B7280 !important;
    border-radius: 0 !important; border-bottom: 3px solid transparent !important;
    background: transparent !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #D97706 !important;
    border-bottom: 3px solid #F59E0B !important;
}
button[data-baseweb="tab"]:hover { color: #D97706 !important; background: #FFFBEB !important; }

/* ── Cards ── */
.kb-card {
    background: white; border-radius: 12px; padding: 20px 22px;
    border: 1px solid #E5E7EB; margin-bottom: 16px;
}
.kb-card-title {
    font-size: 11px; font-weight: 700; color: #9CA3AF;
    text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 14px;
}

/* ── Primary button ── */
.stButton > button[kind="primary"] {
    background: #F59E0B !important; color: white !important;
    border: none !important; border-radius: 8px !important;
    font-weight: 600 !important; font-size: 14px !important;
}
.stButton > button[kind="primary"]:hover { background: #D97706 !important; }
.stButton > button[kind="secondary"] {
    border: 1px solid #E5E7EB !important; border-radius: 8px !important;
    background: white !important;
}
.stButton > button[kind="secondary"]:hover { border-color: #F59E0B !important; color: #D97706 !important; }

/* ── Plan grid ── */
.plan-day-label {
    font-size: 12px; font-weight: 700; color: #374151;
    text-transform: uppercase; letter-spacing: 0.6px;
    padding: 8px 4px 6px 4px; text-align: center;
    border-bottom: 2px solid #FDE68A; margin-bottom: 8px;
}
.plan-day-date { font-size: 11px; color: #9CA3AF; font-weight: 400; display: block; }
.meal-label {
    font-size: 11px; font-weight: 700; color: #9CA3AF;
    text-transform: uppercase; letter-spacing: 0.5px;
    margin-bottom: 3px; padding-left: 2px;
}
.meal-chip-filled {
    background: #FFFBEB; border: 1px solid #FDE68A;
    border-radius: 8px; padding: 8px 10px;
    font-size: 13px; color: #92400E; font-weight: 500;
    text-align: center; min-height: 42px;
    display: flex; align-items: center; justify-content: center;
}
.meal-chip-empty {
    background: #F9FAFB; border: 1.5px dashed #E5E7EB;
    border-radius: 8px; padding: 8px 10px;
    font-size: 12px; color: #D1D5DB; text-align: center;
    min-height: 42px; display: flex; align-items: center; justify-content: center;
}

/* ── Mode badge ── */
.mode-badge {
    display: inline-flex; align-items: center; gap: 5px;
    background: #FEF3C7; color: #92400E;
    border: 1px solid #FDE68A; border-radius: 20px;
    padding: 3px 12px; font-size: 12px; font-weight: 600;
}
.mode-badge-free {
    background: #ECFDF5; color: #065F46;
    border-color: #A7F3D0;
}

/* ── Shopping list ── */
.sl-section {
    font-size: 10px; font-weight: 700; letter-spacing: 1px;
    text-transform: uppercase; color: #9CA3AF;
    padding: 10px 0 4px 0; margin-top: 4px;
    border-top: 1px solid #F3F4F6;
}
.sl-empty {
    background: #F0FDF4; border: 1px solid #BBF7D0;
    border-radius: 10px; padding: 16px;
    color: #166534; font-size: 14px; text-align: center;
}

/* ── Pantry table ── */
[data-testid="stDataFrame"] { border-radius: 10px !important; overflow: hidden !important; }

/* ── Empty state ── */
.empty-state {
    text-align: center; padding: 50px 20px;
}
.empty-state .es-icon { font-size: 48px; margin-bottom: 12px; }
.empty-state .es-title { font-size: 18px; font-weight: 700; color: #374151; margin-bottom: 6px; }
.empty-state .es-desc { font-size: 14px; color: #9CA3AF; line-height: 1.6; }

/* ── Suggestion chips ── */
.chips-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; justify-content: center; }
.chip {
    background: #FEF3C7; color: #92400E;
    border: 1px solid #FDE68A; border-radius: 20px;
    padding: 6px 14px; font-size: 13px; font-weight: 500;
    cursor: pointer; white-space: nowrap;
}

/* ── Chat input focus ── */
[data-testid="stChatInput"] textarea {
    border-radius: 12px !important;
}

/* ── Input elements ── */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
    border-radius: 8px !important;
}

/* ── Success / info toast style ── */
[data-testid="stAlert"] { border-radius: 10px !important; }

/* ── Divider ── */
hr { border-color: #F3F4F6 !important; margin: 16px 0 !important; }

/* ── Expander ── */
[data-testid="stExpander"] {
    border: 1px solid #E5E7EB !important;
    border-radius: 10px !important;
    background: white !important;
}
details summary { font-weight: 600 !important; color: #374151 !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────
ss = st.session_state
ss.setdefault("messages_kitchen", [])
ss.setdefault("events", [])
ss.setdefault("focus_msg_idx", None)
ss.setdefault("start_date", datetime.date.today())
ss.setdefault("cuisine_autofocus", "")
ss.setdefault("show_shopping_list", False)
ss.setdefault("pantry_filter", "")
ss.setdefault("active_tab", 0)

# ─────────────────────────────────────────────────────────────────────────────
# Paths & helpers
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.abspath(os.path.dirname(__file__))
DATA_DIR    = os.path.join(BASE_DIR, "data")
PANTRY_PATH = os.path.join(DATA_DIR, "pantry.json")
KEY_RE      = re.compile(r"^\s*([^(]+?)\s*\(([^)]+)\)\s*$")

def _load_json_ok(path: str) -> Tuple[bool, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return True, json.load(f)
    except FileNotFoundError:
        return False, f"Missing: {os.path.relpath(path, BASE_DIR)}"
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON · {e}"

ALT_UNITS_PATH = os.path.join(DATA_DIR, "alt_units.json")

def _load_alt_hints() -> dict:
    try:
        with open(ALT_UNITS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception:
        data = {}
    rules  = data.get("rules", []) or []
    labels = data.get("labels", {}) or {}
    hints: Dict[str, Dict[str, Any]] = {}
    base_count_aliases = ["count", "pc", "pcs", "piece", "pieces"]
    for r in rules:
        item   = str(r.get("item","")).strip().lower()
        fr     = str(r.get("from","")).strip().lower()
        to     = str(r.get("to","")).strip().lower()
        factor = r.get("factor", None)
        if not item or fr != "count" or factor is None:
            continue
        h = hints.setdefault(item, {"count_to_g": None, "count_to_ml": None,
                                     "count_aliases": list(base_count_aliases)})
        if to == "g":   h["count_to_g"]  = float(factor)
        elif to == "ml": h["count_to_ml"] = float(factor)
        lbl = (labels.get(item) or {}).get("count_label")
        if lbl:
            lbl = str(lbl).strip().lower()
            if lbl and lbl not in h["count_aliases"]:
                h["count_aliases"].append(lbl)
    return hints

ALT_HINTS = _load_alt_hints()

def _pretty_quantity(item: str, unit: str, qty: Any) -> str:
    try:    q = float(qty)
    except: return f"{qty} {unit}"
    name = (item or "").strip().lower()
    u    = (unit or "").strip().lower()
    h    = ALT_HINTS.get(name)
    def _fmt(x: float, suffix: str) -> str:
        return f"{int(x)} {suffix}" if abs(x - int(x)) < 1e-9 else f"{x:g} {suffix}"
    if not h: return _fmt(q, u)
    if u == "g" and h.get("count_to_g"):
        approx = q / float(h["count_to_g"])
        label  = (h.get("count_aliases") or ["count"])[-1]
        return f"{_fmt(q, 'g')} (~{_fmt(round(approx), label)})"
    if u == "ml" and h.get("count_to_ml"):
        approx = q / float(h["count_to_ml"])
        label  = (h.get("count_aliases") or ["count"])[-1]
        return f"{_fmt(q, 'ml')} (~{_fmt(round(approx), label)})"
    if h and u in (h.get("count_aliases") or []):
        if h.get("count_to_g"):  return f"{_fmt(q, u)} (~{_fmt(q * float(h['count_to_g']), 'g')})"
        if h.get("count_to_ml"): return f"{_fmt(q, u)} (~{_fmt(q * float(h['count_to_ml']), 'ml')})"
    return _fmt(q, u)

def _parse_pantry_rows(d: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for k, v in sorted((d or {}).items(), key=lambda kv: kv[0].lower()):
        m = KEY_RE.match(k)
        item = m.group(1).strip().lower() if m else k.strip().lower()
        unit = m.group(2).strip().lower() if m else "count"
        try:    qty = int(v)
        except:
            try:    qty = float(v)
            except: qty = v
        rows.append({"item": item, "unit": unit, "quantity": qty})
    for i, r in enumerate(rows, 1):
        r["#"] = i
    return [{"#": r["#"], "Item": r["item"], "Unit": r["unit"],
             "Quantity": _pretty_quantity(r["item"], r["unit"], r["quantity"])} for r in rows]

def _fmt_recipe_md(r: dict) -> str:
    name  = str(r.get("name","")).title()
    cuisine = (r.get("cuisine","") or "").title()
    prep  = int(r.get("prep_time_min", 0))
    cook  = int(r.get("cook_time_min", 0))
    ings  = r.get("ingredients", [])
    steps = r.get("steps", [])
    ing_lines = [
        f"- {i.get('quantity')} {i.get('unit')} {i.get('item')}"
        if (i.get("unit") and i.get("unit") != "count")
        else f"- {i.get('quantity')} × {i.get('item')}"
        for i in ings
    ]
    step_lines = [f"{i+1}. {s}" for i, s in enumerate(steps)]
    return "\n".join([
        f"**{name}** · {cuisine} — ⏱ {prep + cook} min",
        "", "**Ingredients:**", *ing_lines,
        "", "**Steps:**", *step_lines,
    ])

def _render_shopping_list() -> None:
    deficits = planner_memory.memories.get("shopping_list") or []
    if not deficits:
        st.markdown('<div class="sl-empty">✅ Your pantry covers everything in the plan!</div>',
                    unsafe_allow_html=True)
        return
    dairy_set  = {"milk","cream","yogurt","paneer","cheese","butter","ghee","egg","eggs"}
    meat_set   = {"chicken","mutton","lamb","beef","pork","fish","prawn","shrimp","crab"}
    veggie_set = {"spinach","tomato","onion","garlic","ginger","chili","pepper","potato",
                  "carrot","peas","capsicum","coriander","lemon","lime","mint","celery",
                  "broccoli","cauliflower","mushroom","cucumber","zucchini","eggplant"}
    produce, dairy_meat, dry_goods = [], [], []
    for d in deficits:
        item = d.get("item","")
        qty  = d.get("buy", 0)
        unit = d.get("unit","")
        have = d.get("have", 0)
        need = d.get("need", 0)
        label = f"**{item.title()}** — {qty} {unit}"
        if have > 0:
            label += f" *(have {have}, need {need})*"
        key = item.lower()
        if key in dairy_set or key in meat_set: dairy_meat.append((item, label))
        elif key in veggie_set:                  produce.append((item, label))
        else:                                    dry_goods.append((item, label))
    for section, items in [
        ("🥦  Produce & Fresh", produce),
        ("🥩  Dairy & Protein", dairy_meat),
        ("🌾  Dry Goods & Pantry", dry_goods),
    ]:
        if items:
            st.markdown(f'<div class="sl-section">{section}</div>', unsafe_allow_html=True)
            for item_name, label in items:
                st.checkbox(label, key=f"sl_ck_{item_name}", value=False)

# ─────────────────────────────────────────────────────────────────────────────
# Event labeller (chat history sidebar labels)
# ─────────────────────────────────────────────────────────────────────────────
_NUM  = r"(?P<num>\d+(?:\.\d+)?)"
_UNIT = r"(?P<unit>count|counts|pcs?|pieces?|gms?|grams?|kg|ml|l)\b"
_ITEM = r"(?P<item>[a-zA-Z][a-zA-Z \-']{0,40})"

USER_PATTERNS: List[Tuple[re.Pattern, callable]] = [
    (re.compile(r"(?i)\b(what('?s| is) in|list|show).*pantry\b"), lambda m: "List pantry"),
    (re.compile(r"(?i)\b(how (many|much)|do i have)\s+(?P<item>[a-zA-Z \-']+)\??"),
     lambda m: f"Qty: {m.group('item').strip().lower()}"),
    (re.compile(fr"(?i)\badd\b\s+{_NUM}\s*(?:{_UNIT})?\s+{_ITEM}"),
     lambda m: f"Add {m.group('num')}{' '+m.group('unit') if m.groupdict().get('unit') else ''} {m.group('item').strip().lower()}"),
    (re.compile(fr"(?i)\b(?:remove|delete)\b\s+{_NUM}\s*(?:{_UNIT})?\s+{_ITEM}"),
     lambda m: f"Remove {m.group('num')}{' '+m.group('unit') if m.groupdict().get('unit') else ''} {m.group('item').strip().lower()}"),
    (re.compile(r"(?i)\b(plan|meal plan)\b"),  lambda m: "Plan meals"),
    (re.compile(r"(?i)\b(shopping list|what.*missing|gaps?)\b"), lambda m: "Shopping list"),
    (re.compile(r"(?i)\bcooked\b"),            lambda m: "Marked cooked"),
    (re.compile(r"(?i)\bwhat can i cook\b"),   lambda m: "Cookable dishes"),
]

def label_user_turn(text: str) -> str:
    s = text.strip()
    for pat, labeller in USER_PATTERNS:
        m = pat.search(s)
        if m: return labeller(m)
    words = re.findall(r"[^\s]+", s)
    return " ".join(words[:6]) + ("…" if len(words) > 6 else "")

# ─────────────────────────────────────────────────────────────────────────────
# Brand header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="kb-brand">
  <span class="logo">🍳</span>
  <span class="name">Kitch<span class="dot">Bot</span></span>
  <span class="tag">— Cook regularly, stress less</span>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────
tab_pantry, tab_plan, tab_chat = st.tabs(["📦  My Pantry", "📅  Meal Plan", "💬  Chat with KitchBot"])


# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — PANTRY
# ═════════════════════════════════════════════════════════════════════════════
with tab_pantry:
    col_table, col_actions = st.columns([0.58, 0.42], gap="large")

    # ── Left: Pantry table ────────────────────────────────────────────────────
    with col_table:
        st.markdown('<div class="kb-card-title">Your Pantry</div>', unsafe_allow_html=True)
        ok, payload = _load_json_ok(PANTRY_PATH)
        if ok and isinstance(payload, dict) and payload:
            rows = _parse_pantry_rows(payload)
            # Filter
            pf = st.text_input("🔍 Filter items", placeholder="e.g. chicken, rice…",
                               label_visibility="collapsed", key="pantry_filter_input")
            if pf.strip():
                rows = [r for r in rows if pf.strip().lower() in r["Item"].lower()]
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True,
                         column_config={
                             "#":        st.column_config.NumberColumn(width="small"),
                             "Item":     st.column_config.TextColumn(width="medium"),
                             "Unit":     st.column_config.TextColumn(width="small"),
                             "Quantity": st.column_config.TextColumn(width="medium"),
                         })
            st.caption(f"{len(rows)} item{'s' if len(rows) != 1 else ''} in pantry")
        elif ok and not payload:
            st.markdown("""
            <div class="empty-state">
              <div class="es-icon">📦</div>
              <div class="es-title">Pantry is empty</div>
              <div class="es-desc">Add your first ingredient using the form on the right.</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.error(payload)

    # ── Right: Actions ────────────────────────────────────────────────────────
    with col_actions:

        # ── Quick Add ─────────────────────────────────────────────────────────
        with st.expander("➕  Add item", expanded=True):
            with st.form("pantry_add_form", clear_on_submit=True):
                item_name = st.text_input("Item name", placeholder="e.g. chicken, rice, milk…")
                a1, a2 = st.columns(2)
                qty  = a1.number_input("Quantity", min_value=1, value=1, step=1)
                unit = a2.selectbox("Unit", ["count", "g", "ml"])
                submitted = st.form_submit_button("Add to Pantry", type="primary",
                                                  use_container_width=True)
            if submitted:
                if not item_name.strip():
                    st.warning("Please enter an item name.")
                else:
                    with st.spinner("Adding…"):
                        try:
                            result = _tool_add.invoke({
                                "payload": {
                                    "item": item_name.strip().lower(),
                                    "quantity": int(qty),
                                    "unit": unit,
                                }
                            })
                            st.success(f"✓ {result}")
                        except Exception as e:
                            st.error(f"Error: {e}")

        # ── Remove item ───────────────────────────────────────────────────────
        with st.expander("➖  Remove item"):
            with st.form("pantry_remove_form", clear_on_submit=True):
                rem_item = st.text_input("Item name", placeholder="e.g. egg, tomato…",
                                         key="rem_item")
                r1, r2, r3 = st.columns([1.2, 1, 1])
                rem_qty  = r1.number_input("Qty (0 = remove all)", min_value=0, value=0,
                                           step=1, key="rem_qty")
                rem_unit = r2.selectbox("Unit", ["count", "g", "ml"], key="rem_unit")
                rem_sub  = r3.form_submit_button("Remove", type="primary",
                                                  use_container_width=True)
            if rem_sub:
                if not rem_item.strip():
                    st.warning("Enter an item name.")
                else:
                    payload_rem: Dict[str, Any] = {"item": rem_item.strip().lower()}
                    if rem_qty > 0:
                        payload_rem["quantity"] = int(rem_qty)
                        payload_rem["unit"] = rem_unit
                    with st.spinner("Removing…"):
                        try:
                            result = _tool_remove.invoke({"payload": payload_rem})
                            st.success(f"✓ {result}")
                        except Exception as e:
                            st.error(f"Error: {e}")

        # ── Update / set exact quantity ───────────────────────────────────────
        with st.expander("✏️  Update quantity"):
            with st.form("pantry_update_form", clear_on_submit=True):
                upd_item = st.text_input("Item name", key="upd_item")
                u1, u2, u3 = st.columns([1.2, 1, 1])
                upd_qty  = u1.number_input("New quantity", min_value=0, value=1,
                                           step=1, key="upd_qty")
                upd_unit = u2.selectbox("Unit", ["count", "g", "ml"], key="upd_unit")
                upd_sub  = u3.form_submit_button("Update", type="primary",
                                                  use_container_width=True)
            if upd_sub:
                if not upd_item.strip():
                    st.warning("Enter an item name.")
                else:
                    with st.spinner("Updating…"):
                        try:
                            result = _tool_update.invoke({
                                "payload": {
                                    "item": upd_item.strip().lower(),
                                    "quantity": int(upd_qty),
                                    "unit": upd_unit,
                                }
                            })
                            st.success(f"✓ {result}")
                        except Exception as e:
                            st.error(f"Error: {e}")

        # ── Reset button ───────────────────────────────────────────────────────
        st.divider()
        if st.button("↺  Reset chat & plan", use_container_width=True):
            ss["messages_kitchen"].clear()
            ss["events"].clear()
            ss["focus_msg_idx"] = None
            ss["cuisine_autofocus"] = ""
            ss["show_shopping_list"] = False
            try:
                planner_memory.memories.clear()
                planner_memory.memories["constraints"] = dict(PLANNER_DEFAULTS)
            except Exception:
                pass
            try:
                if slot_memory:
                    slot_memory.memories.clear()
            except Exception:
                pass
            st.success("Chat and plan cleared.")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — MEAL PLAN
# ═════════════════════════════════════════════════════════════════════════════
with tab_plan:

    # ── Header row: mode badge + start date + generate button ─────────────────
    h1, h2, h3 = st.columns([0.4, 0.35, 0.25])
    with h1:
        _c  = planner_memory.memories.get("constraints", {})
        _mode = _c.get("mode", "pantry-first-strict")
        if _mode == "pantry-first-strict":
            st.markdown('<span class="mode-badge">🔒 Pantry-first (strict)</span>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<span class="mode-badge mode-badge-free">🛒 Freeform</span>',
                        unsafe_allow_html=True)
    with h2:
        ss["start_date"] = st.date_input("Plan start date", ss["start_date"],
                                          label_visibility="collapsed")
    with h3:
        gen_clicked = st.button("✨ Generate Plan", type="primary", use_container_width=True)

    # ── Generate settings (collapsible) ───────────────────────────────────────
    with st.expander("⚙️  Plan settings", expanded=gen_clicked):
        s1, s2, s3 = st.columns(3)
        gen_days  = s1.number_input("Days", 1, 14, 3, 1)
        gen_meals = s2.selectbox("Meals/day",
            ["3 (Breakfast, Lunch, Dinner)", "2 (Lunch, Dinner)", "1 (Dinner only)"])
        gen_mode  = s3.selectbox("Mode", ["Pantry-first", "Freeform"])

        s4, s5, s6 = st.columns(3)
        gen_cuisine  = s4.text_input("Cuisine", placeholder="any")
        gen_diet     = s5.selectbox("Diet", ["Any", "vegetarian", "eggtarian", "non-veg"])
        gen_max_time = s6.number_input("Max time (min)", 0, 240, 0, 15)
        gen_no_rpt   = st.checkbox("Avoid repeats", value=False)

        go_btn = st.button("Generate", type="primary", use_container_width=True, key="gen_go")

    if gen_clicked or go_btn:
        meals_hint = ("3 meals/day" if gen_meals.startswith("3") else
                      "2 meals/day" if gen_meals.startswith("2") else "1 meal/day")
        mode_hint  = "pantry-first" if gen_mode == "Pantry-first" else "freeform"
        req  = f"Please generate a {int(gen_days)}-day {mode_hint} meal plan with {meals_hint}."
        if gen_cuisine.strip(): req += f" Cuisine: {gen_cuisine.strip()}."
        if gen_diet != "Any":   req += f" Diet: {gen_diet}."
        if gen_max_time > 0:    req += f" Max cook time: {int(gen_max_time)} minutes."
        if gen_no_rpt:          req += " No repeats."
        with st.spinner("Planning your meals…"):
            try:
                out = kitchen_chat(req)
                ss["messages_kitchen"].append({"role": "user",    "content": req})
                ss["messages_kitchen"].append({"role": "assistant","content": out})
                st.success(out)
            except Exception as e:
                st.error(f"Error: {e}")

    st.divider()

    # ── Plan grid ─────────────────────────────────────────────────────────────
    plan: Dict[str, Dict[str, str]] = planner_memory.memories.get("plan", {}) or {}

    if not plan:
        st.markdown("""
        <div class="empty-state">
          <div class="es-icon">📅</div>
          <div class="es-title">No plan yet</div>
          <div class="es-desc">
            Hit <strong>✨ Generate Plan</strong> above to create your meal plan,<br>
            or ask KitchBot in the Chat tab.
          </div>
        </div>""", unsafe_allow_html=True)
    else:
        edit_mode = st.toggle("✏️  Edit mode", value=False,
                              help="Enable to rename dishes; click Save to commit.")

        days_sorted = sorted(plan.keys(), key=lambda d: (int(re.sub(r"\D","",d) or 0), d))

        def _day_label(day_key: str) -> Tuple[str, str]:
            try:    n = int(re.sub(r"\D","",day_key) or "1")
            except: n = 1
            d = ss["start_date"] + datetime.timedelta(days=n-1)
            return day_key, d.strftime("%a, %d %b")

        MEALS = ["Breakfast", "Lunch", "Dinner"]

        # Column headers
        header_cols = st.columns([0.12] + [1] * len(days_sorted), gap="small")
        header_cols[0].markdown("&nbsp;", unsafe_allow_html=True)
        for ci, day in enumerate(days_sorted):
            dk, date_str = _day_label(day)
            header_cols[ci+1].markdown(
                f'<div class="plan-day-label">{dk}<span class="plan-day-date">{date_str}</span></div>',
                unsafe_allow_html=True)

        # Meal rows
        pending_updates: List[Dict] = []
        for meal in MEALS:
            row_cols = st.columns([0.12] + [1] * len(days_sorted), gap="small")
            row_cols[0].markdown(
                f'<div class="meal-label" style="padding-top:10px">{meal[:5]}</div>',
                unsafe_allow_html=True)
            for ci, day in enumerate(days_sorted):
                dish = (plan.get(day) or {}).get(meal, "")
                with row_cols[ci+1]:
                    if not edit_mode:
                        if dish:
                            if st.button(dish, key=f"pb_{day}_{meal}",
                                         use_container_width=True, help=f"Preview {dish}"):
                                ss["cuisine_autofocus"] = dish
                        else:
                            st.markdown('<div class="meal-chip-empty">—</div>',
                                        unsafe_allow_html=True)
                    else:
                        new_val = st.text_input(
                            f"{meal}", value=dish,
                            key=f"edit_{day}_{meal}", label_visibility="collapsed",
                            placeholder="Dish name…")
                        if new_val.strip() and new_val.strip() != (dish or "").strip():
                            pending_updates.append({
                                "day": day, "meal": meal,
                                "recipe_name": new_val.strip(), "reason": "edited in UI"
                            })

        if edit_mode and st.button("💾 Save edits", type="primary", use_container_width=True):
            msgs = []
            for upd in pending_updates:
                try:
                    msg = update_plan.invoke({"payload": upd})
                    plan.setdefault(upd["day"], {})[upd["meal"]] = upd["recipe_name"]
                    planner_memory.memories["plan"] = plan
                except Exception as e:
                    msg = f"Error: {e}"
                msgs.append(str(msg))
            st.success("Saved:\n" + "\n".join(msgs) if msgs else "No changes.")

        # ── Recipe preview (autofocus) ─────────────────────────────────────────
        if ss.get("cuisine_autofocus"):
            dish = ss["cuisine_autofocus"]
            recipes_all = cuisine_load()
            picked = next((r for r in recipes_all
                           if (r.get("name") or "").lower() == dish.lower()), None)
            with st.expander(f"📖  {dish.title()} — recipe", expanded=True):
                if picked:
                    st.markdown(_fmt_recipe_md(picked))
                else:
                    st.info("Recipe not found in the database.")
                if st.button("Close preview", key="close_preview"):
                    ss["cuisine_autofocus"] = ""
                    st.rerun()

        st.divider()

        # ── Cook meal + Shopping + Export ─────────────────────────────────────
        act1, act2, act3 = st.columns(3, gap="medium")

        with act1:
            st.markdown('<div class="kb-card-title">Mark Cooked</div>',
                        unsafe_allow_html=True)
            with st.form("cook_form"):
                ck_day  = st.text_input("Day (e.g. Day1)", placeholder="Day1")
                ck_meal = st.selectbox("Meal", ["Breakfast","Lunch","Dinner"])
                ck_dish = st.text_input("Or enter dish name", placeholder="optional")
                ck_sub  = st.form_submit_button("✅ Mark Cooked", type="primary",
                                                use_container_width=True)
            if ck_sub:
                p = {"dish": ck_dish.strip()} if ck_dish.strip() \
                    else {"day": ck_day.strip(), "meal": ck_meal}
                try:
                    st.success(str(cook_meal.invoke({"payload": p})))
                except Exception as e:
                    st.error(f"Error: {e}")

        with act2:
            st.markdown('<div class="kb-card-title">Shopping List</div>',
                        unsafe_allow_html=True)
            if st.button("🛒 Get Shopping List", use_container_width=True, type="primary"):
                try:
                    get_shopping_list.invoke({"_": None})
                    ss["show_shopping_list"] = True
                except Exception as e:
                    st.error(f"Error: {e}")
            if ss.get("show_shopping_list"):
                _render_shopping_list()

        with act3:
            st.markdown('<div class="kb-card-title">Export Plan</div>',
                        unsafe_allow_html=True)
            file_name = st.text_input("Filename (optional)", placeholder="my_meal_plan",
                                      key="export_fname")
            if st.button("💾 Export to JSON", use_container_width=True, type="primary"):
                try:
                    msg = save_plan.invoke({"payload": file_name.strip() or None})
                    st.success(str(msg))
                except Exception as e:
                    st.error(f"Error: {e}")
            st.caption("Saved to the /plans folder.")

        st.divider()

        # ── Recipe search / browse ─────────────────────────────────────────────
        with st.expander("🔍  Browse recipes"):
            recipes_all = cuisine_load()
            cuisines    = sorted({(r.get("cuisine") or "").title()
                                  for r in recipes_all if r.get("cuisine")})
            bc1, bc2, bc3 = st.columns([1.5, 1, 1])
            q_name      = bc1.text_input("Search by name", placeholder="e.g. palak paneer",
                                         key="browse_q")
            sel_cuisine = bc2.selectbox("Cuisine", ["Any"] + cuisines, key="browse_cuisine")
            sel_diet    = bc3.selectbox("Diet", ["Any","veg","eggtarian","non-veg"],
                                        key="browse_diet")

            q_l        = q_name.strip().lower()
            wc         = (sel_cuisine if sel_cuisine != "Any" else "").lower()
            wd         = (sel_diet    if sel_diet    != "Any" else "")
            matches    = [r for r in recipes_all
                          if (not q_l or q_l in (r.get("name","")).lower())
                          and (not wc or (r.get("cuisine","").lower() == wc))
                          and cuisine_diet_ok(r.get("diet"), wd)]

            if not matches:
                st.info("No recipes match those filters.")
            else:
                disp = [{"Name": r.get("name","").title(),
                          "Cuisine": (r.get("cuisine","") or "").title(),
                          "Diet": r.get("diet",""),
                          "Time (min)": int(r.get("prep_time_min",0)) + int(r.get("cook_time_min",0))}
                         for r in matches]
                st.dataframe(pd.DataFrame(disp), use_container_width=True, hide_index=True)
                names  = [m["Name"] for m in disp]
                pick   = st.selectbox("View full recipe", names, key="browse_pick")
                picked = next(r for r in matches if r.get("name","").title() == pick)
                st.markdown(_fmt_recipe_md(picked))


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — CHAT
# ═════════════════════════════════════════════════════════════════════════════
with tab_chat:

    msgs = ss["messages_kitchen"]

    # ── Empty state ────────────────────────────────────────────────────────────
    if not msgs:
        st.markdown("""
        <div class="empty-state" style="padding-top: 30px">
          <div class="es-icon">🤖</div>
          <div class="es-title">Hey! I'm KitchBot</div>
          <div class="es-desc">
            Ask me anything about your pantry, recipes, or meal planning.<br>
            Here are a few things to get you started:
          </div>
        </div>""", unsafe_allow_html=True)

        # Suggestion chips (clicking pre-fills the input via session state)
        suggestions = [
            "What can I cook right now?",
            "Generate a 3-day pantry-first plan",
            "What's missing for Palak Paneer?",
            "Show me Indian vegetarian recipes",
            "Get my shopping list",
        ]
        chip_html = '<div class="chips-row">' + "".join(
            f'<span class="chip">{s}</span>' for s in suggestions
        ) + '</div>'
        st.markdown(chip_html, unsafe_allow_html=True)
        st.caption("(Type your question below or click a suggestion above.)")

    # ── Message history ────────────────────────────────────────────────────────
    for i, msg in enumerate(msgs):
        role   = msg["role"]
        avatar = "🙂" if role == "user" else "🍳"
        with st.chat_message(role, avatar=avatar):
            st.markdown(msg["content"])

    # ── Chat input (pins to bottom of tab) ────────────────────────────────────
    prompt = st.chat_input("Ask KitchBot anything — pantry, recipes, meal plans…")
    if prompt:
        ss["messages_kitchen"].append({"role": "user", "content": prompt})
        ss["events"].append({"label": label_user_turn(prompt),
                              "msg_idx": len(ss["messages_kitchen"]) - 1})

        with st.chat_message("user", avatar="🙂"):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar="🍳"):
            with st.spinner("KitchBot is thinking…"):
                try:
                    reply = kitchen_chat(prompt)
                except Exception as err:
                    reply = f"Sorry, something went wrong: {err}"
            if isinstance(reply, dict) and "output" in reply:
                reply = reply["output"]
            reply = str(reply)
            st.markdown(reply)

        ss["messages_kitchen"].append({"role": "assistant", "content": reply})
