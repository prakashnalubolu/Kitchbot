"use client";
import { useState, useEffect, useRef } from "react";
import { pantryApi, expiryApi, visionApi, ScannedItem } from "@/lib/api";
import { Plus, Trash2, RefreshCw, Upload, AlertTriangle, X, Check, Search, Edit2, Calendar } from "lucide-react";

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

// Backend format examples:
//   "- **Milk** — expires in 3 days (2026-05-01)"
//   "- **Eggs** — expires tomorrow"
//   "- **Butter** — expires TODAY"
//   "- **Yogurt** — expired 2 day(s) ago!"
function parseExpiry(raw: string): ExpiryAlert[] {
  const today = new Date();
  const dateStr = (d: Date) => d.toISOString().slice(0, 10);

  return raw.split("\n").map(line => {
    const clean = line.replace(/^[•\-*]\s*/, "").replace(/\*\*/g, "").trim();
    if (!clean || clean.startsWith("⚠️") || clean.startsWith("✅") || clean.startsWith("**Use")) return null;

    // "Item — expires in N days (YYYY-MM-DD)"
    let m = clean.match(/^(.+?)\s*[—–-]\s*expires in (\d+) days?\s*\((\d{4}-\d{2}-\d{2})\)/i);
    if (m) return { item: m[1].trim(), expires: m[3], days_left: parseInt(m[2]) };

    // "Item — expires tomorrow"
    m = clean.match(/^(.+?)\s*[—–-]\s*expires tomorrow/i);
    if (m) {
      const d = new Date(today); d.setDate(d.getDate() + 1);
      return { item: m[1].trim(), expires: dateStr(d), days_left: 1 };
    }

    // "Item — expires TODAY"
    m = clean.match(/^(.+?)\s*[—–-]\s*expires today/i);
    if (m) return { item: m[1].trim(), expires: dateStr(today), days_left: 0 };

    // "Item — expired N day(s) ago"
    m = clean.match(/^(.+?)\s*[—–-]\s*expired (\d+) day/i);
    if (m) {
      const n = parseInt(m[2]);
      const d = new Date(today); d.setDate(d.getDate() - n);
      return { item: m[1].trim(), expires: dateStr(d), days_left: -n };
    }

    return null;
  }).filter(Boolean) as ExpiryAlert[];
}

const UNITS = ["count", "g", "ml", "kg", "l", "pack"];

function ReceiptConfirmModal({
  items, confidence, onConfirm, onCancel,
}: {
  items: ScannedItem[];
  confidence: string;
  onConfirm: (items: ScannedItem[]) => void;
  onCancel: () => void;
}) {
  const [rows, setRows] = useState<ScannedItem[]>(items);
  const update = (i: number, field: keyof ScannedItem, value: string | number) =>
    setRows(r => r.map((row, idx) => idx === i ? { ...row, [field]: value } : row));
  const remove = (i: number) => setRows(r => r.filter((_, idx) => idx !== i));
  const confidenceColor =
    confidence === "high"   ? "text-green-700 bg-green-50 border-green-200" :
    confidence === "medium" ? "text-amber-700 bg-amber-50 border-amber-200" :
                              "text-red-700 bg-red-50 border-red-200";
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Receipt Scanned</h2>
            <span className={`text-xs font-medium px-2 py-0.5 rounded border mt-1 inline-block ${confidenceColor}`}>
              {confidence} confidence
            </span>
          </div>
          <button onClick={onCancel} className="text-gray-400 hover:text-gray-600 p-1 rounded"><X size={18} /></button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-3 space-y-2">
          {rows.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-6">No items — try a clearer image.</p>
          )}
          {rows.map((row, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-sm text-gray-800 flex-1 capitalize">{row.item}</span>
              <input type="number" min="0" step="any" value={row.quantity}
                onChange={e => update(i, "quantity", parseFloat(e.target.value) || 0)}
                className="border rounded px-2 py-1 text-sm w-20 text-center" />
              <select value={row.unit} onChange={e => update(i, "unit", e.target.value)}
                className="border rounded px-2 py-1 text-sm">
                {UNITS.map(u => <option key={u}>{u}</option>)}
              </select>
              <button onClick={() => remove(i)} className="text-gray-300 hover:text-red-500 p-1 rounded">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
        <div className="px-5 py-4 border-t border-gray-100 flex items-center justify-between gap-3">
          <p className="text-xs text-gray-400">{rows.length} item{rows.length !== 1 ? "s" : ""} — edit or remove before adding</p>
          <div className="flex gap-2">
            <button onClick={onCancel}
              className="px-3 py-1.5 rounded text-sm border border-gray-200 text-gray-600 hover:bg-gray-50">
              Cancel
            </button>
            <button onClick={() => onConfirm(rows)} disabled={rows.length === 0}
              className="px-4 py-1.5 rounded text-sm bg-green-600 text-white hover:bg-green-700 disabled:opacity-40 flex items-center gap-1.5">
              <Check size={14} /> Add {rows.length} to Pantry
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

type EditEntry   = { key: string; qty: string; unit: string };
type ExpiryEdit  = { key: string; item: string; date: string };

export default function PantryPage() {
  const [pantry, setPantry]         = useState<PantryEntry[]>([]);
  const [expiryAlerts, setExpiryAlerts] = useState<ExpiryAlert[]>([]);
  const [expiryMap, setExpiryMap]   = useState<Record<string, string>>({});   // item.lower → YYYY-MM-DD
  const [loading, setLoading]       = useState(true);
  const [msg, setMsg]               = useState("");
  const [item, setItem]             = useState("");
  const [qty, setQty]               = useState("");
  const [unit, setUnit]             = useState("count");
  const [scanning, setScanning]     = useState(false);
  const [scanned, setScanned]       = useState<{ items: ScannedItem[]; confidence: string } | null>(null);
  const [applying, setApplying]     = useState(false);
  const [search, setSearch]         = useState("");
  const [confirmKey, setConfirmKey] = useState<string | null>(null);
  const [editEntry, setEditEntry]   = useState<EditEntry | null>(null);
  const [expiryEdit, setExpiryEdit] = useState<ExpiryEdit | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      // Fetch pantry + all expiry data (within_days=3650 ≈ all items)
      const [p, e] = await Promise.all([pantryApi.list(), expiryApi.soon(3650)]);
      setPantry(parsePantry(p.result));
      const allExpiry = parseExpiry(e.result);
      // Build item→date map
      const map: Record<string, string> = {};
      allExpiry.forEach(a => { map[a.item.toLowerCase()] = a.expires; });
      setExpiryMap(map);
      // Alerts = expiring within 7 days
      setExpiryAlerts(allExpiry.filter(a => a.days_left <= 7));
    } finally { setLoading(false); }
  };

  useEffect(() => { refresh(); }, []);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(""), 4000); };

  const handleAdd = async () => {
    if (!item.trim() || !qty) return;
    await pantryApi.add(item.trim().toLowerCase(), parseFloat(qty), unit);
    setItem(""); setQty(""); setUnit("count");
    flash("Added to pantry");
    refresh();
  };

  const handleRemove = async (e: PantryEntry) => {
    await pantryApi.remove(e.item, null, e.unit || "count");
    setConfirmKey(null);
    flash(`Removed ${e.item}`);
    refresh();
  };

  const handleUpdate = async () => {
    if (!editEntry) return;
    const entry = pantry.find(e => e.key === editEntry.key);
    if (!entry) return;
    await pantryApi.update(entry.item, parseFloat(editEntry.qty) || 0, editEntry.unit);
    setEditEntry(null);
    flash(`Updated ${entry.item}`);
    refresh();
  };

  const handleSetExpiry = async () => {
    if (!expiryEdit || !expiryEdit.date) return;
    await expiryApi.set(expiryEdit.item, expiryEdit.date);
    setExpiryEdit(null);
    flash(`Expiry set for ${expiryEdit.item}`);
    refresh();
  };

  const handleRemoveExpiry = async (itemName: string) => {
    await expiryApi.remove(itemName);
    setExpiryEdit(null);
    flash(`Expiry removed for ${itemName}`);
    refresh();
  };

  const handleScan = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setScanning(true);
    try {
      const res = await visionApi.scan(file);
      setScanned(res);
    } catch (err: any) {
      flash(`Scan failed: ${err.message}`);
    } finally {
      setScanning(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleConfirm = async (items: ScannedItem[]) => {
    setScanned(null);
    setApplying(true);
    let added = 0, failed = 0;
    for (const entry of items) {
      try { await pantryApi.add(entry.item, entry.quantity, entry.unit); added++; }
      catch { failed++; }
    }
    setApplying(false);
    flash(failed > 0 ? `Added ${added} items — ${failed} failed` : `Added ${added} items from receipt`);
    refresh();
  };

  const duplicate = item.trim()
    ? pantry.find(e => e.item.toLowerCase() === item.trim().toLowerCase())
    : null;

  const filtered = pantry.filter(e =>
    e.item.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-5">
      {scanned && (
        <ReceiptConfirmModal
          items={scanned.items}
          confidence={scanned.confidence}
          onConfirm={handleConfirm}
          onCancel={() => { setScanned(null); if (fileRef.current) fileRef.current.value = ""; }}
        />
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Pantry</h1>
        <button onClick={refresh} className="p-1.5 rounded hover:bg-gray-100 text-gray-500" title="Refresh">
          <RefreshCw size={16} />
        </button>
      </div>

      {expiryAlerts.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-1">
          <p className="text-sm font-semibold text-amber-800 flex items-center gap-1">
            <AlertTriangle size={14} /> Expiring soon — use these first!
          </p>
          {expiryAlerts.map(a => (
            <p key={a.item} className="text-xs text-amber-700">
              {a.item} — {a.expires}
              {a.days_left < 0
                ? ` (expired ${Math.abs(a.days_left)}d ago)`
                : a.days_left === 0 ? " (today!)" : a.days_left === 1 ? " (tomorrow)" : ` (${a.days_left}d left)`}
            </p>
          ))}
        </div>
      )}

      {msg && (
        <p className="text-sm bg-green-50 border border-green-200 text-green-800 rounded p-2">{msg}</p>
      )}

      {/* Add item */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="text-sm font-semibold text-gray-700 mb-3">Add item</p>
        <div className="flex gap-2 flex-wrap">
          <div className="flex-1 min-w-28">
            <input value={item} onChange={e => setItem(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleAdd()}
              placeholder="e.g. tomato"
              className="border rounded px-2 py-1.5 text-sm w-full" />
            {duplicate && (
              <p className="text-xs text-amber-600 mt-1 flex items-center gap-1">
                <AlertTriangle size={11} />
                Already in pantry: {duplicate.qty} {duplicate.unit}
              </p>
            )}
          </div>
          <input value={qty} onChange={e => setQty(e.target.value)} type="number" min="0"
            placeholder="Qty" className="border rounded px-2 py-1.5 text-sm w-20" />
          <select value={unit} onChange={e => setUnit(e.target.value)}
            className="border rounded px-2 py-1.5 text-sm">
            {UNITS.map(u => <option key={u}>{u}</option>)}
          </select>
          <button onClick={handleAdd}
            className="bg-green-600 text-white px-3 py-1.5 rounded text-sm flex items-center gap-1 hover:bg-green-700">
            <Plus size={14} /> Add
          </button>
        </div>
      </div>

      {/* Receipt scan */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="text-sm font-semibold text-gray-700 mb-1">Scan grocery receipt</p>
        <p className="text-xs text-gray-400 mb-3">Upload a photo or PDF — review items before adding to pantry.</p>
        <input ref={fileRef} type="file" accept="image/*,.pdf" onChange={handleScan} className="hidden" />
        <button onClick={() => fileRef.current?.click()} disabled={scanning || applying}
          className="flex items-center gap-2 bg-blue-600 text-white px-3 py-1.5 rounded text-sm hover:bg-blue-700 disabled:opacity-50">
          <Upload size={14} />
          {scanning ? "Scanning…" : applying ? "Adding…" : "Upload Receipt"}
        </button>
      </div>

      {/* Inventory */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 space-y-2">
          <p className="text-sm font-semibold text-gray-700">
            Inventory ({filtered.length}{search ? ` of ${pantry.length}` : ""} items)
          </p>
          {pantry.length > 4 && (
            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
              <input value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Filter items…"
                className="w-full border rounded pl-7 pr-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-green-400" />
            </div>
          )}
        </div>

        {loading ? (
          <p className="p-4 text-sm text-gray-400">Loading…</p>
        ) : pantry.length === 0 ? (
          <p className="p-4 text-sm text-gray-400">Pantry is empty. Add some items above.</p>
        ) : filtered.length === 0 ? (
          <p className="p-4 text-sm text-gray-400">No items match "{search}".</p>
        ) : (
          <ul className="divide-y divide-gray-50">
            {filtered.map(e => {
              const itemExp = expiryMap[e.item.toLowerCase()];
              return (
                <li key={e.key}>
                  {confirmKey === e.key ? (
                    /* Delete confirmation */
                    <div className="flex items-center justify-between px-4 py-2.5 bg-red-50">
                      <p className="text-sm text-red-700">Remove <strong>{e.item}</strong>?</p>
                      <div className="flex gap-2">
                        <button onClick={() => setConfirmKey(null)}
                          className="text-xs px-3 py-1 rounded border border-gray-300 text-gray-600 hover:bg-white">
                          Cancel
                        </button>
                        <button onClick={() => handleRemove(e)}
                          className="text-xs px-3 py-1 rounded bg-red-600 text-white hover:bg-red-700">
                          Remove
                        </button>
                      </div>
                    </div>
                  ) : editEntry?.key === e.key ? (
                    /* Quantity edit */
                    <div className="flex items-center gap-2 px-4 py-2.5 bg-blue-50">
                      <span className="text-sm font-medium text-gray-900 capitalize flex-1">{e.item}</span>
                      <input type="number" min="0" value={editEntry.qty}
                        onChange={ev => setEditEntry({ ...editEntry, qty: ev.target.value })}
                        className="border rounded px-2 py-1 text-sm w-20 text-center" />
                      <select value={editEntry.unit}
                        onChange={ev => setEditEntry({ ...editEntry, unit: ev.target.value })}
                        className="border rounded px-2 py-1 text-sm">
                        {UNITS.map(u => <option key={u}>{u}</option>)}
                      </select>
                      <button onClick={handleUpdate}
                        className="text-xs px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-700">Save</button>
                      <button onClick={() => setEditEntry(null)}
                        className="text-xs px-3 py-1 rounded border border-gray-300 text-gray-600 hover:bg-white">Cancel</button>
                    </div>
                  ) : expiryEdit?.key === e.key ? (
                    /* Expiry date edit */
                    <div className="flex items-center gap-2 px-4 py-2.5 bg-amber-50">
                      <span className="text-sm font-medium text-gray-900 capitalize flex-1">{e.item}</span>
                      <input type="date" value={expiryEdit.date}
                        onChange={ev => setExpiryEdit({ ...expiryEdit, date: ev.target.value })}
                        className="border rounded px-2 py-1 text-sm" />
                      <button onClick={handleSetExpiry} disabled={!expiryEdit.date}
                        className="text-xs px-3 py-1 rounded bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-40">
                        Set
                      </button>
                      {itemExp && (
                        <button onClick={() => handleRemoveExpiry(e.item)}
                          className="text-xs px-3 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50">
                          Remove
                        </button>
                      )}
                      <button onClick={() => setExpiryEdit(null)}
                        className="text-xs px-3 py-1 rounded border border-gray-300 text-gray-600 hover:bg-white">Cancel</button>
                    </div>
                  ) : (
                    /* Normal row */
                    <div className="flex items-center justify-between px-4 py-2.5 hover:bg-gray-50">
                      <div>
                        <span className="text-sm font-medium text-gray-900 capitalize">{e.item}</span>
                        {e.qty && <span className="ml-2 text-xs text-gray-500">{e.qty} {e.unit}</span>}
                        {itemExp && (
                          <span className="ml-2 text-xs text-amber-600 inline-flex items-center gap-0.5">
                            <Calendar size={10} /> {itemExp}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-0.5">
                        <button
                          onClick={() => setExpiryEdit({ key: e.key, item: e.item, date: itemExp || "" })}
                          className="text-gray-300 hover:text-amber-500 p-1 rounded" title="Set expiry date">
                          <Calendar size={13} />
                        </button>
                        <button
                          onClick={() => setEditEntry({ key: e.key, qty: e.qty || "1", unit: e.unit || "count" })}
                          className="text-gray-300 hover:text-blue-500 p-1 rounded" title="Edit quantity">
                          <Edit2 size={13} />
                        </button>
                        <button onClick={() => setConfirmKey(e.key)}
                          className="text-gray-300 hover:text-red-500 p-1 rounded" title="Remove">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
