"use client";

import dynamic from "next/dynamic";
import { useEffect } from "react";
import { layout } from "@/lib/layoutClient";
import { scene } from "@/lib/sceneData";
import { socket } from "@/lib/socket";
import { useMirage } from "@/lib/store";
import { view } from "@/lib/viewState";
import { ConnectionOverlay } from "./hud/ConnectionOverlay";
import { Feed } from "./hud/Feed";
import { Frame } from "./hud/Frame";
import { MetricsStrip } from "./hud/MetricsStrip";
import { OrganicLabels } from "./hud/OrganicLabels";
import { TargetRing } from "./hud/TargetRing";
import { TopBar } from "./hud/TopBar";
import { AttackerConsole } from "./panels/AttackerConsole";

const Scene = dynamic(() => import("./scene/Scene"), { ssr: false });

export default function MirageApp() {
  useEffect(() => {
    layout.start();
    socket.start();
    if (process.env.NODE_ENV !== "production") {
      (window as unknown as Record<string, unknown>).__mirage = { scene, view, store: useMirage };
    }
  }, []);

  return (
    <main className="fixed inset-0 overflow-hidden bg-void select-none">
      <Scene />
      <Frame />
      <OrganicLabels />
      <TargetRing />
      <TopBar />
      <AttackerConsole />
      <Feed />
      <MetricsStrip />
      <ConnectionOverlay />
    </main>
  );
}
