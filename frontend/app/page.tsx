"use client";
import { useState, useEffect, useRef } from "react";
import { pantryApi, expiryApi, visionApi } from "@/lib/api";
import { Plus, Trash2, RefreshCw, Upload, AlertTriangle } from "lucide-react";

type PantryEntry = { key: string; item: string; qty: string; unit: string };

function parsePantry(raw: string): PantryEntry[] {
  return raw.split("\n")
    .filter(l => l.trim() && !l.startsWith("Pantry") && !l.startsWith("Empty"))
    .map((line, i) => {
      const clean = line.replace(/^[•\-*]\s*/, "").trim();
      const m = clean.match(/^(.+?)\s*[:\—–-]\s*([\d.]+)\s*(\w+)/);
      if (m) return { key: `${i}`, item: m[1].trim(), qty: m[2], unit: m[3] };
      return { key: `${i}`, item: clean, qty: "", unit: "" };
    }).filter(e => e.item.length > 1);
}

type ExpiryAlert = { item: string; expires: string; days_left: number };

function parseExpiry(raw: string): ExpiryAlert[] {
  return raw.split("\n")
    .map(line => {
      const m = line.match(/(.+?):.*?(\d{4}-\d{2}-\d{2}).*?(\d+)\s*day/i);
      return m ? { item: m[1].trim(), expires: m[2], days_left: parseInt(m[3]) } : null;
    }).filter(Boolean) as ExpiryAlert[];
}

export default function PantryPage() {
  const [pantry, setPantry]     = useState<PantryEntry[]>([]);
  const [expiry, setExpiry]     = useState<ExpiryAlert[]>([]);
  const [loading, setLoading]   = useState(true);
  const [msg, setMsg]           = useState("");
  const [item, setItem]         = useState("");
  const [qty, setQty]           = useState("");
  const [unit, setUnit]         = useState("count");
  const [scanning, setScanning] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const [p, e] = await Promise.all([pantryApi.list(), expiryApi.soon(4)]);
      setPantry(parsePantry(p.result));
      setExpiry(parseExpiry(e.result));
    } finally { setLoading(false); }
  };

  useEffect(() => { refresh(); }, []);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(""), 4000); };

  const handleAdd = async () => {
    if (!item.trim() || !qty) return;
    await pantryApi.add(item.trim().toLowerCase(), parseFloat(qty), unit);
    setItem(""); setQty(""); setUnit("count");
    flash("✅ Added to pantry");
    refresh();
  };

  const handleRemove = async (e: PantryEntry) => {
    await pantryApi.remove(e.item, null, e.unit || "count");
    flash(`🗑 Removed ${e.item}`);
    refresh();
  };

  const handleScan = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setScanning(true);
    try {
      const res = await visionApi.scanAndApply(file);
      flash(`✅ Scanned ${res.scanned} items — ${res.added.length} added (confidence: ${res.confidence})`);
      refresh();
    } catch (err: any) {
      flash(`❌ Scan failed: ${err.message}`);
    } finally {
      setScanning(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Pantry</h1>
        <button onClick={refresh} className="p-1.5 rounded hover:bg-gray-100 text-gray-500" title="Refresh">
          <RefreshCw size={16} />
        </button>
      </div>

      {expiry.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-1">
          <p className="text-sm font-semibold text-amber-800 flex items-center gap-1">
            <AlertTriangle size={14} /> Expiring soon — use these first!
          </p>
          {expiry.map(a => (
            <p key={a.item} className="text-xs text-amber-700">
              {a.item} — {a.expires} ({a.days_left}d left)
            </p>
          ))}
        </div>
      )}

      {msg && (
        <p className="text-sm bg-green-50 border border-green-200 text-green-800 rounded p-2">{msg}</p>
      )}

      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="text-sm font-semibold text-gray-700 mb-3">Add item</p>
        <div className="flex gap-2 flex-wrap">
          <input value={item} onChange={e => setItem(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleAdd()}
            placeholder="e.g. tomato" className="border rounded px-2 py-1.5 text-sm flex-1 min-w-28" />
          <input value={qty} onChange={e => setQty(e.target.value)} type="number" min="0"
            placeholder="Qty" className="border rounded px-2 py-1.5 text-sm w-20" />
          <select value={unit} onChange={e => setUnit(e.target.value)}
            className="border rounded px-2 py-1.5 text-sm">
            {["count","g","ml","kg","l","pack"].map(u => <option key={u}>{u}</option>)}
          </select>
          <button onClick={handleAdd}
            className="bg-green-600 text-white px-3 py-1.5 rounded text-sm flex items-center gap-1 hover:bg-green-700">
            <Plus size={14} /> Add
          </button>
        </div>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="text-sm font-semibold text-gray-700 mb-1">Scan grocery receipt</p>
        <p className="text-xs text-gray-400 mb-3">Upload a photo or PDF — items added automatically via AI vision.</p>
        <input ref={fileRef} type="file" accept="image/*,.pdf" onChange={handleScan} className="hidden" />
        <button onClick={() => fileRef.current?.click()} disabled={scanning}
          className="flex items-center gap-2 bg-blue-600 text-white px-3 py-1.5 rounded text-sm hover:bg-blue-700 disabled:opacity-50">
          <Upload size={14} /> {scanning ? "Scanning…" : "Upload Receipt"}
        </button>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <p className="text-sm font-semibold text-gray-700">Inventory ({pantry.length} items)</p>
        </div>
        {loading ? (
          <p className="p-4 text-sm text-gray-400">Loading…</p>
        ) : pantry.length === 0 ? (
          <p className="p-4 text-sm text-gray-400">Pantry is empty. Add some items above.</p>
        ) : (
          <ul className="divide-y divide-gray-50">
            {pantry.map(e => (
              <li key={e.key} className="flex items-center justify-between px-4 py-2.5 hover:bg-gray-50">
                <div>
                  <span className="text-sm font-medium text-gray-900 capitalize">{e.item}</span>
                  {e.qty && <span className="ml-2 text-xs text-gray-500">{e.qty} {e.unit}</span>}
                </div>
                <button onClick={() => handleRemove(e)} className="text-gray-300 hover:text-red-500 p-1 rounded">
                  <Trash2 size={14} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
