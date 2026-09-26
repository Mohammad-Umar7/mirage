import type { Metadata, Viewport } from "next";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/600.css";
import "@fontsource/sora/300.css";
import "@fontsource/sora/400.css";
import "@fontsource/sora/600.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "MIRAGE — Sybil swarm detection",
  description:
    "Faking one person is cheap. Faking ten thousand independent people isn't. Live coordination detection and correlation-weighted governance.",
};

export const viewport: Viewport = {
  themeColor: "#050403",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
