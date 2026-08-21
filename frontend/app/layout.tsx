import type { Metadata } from "next";
import { Inter, Playfair_Display } from "next/font/google";
import { QueryProvider } from "@/components/providers/QueryProvider";
import "./globals.css";
const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const playfair = Playfair_Display({ subsets: ["latin"], variable: "--font-playfair" });
export const metadata: Metadata = { title: "JewelPass", description: "Verified digital passports for exceptional jewelry", manifest: "/manifest.json", themeColor: "#c9a84c" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" className={`${inter.variable} ${playfair.variable}`}><body><QueryProvider>{children}</QueryProvider></body></html>;
}
