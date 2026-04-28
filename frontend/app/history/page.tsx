"use client";
import { useState, useEffect } from "react";
import { historyApi } from "@/lib/api";
import { ThumbsUp, ThumbsDown, Shuffle, RefreshCw } from "lucide-react";

type HistoryEntry = { date: string; dish: string; meal: string };
type RatingEntry  = { dish: string; up: number; down: number; last: string };

// Backend format: "- Dish Name — YYYY-MM-DD (meal)"
function parseHistory(raw: string): HistoryEntry[] {
  return raw.split("\n")
    .filter(l => l.trim() && !l.startsWith("**") && !l.startsWith("No ") && !l.startsWith("Cook"))
    .map(line => {
      const clean = line.replace(/^[•\-*]\s*/, "").trim();
      // "Chicken Curry — 2024-01-15 (dinner)"
      const m = clean.match(/^(.+?)\s*[—–-]\s*(\d{4}-\d{2}-\d{2})\s*(?:\((\w+)\))?/);
      if (m) return { dish: m[1].trim(), date: m[2], meal: m[3] ?? "" };
      return { date: "", dish: clean, meal: "" };
    }).filter(e => e.dish.length > 1 && !e.dish.startsWith("*") && !e.dish.startsWith("Meal"));
}

// Backend format: "- Dish Name — 👍👍👍 (+3 net)"
function parseRatings(raw: string): RatingEntry[] {
  return raw.split("\n")
    .filter(l => l.match(/^[•\-*]/))
    .map(line => {
      const clean = line.replace(/^[•\-*]\s*/, "").trim();
      // "Chicken Curry — 👍👍 (+2 net)"
      const m = clean.match(/^(.+?)\s*[—–-]\s*(👍*)\s*\(([+-]?\d+)\s*net\)/);
      if (!m) return null;
      const dish = m[1].trim();
      const ups  = [...m[2]].filter(c => c === "👍").length;
      const net  = parseInt(m[3]);
      const downs = Math.max(0, ups - net);
      return { dish, up: ups, down: downs, last: net >= 0 ? "up" : "down" };
    }).filter(Boolean) as RatingEntry[];
}

export default function HistoryPage() {
  const [history, setHistory]     = useState<HistoryEntry[]>([]);
  const [ratings, setRatings]     = useState<RatingEntry[]>([]);
  const [variety, setVariety]     = useState("");
  const [rateInput, setRateInput] = useState("");
  const [msg, setMsg]             = useState("");
  const [days, setDays]           = useState(30);
  const [tab, setTab]             = useState<"history" | "ratings">("history");

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(""), 3000); };

  const load = async () => {
    const [h, r] = await Promise.all([historyApi.list(days), historyApi.top(20)]);
    setHistory(parseHistory(h.result));
    setRatings(parseRatings(r.result));
  };

  useEffect(() => { load(); }, [days]);

  const handleRate = async (dish: string, rating: "up" | "down") => {
    const target = dish || rateInput.trim();
    if (!target) return;
    await historyApi.rate(target, rating);
    flash(`${rating === "up" ? "👍" : "👎"} Rated ${target}`);
    setRateInput("");
    load();
  };

  const handleVariety = async () => {
    const res = await historyApi.variety(7);
    setVariety(res.result);
  };

  const mealLabel = (meal: string) => {
    if (!meal) return null;
    const colors: Record<string, string> = {
      breakfast: "bg-amber-50 text-amber-700",
      lunch:     "bg-blue-50 text-blue-700",
      dinner:    "bg-purple-50 text-purple-700",
      snack:     "bg-green-50 text-green-700",
    };
    const key = meal.toLowerCase();
    return (
      <span className={`text-xs px-1.5 py-0.5 rounded capitalize ${colors[key] ?? "bg-gray-100 text-gray-500"}`}>
        {meal}
      </span>
    );
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Cook Log</h1>
          <p className="text-xs text-gray-500 mt-0.5">Every meal you've cooked + your recipe ratings</p>
        </div>
        <button onClick={load} className="p-1.5 rounded hover:bg-gray-100 text-gray-500">
          <RefreshCw size={16} />
        </button>
      </div>

      {msg && <p className="text-sm bg-green-50 border border-green-200 text-green-800 rounded p-2">{msg}</p>}

      {/* Variety button */}
      <button onClick={handleVariety}
        className="flex items-center gap-2 bg-purple-50 border border-purple-200 text-purple-700 px-3 py-2 rounded-lg text-sm hover:bg-purple-100">
        <Shuffle size={14} /> Suggest something different
      </button>
      {variety && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="text-sm font-semibold text-gray-700 mb-2">Variety suggestions</p>
          <pre className="text-sm text-gray-700 whitespace-pre-wrap font-sans">{variety}</pre>
        </div>
      )}

      {/* Rate a recipe */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="text-sm font-semibold text-gray-700 mb-3">Rate a recipe</p>
        <div className="flex gap-2">
          <input value={rateInput} onChange={e => setRateInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && rateInput.trim() && handleRate(rateInput, "up")}
            placeholder="Recipe name…" className="border rounded px-2 py-1.5 text-sm flex-1" />
          <button onClick={() => handleRate(rateInput, "up")} disabled={!rateInput.trim()}
            className="flex items-center gap-1 bg-green-50 border border-green-200 text-green-700 px-3 py-1.5 rounded text-sm hover:bg-green-100 disabled:opacity-40">
            <ThumbsUp size={13} /> Like
          </button>
          <button onClick={() => handleRate(rateInput, "down")} disabled={!rateInput.trim()}
            className="flex items-center gap-1 bg-red-50 border border-red-200 text-red-700 px-3 py-1.5 rounded text-sm hover:bg-red-100 disabled:opacity-40">
            <ThumbsDown size={13} /> Dislike
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {(["history", "ratings"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize border-b-2 -mb-px transition-colors
              ${tab === t ? "border-green-600 text-green-700" : "border-transparent text-gray-500 hover:text-gray-700"}`}>
            {t}
          </button>
        ))}
        {tab === "history" && (
          <div className="ml-auto flex items-center gap-1 pb-1">
            <label className="text-xs text-gray-500">Last</label>
            <select value={days} onChange={e => setDays(+e.target.value)}
              className="border rounded px-1.5 py-0.5 text-xs">
              {[7, 14, 30, 90].map(d => <option key={d} value={d}>{d}d</option>)}
            </select>
          </div>
        )}
      </div>

      {tab === "history" && (
        history.length === 0
          ? <p className="text-sm text-gray-400 py-4">No cooking history yet. Cook something from the Meal Plan!</p>
          : <ul className="space-y-1">
              {history.map((e, i) => (
                <li key={i} className="bg-white border border-gray-100 rounded-lg px-4 py-3 flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900">{e.dish}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      {e.date && <span className="text-xs text-gray-400">{e.date}</span>}
                      {mealLabel(e.meal)}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 ml-2">
                    <button onClick={() => handleRate(e.dish, "up")} className="text-gray-300 hover:text-green-500 p-1" title="Like">
                      <ThumbsUp size={13} />
                    </button>
                    <button onClick={() => handleRate(e.dish, "down")} className="text-gray-300 hover:text-red-500 p-1" title="Dislike">
                      <ThumbsDown size={13} />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
      )}

      {tab === "ratings" && (
        ratings.length === 0
          ? <p className="text-sm text-gray-400 py-4">No ratings yet. Cook and rate some dishes!</p>
          : <ul className="space-y-1">
              {ratings.map((r, i) => (
                <li key={i} className="bg-white border border-gray-100 rounded-lg px-4 py-3 flex items-center justify-between">
                  <p className="text-sm font-medium text-gray-900">{r.dish}</p>
                  <div className="flex items-center gap-3 text-sm">
                    <span className="flex items-center gap-1 text-green-600">
                      <ThumbsUp size={12} /> {r.up}
                    </span>
                    <span className="flex items-center gap-1 text-red-500">
                      <ThumbsDown size={12} /> {r.down}
                    </span>
                    <span className={`text-xs font-medium ${r.up > r.down ? "text-green-600" : r.down > r.up ? "text-red-500" : "text-gray-400"}`}>
                      {r.up > r.down ? "👍 Liked" : r.down > r.up ? "👎 Disliked" : "—"}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
      )}
    </div>
  );
}
