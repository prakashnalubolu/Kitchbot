"use client";
import { useState, useEffect, useRef } from "react";
import { chatApi } from "@/lib/api";
import { Send, Bot, User, Wrench, Trash2 } from "lucide-react";

type Message = {
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
  tools?: string[];
};

const WELCOME: Message = {
  role: "assistant",
  text: "Hi! I'm KitchBot 🥘 I can help you plan meals, manage your pantry, find recipes, and track food waste. What would you like to do?",
};

function ToolBadge({ name }: { name: string }) {
  const label: Record<string, string> = {
    list_pantry:          "📦 Reading pantry",
    add_to_pantry:        "📦 Updating pantry",
    remove_from_pantry:   "📦 Updating pantry",
    auto_plan:            "📅 Planning meals",
    get_shopping_list:    "🛒 Building list",
    cook_meal:            "🍳 Marking cooked",
    find_recipes_by_items:"🔍 Matching recipes",
    get_recipe:           "📖 Fetching recipe",
    missing_ingredients:  "🔍 Checking ingredients",
    rate_recipe:          "⭐ Saving rating",
    get_expiring_soon:    "⏰ Checking expiry",
    get_impact_stats:     "🌱 Loading impact",
    suggest_variety:      "🎲 Finding variety",
  };
  return (
    <span className="inline-flex items-center gap-1 text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
      <Wrench size={10} />
      {label[name] ?? name.replace(/_/g, " ")}
    </span>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([WELCOME]);
  const [input, setInput]       = useState("");
  const [sending, setSending]   = useState(false);
  const [activeTools, setActiveTools] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const wsRef     = useRef<WebSocket | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeTools]);

  useEffect(() => {
    return () => { wsRef.current?.close(); };
  }, []);

  const clearChat = () => {
    wsRef.current?.close();
    setMessages([WELCOME]);
    setActiveTools([]);
    setInput("");
    setSending(false);
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setSending(true);
    setActiveTools([]);

    setMessages(prev => [...prev, { role: "user", text }]);

    const wsUrl = chatApi.wsUrl();

    try {
      await new Promise<void>((resolve) => {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        let buffer = "";
        let msgIndex = -1;
        const toolsUsed: string[] = [];

        ws.onopen = () => ws.send(JSON.stringify({ message: text, session_id: "default" }));

        ws.onmessage = (e) => {
          const ev = JSON.parse(e.data);

          if (ev.type === "error") {
            setMessages(prev => [...prev, { role: "assistant", text: `⚠️ ${ev.message}` }]);
            ws.close(); resolve(); return;
          }

          if (ev.type === "tool_start") {
            toolsUsed.push(ev.name);
            setActiveTools([...toolsUsed]);
          }

          if (ev.type === "token") {
            buffer += ev.text;
            if (msgIndex === -1) {
              setMessages(prev => {
                msgIndex = prev.length;
                return [...prev, { role: "assistant", text: buffer, streaming: true, tools: [...toolsUsed] }];
              });
            } else {
              setMessages(prev => {
                const updated = [...prev];
                updated[msgIndex] = { role: "assistant", text: buffer, streaming: true, tools: [...toolsUsed] };
                return updated;
              });
            }
          }

          if (ev.type === "done") {
            const finalText = ev.full || buffer;
            setMessages(prev => {
              const updated = [...prev];
              if (msgIndex === -1) {
                return [...prev, { role: "assistant", text: finalText, tools: [...toolsUsed] }];
              }
              updated[msgIndex] = { role: "assistant", text: finalText, tools: [...toolsUsed] };
              return updated;
            });
            setActiveTools([]);
            ws.close(); resolve();
          }
        };

        ws.onerror = async () => {
          ws.close();
          try {
            const res = await chatApi.send(text);
            setMessages(prev => [...prev, { role: "assistant", text: res.result }]);
          } catch (err: any) {
            setMessages(prev => [...prev, { role: "assistant", text: `❌ ${err.message}` }]);
          }
          resolve();
        };

        ws.onclose = () => resolve();
        setTimeout(() => { ws.close(); resolve(); }, 120_000);
      });
    } finally {
      setSending(false);
      setActiveTools([]);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-gray-900">Chat</h1>
        <button
          onClick={clearChat}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-red-500 px-2 py-1 rounded hover:bg-red-50 transition-colors"
          title="Clear conversation">
          <Trash2 size={13} /> Clear chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-4 mb-4 pr-1">
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-2.5 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
            <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5
              ${m.role === "assistant" ? "bg-green-100 text-green-700" : "bg-blue-100 text-blue-700"}`}>
              {m.role === "assistant" ? <Bot size={14} /> : <User size={14} />}
            </div>
            <div className="max-w-[80%] space-y-1.5">
              {m.tools && m.tools.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {[...new Set(m.tools)].map(t => <ToolBadge key={t} name={t} />)}
                </div>
              )}
              <div className={`px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed
                ${m.role === "assistant"
                  ? "bg-white border border-gray-200 text-gray-800"
                  : "bg-blue-600 text-white"}`}>
                <pre className="whitespace-pre-wrap font-sans">{m.text}</pre>
                {m.streaming && (
                  <span className="inline-block w-1.5 h-3.5 bg-gray-400 ml-1 animate-pulse rounded-sm" />
                )}
              </div>
            </div>
          </div>
        ))}

        {activeTools.length > 0 && (
          <div className="flex gap-1.5 flex-wrap pl-9">
            {[...new Set(activeTools)].map(t => (
              <span key={t} className="inline-flex items-center gap-1 text-xs bg-yellow-50 text-yellow-700 border border-yellow-200 px-2 py-0.5 rounded-full animate-pulse">
                <Wrench size={10} />
                {t.replace(/_/g, " ")}…
              </span>
            ))}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="flex gap-2 items-end">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
          placeholder="Ask KitchBot anything… (Enter to send, Shift+Enter for new line)"
          rows={2}
          disabled={sending}
          className="flex-1 border border-gray-200 rounded-xl px-3.5 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-green-500 disabled:opacity-60"
        />
        <button onClick={sendMessage} disabled={sending || !input.trim()}
          className="bg-green-600 text-white p-2.5 rounded-xl hover:bg-green-700 disabled:opacity-40 flex-shrink-0">
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}
