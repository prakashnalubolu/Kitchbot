"use client";
import { useState, useEffect } from "react";
import { historyApi, expiryApi } from "@/lib/api";
import { Leaf, Flame, UtensilsCrossed, TrendingUp, AlertTriangle, RefreshCw } from "lucide-react";

type Stats = {
  meals: number;
  food_saved_kg: number;
  co2_saved_kg: number;
  pantry_first_pct: number;
  tree_days: number;
};

function parseStats(raw: string): Stats {
  const n = (pattern: RegExp) => parseFloat(raw.match(pattern)?.[1] ?? "0");
  return {
    meals:           n(/(\d+)\s*meal/i),
    food_saved_kg:   n(/([\d.]+)\s*kg.*?(?:food|saved)/i),
    co2_saved_kg:    n(/([\d.]+)\s*kg.*?co[2₂]/i),
    pantry_first_pct: n(/([\d.]+)\s*%.*?pantry/i),
    tree_days:       n(/([\d.]+)\s*(?:tree|seedling)/i),
  };
}

type ExpiringItem = { item: string; expires: string; days_left: number };

function parseExpiry(raw: string): ExpiringItem[] {
  return raw.split("\n").map(line => {
    const m = line.match(/(.+?):.*?(\d{4}-\d{2}-\d{2}).*?(\d+)\s*day/i);
    return m ? { item: m[1].trim(), expires: m[2], days_left: parseInt(m[3]) } : null;
  }).filter(Boolean) as ExpiringItem[];
}

const Stat = ({ icon, label, value, sub, color }: {
  icon: React.ReactNode; label: string; value: string; sub?: string; color: string;
}) => (
  <div className={`bg-white border border-gray-200 rounded-xl p-4 flex items-start gap-3`}>
    <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${color}`}>
      {icon}
    </div>
    <div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      <p className="text-xs font-medium text-gray-700">{label}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  </div>
);

export default function ImpactPage() {
  const [stats, setStats]     = useState<Stats | null>(null);
  const [expiring, setExpiring] = useState<ExpiringItem[]>([]);
  const [rawStats, setRaw]    = useState("");

  const load = async () => {
    const [s, e] = await Promise.all([historyApi.impact(), expiryApi.soon(7)]);
    setRaw(s.result);
    setStats(parseStats(s.result));
    setExpiring(parseExpiry(e.result));
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Sustainability</h1>
          <p className="text-xs text-gray-500 mt-0.5">Your food waste reduction stats and expiring items</p>
        </div>
        <button onClick={load} className="p-1.5 rounded hover:bg-gray-100 text-gray-500">
          <RefreshCw size={16} />
        </button>
      </div>

      <div className="bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-xl p-4">
        <p className="text-sm font-semibold text-green-800">🌍 Every meal you cook from your pantry prevents food waste.</p>
        <p className="text-xs text-green-700 mt-1">
          Globally, 1/3 of all food produced is wasted — generating 8% of greenhouse gas emissions.
          KitchBot tracks your contribution to reducing that.
        </p>
      </div>

      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat icon={<UtensilsCrossed size={16} />} label="Meals cooked"
            value={String(stats.meals)} color="bg-blue-100 text-blue-600" />
          <Stat icon={<TrendingUp size={16} />} label="Food saved"
            value={`${stats.food_saved_kg.toFixed(1)} kg`}
            sub="ingredients used up" color="bg-green-100 text-green-700" />
          <Stat icon={<Flame size={16} />} label="CO₂ avoided"
            value={`${stats.co2_saved_kg.toFixed(1)} kg`}
            sub="≈ 2.5 kg CO₂ per kg food" color="bg-orange-100 text-orange-600" />
          <Stat icon={<Leaf size={16} />} label="Tree-days"
            value={stats.tree_days > 0 ? `${stats.tree_days.toFixed(0)}d` : "—"}
            sub="of CO₂ absorbed by a tree" color="bg-emerald-100 text-emerald-700" />
        </div>
      )}

      {/* Raw stats fallback */}
      {rawStats && !stats?.meals && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <pre className="text-sm text-gray-700 whitespace-pre-wrap font-sans">{rawStats}</pre>
        </div>
      )}

      {/* Expiring items */}
      {expiring.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <div className="bg-amber-50 px-4 py-3 border-b border-amber-100 flex items-center gap-2">
            <AlertTriangle size={14} className="text-amber-600" />
            <p className="text-sm font-semibold text-amber-800">Use these soon to avoid waste</p>
          </div>
          <ul className="divide-y divide-gray-50">
            {expiring.map(e => (
              <li key={e.item} className="flex items-center justify-between px-4 py-3">
                <p className="text-sm font-medium text-gray-900 capitalize">{e.item}</p>
                <div className="text-right">
                  <p className="text-xs text-gray-500">{e.expires}</p>
                  <p className={`text-xs font-medium ${e.days_left <= 2 ? "text-red-500" : "text-amber-600"}`}>
                    {e.days_left}d left
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Facts */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-2">
        <p className="text-sm font-semibold text-gray-700">Did you know?</p>
        {[
          "🇺🇸 Average US household wastes ~32% of food purchased",
          "🌡 Food waste produces methane — 80× more potent than CO₂ over 20 years",
          "💧 1 kg of beef takes ~15,000 litres of water to produce",
          "🥗 Eating seasonal + local cuts food carbon footprint by up to 50%",
          "📦 Meal planning is one of the most effective ways to cut household food waste",
        ].map(f => (
          <p key={f} className="text-xs text-gray-500">{f}</p>
        ))}
      </div>
    </div>
  );
}
