import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import QueryProvider from "./components/query-provider";
import AppShell from "./components/app-shell";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const jetBrainsMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "GraphGuard // Mission Control",
  description: "Evidence-grounded fraud investigation and safe response operations.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${jetBrainsMono.variable}`}><QueryProvider><AppShell>{children}</AppShell></QueryProvider></body>
    </html>
  );
}
