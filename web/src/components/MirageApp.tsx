"use client";

import dynamic from "next/dynamic";
import { useEffect } from "react";
import { layout } from "@/lib/layoutClient";
import { scene } from "@/lib/sceneData";
import { socket } from "@/lib/socket";
import { useMirage } from "@/lib/store";
import { view } from "@/lib/viewState";
import { Captions } from "./hud/Captions";
import { ConnectionOverlay } from "./hud/ConnectionOverlay";
import { DemoControls } from "./hud/DemoControls";
import { Feed } from "./hud/Feed";
import { Frame } from "./hud/Frame";
import { FxDirector } from "./hud/FxDirector";
import { MetricsStrip } from "./hud/MetricsStrip";
import { OrganicLabels } from "./hud/OrganicLabels";
import { TargetRing } from "./hud/TargetRing";
import { TerrainLegend } from "./hud/TerrainLegend";
import { TopBar } from "./hud/TopBar";
import { AttackerConsole } from "./panels/AttackerConsole";
import { EvidencePanel } from "./panels/EvidencePanel";
import { GovernanceView } from "./panels/GovernanceView";

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
    <main className="fixed inset-0 overflow-clip bg-void select-none">
      <Scene />
      <Frame />
      <OrganicLabels />
      <TargetRing />
      <TerrainLegend />
      <TopBar />
      {/* one left column, so the console and the feed can never overlap */}
      <div className="pointer-events-none absolute bottom-[118px] left-10 top-[132px] z-20 flex w-[330px] flex-col gap-5">
        <AttackerConsole />
        <Feed />
      </div>
      <MetricsStrip />
      <EvidencePanel />
      <GovernanceView />
      <DemoControls />
      <Captions />
      <FxDirector />
      <ConnectionOverlay />
    </main>
  );
}
