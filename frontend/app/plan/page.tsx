"use client";
import { useState, useEffect } from "react";
import { planApi } from "@/lib/api";
import { Wand2, ShoppingCart, ChefHat, Download, Settings2, RefreshCw } from "lucide-react";

type Slot = { day: string; meal: string; dish: string; covered: boolean };

function parsePlan(raw: string): Slot[] {
  const slots: Slot[] = [];
  let currentDay = "";
  for (const line of raw.split("\n")) {
    const dayM = line.match(/^(Day\d+|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)/i);
    if (dayM) { currentDay = dayM[1]; continue; }
    const slotM = line.match(/(Breakfast|Lunch|Dinner|Snack)\s*[:\—]\s*(.+)/i);
    if (slotM && currentDay) {
      const dish = slotM[2].trim();
      slots.push({
        day: currentDay,
        meal: slotM[1],
        dish,
        covered: line.includes("✅") || line.includes("🟢"),
      });
    }
  }
  return slots;
}

const DAYS = [1,2,3,4,5,6,7];
const MEALS = ["Breakfast","Lunch","Dinner"];
const DIETS = ["any","veg","eggtarian","non-veg"];
const MODES = [
  { value: "pantry-preferred", label: "Pantry-first (recommended)" },
  { value: "pantry-first-strict", label: "Strict pantry only" },
  { value: "freeform", label: "Freeform (any recipe)" },
];

export default function PlanPage() {
  const [slots, setSlots]           = useState<Slot[]>([]);
  const [shopping, setShopping]     = useState("");
  const [msg, setMsg]               = useState("");
  const [loading, setLoading]       = useState(false);
  const [showSettings, setSettings] = useState(false);
  const [showShop, setShowShop]     = useState(false);
  // constraints
  const [days, setDays]             = useState(7);
  const [meals, setMeals]           = useState(MEALS);
  const [mode, setMode]             = useState("pantry-preferred");
  const [diet, setDiet]             = useState("any");
  const [household, setHousehold]   = useState(1);
  const [avoidDays, setAvoidDays]   = useState(7);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(""), 4000); };

  const handleGenerate = async () => {
    setLoading(true);
    try {
      await planApi.setConstraints({ mode, diet: diet === "any" ? null : diet, household_size: household, avoid_recent_days: avoidDays });
      const res = await planApi.autoPlan({ days, meals, continue_plan: false });
      setSlots(parsePlan(res.result));
      flash("✅ Plan generated!");
    } finally { setLoading(false); }
  };

  const handleCook = async (s: Slot) => {
    await planApi.cook({ day: s.day, meal: s.meal });
    flash(`🍳 Cooked ${s.dish}! Rate it in History.`);
  };

  const handleShopping = async () => {
    const res = await planApi.shopping();
    setShopping(res.result);
    setShowShop(true);
  };

  const toggleMeal = (m: string) =>
    setMeals(prev => prev.includes(m) ? prev.filter(x => x !== m) : [...prev, m]);

  const grouped = slots.reduce<Record<string, Slot[]>>((acc, s) => {
    (acc[s.day] = acc[s.day] || []).push(s);
    return acc;
  }, {});

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Meal Plan</h1>
        <div className="flex gap-2">
          <button onClick={() => setSettings(s => !s)}
            className="p-1.5 rounded hover:bg-gray-100 text-gray-500" title="Settings">
            <Settings2 size={16} />
          </button>
          {slots.length > 0 && (
            <a href={planApi.pdfUrl()} target="_blank"
              className="p-1.5 rounded hover:bg-gray-100 text-gray-500" title="Download PDF">
              <Download size={16} />
            </a>
          )}
        </div>
      </div>

      {msg && <p className="text-sm bg-green-50 border border-green-200 text-green-800 rounded p-2">{msg}</p>}

      {showSettings && (
        <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
          <p className="text-sm font-semibold text-gray-700">Plan settings</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <label className="text-xs text-gray-600">
              Days
              <input type="number" min={1} max={14} value={days} onChange={e => setDays(+e.target.value)}
                className="mt-1 w-full border rounded px-2 py-1 text-sm" />
            </label>
            <label className="text-xs text-gray-600">
              Household size
              <input type="number" min={1} max={20} value={household} onChange={e => setHousehold(+e.target.value)}
                className="mt-1 w-full border rounded px-2 py-1 text-sm" />
            </label>
            <label className="text-xs text-gray-600">
              Avoid recent (days)
              <input type="number" min={0} max={30} value={avoidDays} onChange={e => setAvoidDays(+e.target.value)}
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
              <p className="text-xs text-gray-600 mb-1">Meals</p>
              <div className="flex gap-1">
                {MEALS.map(m => (
                  <button key={m} onClick={() => toggleMeal(m)}
                    className={`px-2 py-1 rounded text-xs border ${meals.includes(m) ? "bg-green-600 text-white border-green-600" : "text-gray-600"}`}>
                    {m}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        <button onClick={handleGenerate} disabled={loading}
          className="flex items-center gap-2 bg-green-600 text-white px-4 py-2 rounded text-sm hover:bg-green-700 disabled:opacity-50">
          <Wand2 size={15} /> {loading ? "Generating…" : "Generate Plan"}
        </button>
        {slots.length > 0 && (
          <button onClick={handleShopping}
            className="flex items-center gap-2 bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded text-sm hover:bg-gray-50">
            <ShoppingCart size={15} /> Shopping List
          </button>
        )}
      </div>

      {showShop && shopping && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-semibold text-gray-700">Shopping List</p>
            <button onClick={() => setShowShop(false)} className="text-xs text-gray-400 hover:text-gray-600">close</button>
          </div>
          <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono">{shopping}</pre>
        </div>
      )}

      {Object.keys(grouped).length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-lg p-8 text-center">
          <p className="text-gray-400 text-sm">No plan yet. Click Generate Plan to start.</p>
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
                  <li key={s.meal} className="flex items-center justify-between px-4 py-3">
                    <div>
                      <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">{s.meal}</span>
                      <p className="text-sm font-medium text-gray-900 mt-0.5">{s.dish}</p>
                    </div>
                    <button onClick={() => handleCook(s)}
                      className="flex items-center gap-1 text-xs bg-orange-50 text-orange-700 border border-orange-200 px-2 py-1 rounded hover:bg-orange-100">
                      <ChefHat size={12} /> Cook
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
