import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import Nav from "@/components/Nav";

const geist = Geist({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "KitchBot — Meal Planning Assistant",
  description: "Open-source meal planning assistant powered by local AI",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className={`${geist.className} bg-gray-50 min-h-screen`}>
        <Nav />
        <main className="max-w-5xl mx-auto px-3 sm:px-4 py-4 sm:py-6">{children}</main>
      </body>
    </html>
  );
}
