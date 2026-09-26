"use client";

import dynamic from "next/dynamic";
import { useEffect } from "react";
import { layout } from "@/lib/layoutClient";
import { socket } from "@/lib/socket";
import { ConnectionOverlay } from "./hud/ConnectionOverlay";
import { Frame } from "./hud/Frame";
import { MetricsStrip } from "./hud/MetricsStrip";
import { OrganicLabels } from "./hud/OrganicLabels";
import { TargetRing } from "./hud/TargetRing";
import { TopBar } from "./hud/TopBar";

const Scene = dynamic(() => import("./scene/Scene"), { ssr: false });

export default function MirageApp() {
  useEffect(() => {
    layout.start();
    socket.start();
  }, []);

  return (
    <main className="fixed inset-0 overflow-hidden bg-void select-none">
      <Scene />
      <Frame />
      <OrganicLabels />
      <TargetRing />
      <TopBar />
      <MetricsStrip />
      <ConnectionOverlay />
    </main>
  );
}
