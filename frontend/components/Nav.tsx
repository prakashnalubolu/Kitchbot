"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ShoppingBasket, CalendarDays, MessageSquare, History, Leaf } from "lucide-react";

const links = [
  { href: "/",        label: "Pantry",    Icon: ShoppingBasket },
  { href: "/plan",    label: "Meal Plan", Icon: CalendarDays },
  { href: "/chat",    label: "Chat",      Icon: MessageSquare },
  { href: "/history", label: "History",   Icon: History },
  { href: "/impact",  label: "Impact",    Icon: Leaf },
];

export default function Nav() {
  const path = usePathname();
  return (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
      <div className="max-w-5xl mx-auto px-4 flex items-center h-14">
        {/* Logo — hidden on very small screens to save space */}
        <span className="font-bold text-green-700 text-lg mr-4 hidden sm:block">🥘 KitchBot</span>
        <span className="font-bold text-green-700 text-base mr-3 sm:hidden">🥘</span>

        <nav className="flex items-center gap-0.5 sm:gap-1 flex-1">
          {links.map(({ href, label, Icon }) => {
            const active = path === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-1.5 px-2 sm:px-3 py-1.5 rounded-md text-sm font-medium transition-colors
                  ${active
                    ? "bg-green-100 text-green-800"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"}`}
              >
                <Icon size={16} className="flex-shrink-0" />
                {/* Label visible on sm+ */}
                <span className="hidden sm:inline">{label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
