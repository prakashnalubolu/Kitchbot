"use client";
import { useState, useEffect } from "react";
import { historyApi } from "@/lib/api";
import { ThumbsUp, ThumbsDown, Star, Shuffle, RefreshCw } from "lucide-react";

type HistoryEntry = { date: string; dish: string; meal: string };
type RatingEntry  = { dish: string; up: number; down: number; last: string };

function parseHistory(raw: string): HistoryEntry[] {
  return raw.split("\n")
    .filter(l => l.trim() && !l.startsWith("No ") && !l.startsWith("Cook"))
    .map((line, i) => {
      const m = line.match(/(\d{4}-\d{2}-\d{2})[^\w]*(.+?)(?:\s*[-—]\s*(Breakfast|Lunch|Dinner|Snack))?$/i);
      return m
        ? { date: m[1], dish: m[2].trim(), meal: m[3] ?? "" }
        : { date: "", dish: line.trim().replace(/^[•\-*]\s*/, ""), meal: "" };
    }).filter(e => e.dish.length > 1);
}

function parseRatings(raw: string): RatingEntry[] {
  return raw.split("\n")
    .filter(l => l.includes("👍") || l.includes("👎"))
    .map(line => {
      const upM   = line.match(/👍\s*(\d+)/);
      const downM = line.match(/👎\s*(\d+)/);
      const dishM = line.match(/^[•\-*]?\s*(.+?)\s*[:\—]/);
      return dishM
        ? { dish: dishM[1].trim(), up: parseInt(upM?.[1] ?? "0"), down: parseInt(downM?.[1] ?? "0"), last: upM ? "up" : "down" }
        : null;
    }).filter(Boolean) as RatingEntry[];
}

export default function HistoryPage() {
  const [history, setHistory]     = useState<HistoryEntry[]>([]);
  const [ratings, setRatings]     = useState<RatingEntry[]>([]);
  const [variety, setVariety]     = useState("");
  const [rateInput, setRateInput] = useState("");
  const [msg, setMsg]             = useState("");
  const [days, setDays]           = useState(30);
  const [tab, setTab]             = useState<"history"|"ratings">("history");

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

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">History & Ratings</h1>
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
        {(["history","ratings"] as const).map(t => (
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
              {[7,14,30,90].map(d => <option key={d} value={d}>{d}d</option>)}
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
                  <div>
                    <p className="text-sm font-medium text-gray-900">{e.dish}</p>
                    {e.meal && <p className="text-xs text-gray-400">{e.meal}</p>}
                  </div>
                  <div className="flex items-center gap-2">
                    {e.date && <span className="text-xs text-gray-400">{e.date}</span>}
                    <button onClick={() => handleRate(e.dish, "up")} className="text-gray-300 hover:text-green-500 p-1"><ThumbsUp size={13}/></button>
                    <button onClick={() => handleRate(e.dish, "down")} className="text-gray-300 hover:text-red-500 p-1"><ThumbsDown size={13}/></button>
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
                    <span className="flex items-center gap-1 text-green-600"><ThumbsUp size={12}/> {r.up}</span>
                    <span className="flex items-center gap-1 text-red-500"><ThumbsDown size={12}/> {r.down}</span>
                  </div>
                </li>
              ))}
            </ul>
      )}
    </div>
  );
}
