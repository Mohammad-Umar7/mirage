import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // the dev badge sits on top of the HUD frame; the app has its own status UI
  devIndicators: false,
  // pin the workspace root to web/ so stray lockfiles higher up are never picked up
  turbopack: { root: process.cwd() },
};

export default nextConfig;
