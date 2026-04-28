"use client";
import { useState, useEffect } from "react";
import { planApi, recipesApi } from "@/lib/api";
import {
  Wand2, ShoppingCart, ChefHat, Download, Eye, Edit2, X,
  FileJson, Check, Copy, AlertTriangle,
} from "lucide-react";

type Slot = { day: string; meal: string; dish: string; covered: boolean };

const MEALS    = ["Breakfast", "Lunch", "Dinner"];
const DIETS    = ["any", "veg", "eggtarian", "non-veg"];
const CUISINES = ["any", "Indian", "Italian", "Chinese", "Mexican", "American",
                  "Mediterranean", "Thai", "Japanese", "Middle Eastern"];
const MODES    = [
  { value: "pantry-preferred",    label: "Pantry-first (recommended)" },
  { value: "pantry-first-strict", label: "Strict pantry only" },
  { value: "freeform",            label: "Freeform (any recipe)" },
];

// Backend returns: "Mode: ... Filled X/Y slots. Day1: Dish, Dish, Dish Day2: ..."
function parsePlan(raw: string, mealTypes: string[] = MEALS): Slot[] {
  const slots: Slot[] = [];
  const segments = raw.split(/(?=\bDay\d+:)/);
  for (const seg of segments) {
    const m = seg.match(/^(Day\d+):\s*(.+)/);
    if (!m) continue;
    const day = m[1];
    let dishPart = m[2]
      .replace(/\s+\d+\s+slot.*/i, "")
      .replace(/\s+Your pantry.*/i, "")
      .replace(/\s+Switch to.*/i, "")
      .trim();
    const dishes = dishPart.split(",").map(d => d.trim()).filter(d => d && d !== "—");
    dishes.forEach((rawDish, i) => {
      if (i < mealTypes.length) {
        const cooked = rawDish.startsWith("✅");
        const dish = rawDish.replace(/^✅\s*/, "").trim();
        if (dish) slots.push({ day, meal: mealTypes[i], dish, covered: cooked });
      }
    });
  }
  return slots;
}

function ConfirmDialog({
  title, message, confirmLabel = "Confirm", variant = "orange",
  onConfirm, onCancel,
}: {
  title: string; message: string; confirmLabel?: string;
  variant?: "orange" | "red"; onConfirm: () => void; onCancel: () => void;
}) {
  const c = variant === "red"
    ? { ring: "bg-red-100 text-red-600",    btn: "bg-red-600 hover:bg-red-700" }
    : { ring: "bg-orange-100 text-orange-600", btn: "bg-orange-600 hover:bg-orange-700" };
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-sm p-6">
        <div className="flex items-start gap-3 mb-5">
          <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 ${c.ring}`}>
            <AlertTriangle size={16} />
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900 mb-1">{title}</p>
            <p className="text-sm text-gray-600 leading-relaxed">{message}</p>
          </div>
        </div>
        <div className="flex gap-2 justify-end">
          <button onClick={onCancel}
            className="px-4 py-2 text-sm border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50">
            Cancel
          </button>
          <button onClick={onConfirm}
            className={`px-4 py-2 text-sm text-white rounded-lg ${c.btn}`}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function RecipeModal({ dish, onClose }: { dish: string; onClose: () => void }) {
  const [text, setText]   = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    recipesApi.get(dish).then(r => setText(r.result)).finally(() => setLoading(false));
  }, [dish]);
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-900 capitalize">{dish}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1 rounded">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading
            ? <p className="text-sm text-gray-400">Loading recipe…</p>
            : <pre className="text-sm text-gray-700 whitespace-pre-wrap font-sans leading-relaxed">{text}</pre>}
        </div>
      </div>
    </div>
  );
}

function ShoppingListPanel({
  text, loading, onRefresh,
}: {
  text: string; loading: boolean; onRefresh: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) return (
    <div className="text-center py-10 text-sm text-gray-400">Loading shopping list…</div>
  );

  if (!text.trim()) return (
    <div className="bg-white border border-gray-200 rounded-lg p-8 text-center space-y-3">
      <ShoppingCart size={28} className="mx-auto text-gray-300" />
      <p className="text-sm text-gray-500">Shopping list reflects your current meal plan.</p>
      <p className="text-xs text-gray-400">Generate a plan first, then the list updates automatically.</p>
      <button onClick={onRefresh}
        className="text-sm bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700">
        Load Shopping List
      </button>
    </div>
  );

  const lines = text.split("\n").filter(l => l.trim());
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-gray-700">Items needed</p>
        <div className="flex items-center gap-3">
          <button onClick={onRefresh} className="text-xs text-gray-400 hover:text-gray-600">Refresh</button>
          <button onClick={copy} className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1">
            {copied ? <><Check size={11} /> Copied</> : <><Copy size={11} /> Copy all</>}
          </button>
        </div>
      </div>
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <ul className="space-y-1">
          {lines.map((line, i) => {
            const clean = line.replace(/^[•\-*]\s*/, "").trim();
            const isHeader = clean.endsWith(":") && !line.match(/^[•\-*]/);
            return isHeader ? (
              <li key={i} className="text-xs font-semibold text-gray-500 uppercase tracking-wide mt-3 first:mt-0">
                {clean.replace(/:$/, "")}
              </li>
            ) : (
              <li key={i} className="text-sm text-gray-700 flex items-start gap-1.5">
                <span className="text-gray-300 mt-0.5 flex-shrink-0">•</span>
                <span>{clean}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

export default function PlanPage() {
  const [slots, setSlots]         = useState<Slot[]>([]);
  const [shopping, setShopping]   = useState("");
  const [msg, setMsg]             = useState("");
  const [loading, setLoading]     = useState(false);
  const [shopLoading, setShopLoading] = useState(false);
  const [tab, setTab]             = useState<"plan" | "shopping">("plan");
  const [previewDish, setPreviewDish] = useState<string | null>(null);
  const [editSlot, setEditSlot]   = useState<{ day: string; meal: string; value: string } | null>(null);
  const [cookConfirm, setCookConfirm] = useState<Slot | null>(null);
  const [editConfirm, setEditConfirm] = useState(false);
  // plan constraints
  const [days, setDays]           = useState(7);
  const [meals, setMeals]         = useState(MEALS);
  const [mode, setMode]           = useState("pantry-preferred");
  const [diet, setDiet]           = useState("any");
  const [cuisine, setCuisine]     = useState("any");
  const [household, setHousehold] = useState(1);
  const [avoidDays, setAvoidDays] = useState(7);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(""), 4000); };

  const handleGenerate = async () => {
    setLoading(true);
    setSlots([]);
    setShopping("");           // reset stale shopping list
    try {
      await planApi.setConstraints({
        mode,
        diet:    diet    === "any" ? null : diet,
        cuisine: cuisine === "any" ? null : cuisine,
        household_size:    household,
        avoid_recent_days: avoidDays,
      });
      const res = await planApi.autoPlan({ days, meals, continue_plan: false });
      setSlots(parsePlan(res.result, meals));
      flash("Plan generated!");
    } finally { setLoading(false); }
  };

  const handleCook = async (s: Slot) => {
    setCookConfirm(null);
    await planApi.cook({ day: s.day, meal: s.meal });
    setSlots(prev => prev.map(slot =>
      slot.day === s.day && slot.meal === s.meal ? { ...slot, covered: true } : slot
    ));
    flash(`Cooked ${s.dish}! Rate it in History.`);
  };

  const handleShopping = async () => {
    setShopLoading(true);
    try {
      const res = await planApi.shopping();
      setShopping(res.result);
    } finally { setShopLoading(false); }
  };

  const handleSaveEdit = async () => {
    if (!editSlot || !editSlot.value.trim()) return;
    setEditConfirm(false);
    await planApi.updateSlot({
      day: editSlot.day,
      meal: editSlot.meal,
      recipe_name: editSlot.value.trim(),
      reason: "user edit",
    });
    setSlots(prev => prev.map(s =>
      s.day === editSlot.day && s.meal === editSlot.meal
        ? { ...s, dish: editSlot.value.trim() }
        : s
    ));
    setEditSlot(null);
    flash("Meal updated");
  };

  // Auto-load shopping list when switching to that tab
  useEffect(() => {
    if (tab === "shopping" && !shopping && !shopLoading) {
      handleShopping();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const handleExportJson = () => {
    const blob = new Blob([JSON.stringify(slots, null, 2)], { type: "application/json" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = "meal-plan.json"; a.click();
    URL.revokeObjectURL(url);
  };

  const toggleMeal = (m: string) =>
    setMeals(prev => prev.includes(m) ? prev.filter(x => x !== m) : [...prev, m]);

  const grouped = slots.reduce<Record<string, Slot[]>>((acc, s) => {
    (acc[s.day] = acc[s.day] || []).push(s);
    return acc;
  }, {});

  const originalDish = editSlot
    ? slots.find(s => s.day === editSlot.day && s.meal === editSlot.meal)?.dish
    : null;

  return (
    <div className="space-y-5">
      {previewDish && <RecipeModal dish={previewDish} onClose={() => setPreviewDish(null)} />}

      {cookConfirm && (
        <ConfirmDialog
          title="Mark as cooked?"
          message={`Log "${cookConfirm.dish}" (${cookConfirm.meal}, ${cookConfirm.day}) as cooked? This adds it to your cooking history.`}
          confirmLabel="Yes, mark cooked"
          onConfirm={() => handleCook(cookConfirm)}
          onCancel={() => setCookConfirm(null)}
        />
      )}

      {editConfirm && editSlot && (
        <ConfirmDialog
          title="Update meal slot?"
          message={`Replace "${originalDish}" with "${editSlot.value.trim()}" for ${editSlot.meal} on ${editSlot.day}?`}
          confirmLabel="Save change"
          onConfirm={handleSaveEdit}
          onCancel={() => setEditConfirm(false)}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Meal Plan</h1>
        {slots.length > 0 && (
          <div className="flex gap-1">
            <button onClick={handleExportJson}
              className="p-1.5 rounded hover:bg-gray-100 text-gray-500" title="Export JSON">
              <FileJson size={16} />
            </button>
            <a href={planApi.pdfUrl()} target="_blank"
              className="p-1.5 rounded hover:bg-gray-100 text-gray-500" title="Download PDF">
              <Download size={16} />
            </a>
          </div>
        )}
      </div>

      {msg && <p className="text-sm bg-green-50 border border-green-200 text-green-800 rounded p-2">{msg}</p>}

      {/* Settings — always visible */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-4">
        <p className="text-sm font-semibold text-gray-700">Plan settings</p>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <label className="text-xs text-gray-600">
            Days
            <input type="number" min={1} max={14} value={days}
              onChange={e => setDays(+e.target.value)}
              className="mt-1 w-full border rounded px-2 py-1 text-sm" />
          </label>
          <label className="text-xs text-gray-600">
            Household size
            <input type="number" min={1} max={20} value={household}
              onChange={e => setHousehold(+e.target.value)}
              className="mt-1 w-full border rounded px-2 py-1 text-sm" />
          </label>
          <label className="text-xs text-gray-600">
            Avoid recent (days)
            <input type="number" min={0} max={30} value={avoidDays}
              onChange={e => setAvoidDays(+e.target.value)}
              className="mt-1 w-full border rounded px-2 py-1 text-sm" />
          </label>
        </div>

        <div className="flex gap-3 flex-wrap">
          <div>
            <p className="text-xs text-gray-600 mb-1">Mode</p>
            <select value={mode} onChange={e => setMode(e.target.value)}
              className="border rounded px-2 py-1 text-sm">
              {MODES.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
          </div>
          <div>
            <p className="text-xs text-gray-600 mb-1">Diet</p>
            <select value={diet} onChange={e => setDiet(e.target.value)}
              className="border rounded px-2 py-1 text-sm">
              {DIETS.map(d => <option key={d}>{d}</option>)}
            </select>
          </div>
          <div>
            <p className="text-xs text-gray-600 mb-1">Cuisine</p>
            <select value={cuisine} onChange={e => setCuisine(e.target.value)}
              className="border rounded px-2 py-1 text-sm">
              {CUISINES.map(c => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <p className="text-xs text-gray-600 mb-1">Meals</p>
            <div className="flex gap-1">
              {MEALS.map(m => (
                <button key={m} onClick={() => toggleMeal(m)}
                  className={`px-2 py-1 rounded text-xs border transition-colors ${
                    meals.includes(m)
                      ? "bg-green-600 text-white border-green-600"
                      : "text-gray-600 border-gray-200 hover:border-gray-400"
                  }`}>
                  {m}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Generate button */}
      <button onClick={handleGenerate} disabled={loading || meals.length === 0}
        className="flex items-center gap-2 bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50">
        <Wand2 size={15} /> {loading ? "Generating…" : "Generate Plan"}
      </button>

      {/* Tab bar: Plan | Shopping List */}
      <div className="flex gap-1 border-b border-gray-200">
        {(["plan", "shopping"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors
              ${tab === t ? "border-green-600 text-green-700" : "border-transparent text-gray-500 hover:text-gray-700"}`}>
            {t === "shopping"
              ? <><ShoppingCart size={13} /> Shopping List</>
              : "Plan"}
          </button>
        ))}
      </div>

      {/* Plan tab */}
      {tab === "plan" && (
        Object.keys(grouped).length === 0 ? (
          <div className="bg-white border border-gray-200 rounded-lg p-8 text-center">
            <p className="text-gray-400 text-sm">No plan yet. Set your preferences above and click Generate Plan.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {Object.entries(grouped).map(([day, daySlots]) => (
              <div key={day} className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                <div className="bg-gray-50 px-4 py-2 border-b border-gray-100">
                  <p className="text-sm font-semibold text-gray-700">{day}</p>
                </div>
                <ul className="divide-y divide-gray-50">
                  {daySlots.map(s => (
                    <li key={s.meal} className="px-4 py-3">
                      {editSlot?.day === s.day && editSlot?.meal === s.meal ? (
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-gray-400 uppercase tracking-wide w-16 flex-shrink-0">
                            {s.meal}
                          </span>
                          <input
                            value={editSlot.value}
                            onChange={e => setEditSlot({ ...editSlot, value: e.target.value })}
                            onKeyDown={e => {
                              if (e.key === "Enter")  setEditConfirm(true);
                              if (e.key === "Escape") setEditSlot(null);
                            }}
                            className="flex-1 border rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-green-400"
                            autoFocus
                          />
                          <button onClick={() => setEditConfirm(true)}
                            className="text-xs px-2 py-1 rounded bg-green-600 text-white hover:bg-green-700">
                            Save
                          </button>
                          <button onClick={() => setEditSlot(null)}
                            className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-600">
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center justify-between">
                          <div className="flex-1 min-w-0">
                            <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">{s.meal}</span>
                            <div className="flex items-center gap-2 mt-0.5">
                              <p className="text-sm font-medium text-gray-900 truncate">{s.dish}</p>
                              {s.covered && (
                                <span className="text-xs text-green-600 bg-green-50 border border-green-200 px-1.5 py-0.5 rounded-full flex-shrink-0">
                                  ✓ cooked
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-1 ml-2 flex-shrink-0">
                            <button onClick={() => setPreviewDish(s.dish)}
                              className="p-1.5 rounded text-gray-300 hover:text-blue-500 hover:bg-blue-50" title="View recipe">
                              <Eye size={13} />
                            </button>
                            <button onClick={() => setEditSlot({ day: s.day, meal: s.meal, value: s.dish })}
                              className="p-1.5 rounded text-gray-300 hover:text-gray-600 hover:bg-gray-100" title="Edit meal">
                              <Edit2 size={13} />
                            </button>
                            <button
                              onClick={() => setCookConfirm(s)}
                              disabled={s.covered}
                              className="flex items-center gap-1 text-xs bg-orange-50 text-orange-700 border border-orange-200 px-2 py-1 rounded hover:bg-orange-100 disabled:opacity-40 disabled:cursor-not-allowed">
                              <ChefHat size={12} /> {s.covered ? "Cooked" : "Cook"}
                            </button>
                          </div>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )
      )}

      {/* Shopping List tab */}
      {tab === "shopping" && (
        <ShoppingListPanel
          text={shopping}
          loading={shopLoading}
          onRefresh={handleShopping}
        />
      )}
    </div>
  );
}
