import type { Metadata } from "next";
import { Instrument_Sans, JetBrains_Mono, Pixelify_Sans } from "next/font/google";
import "./globals.css";

const sans = Instrument_Sans({ subsets: ["latin"], variable: "--font-instrument" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains" });
const pixel = Pixelify_Sans({ subsets: ["latin"], variable: "--font-pixelify" }); // the village

export const metadata: Metadata = {
  title: "Agent Lab",
  description: "Watch hand-built agents work, step by step.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} ${pixel.variable}`}>
      <body className="bg-paper font-sans text-ink antialiased">{children}</body>
    </html>
  );
}
