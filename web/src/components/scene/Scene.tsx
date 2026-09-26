"use client";

import { PerformanceMonitor } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useState } from "react";
import { palette } from "@/lib/palette";
import { CameraRig } from "./CameraRig";
import { ClusterGlow } from "./ClusterGlow";
import { Edges } from "./Edges";
import { Effects } from "./Effects";
import { Halos } from "./Halos";
import { HudSync } from "./HudSync";
import { Nodes } from "./Nodes";
import { Shockwave } from "./Shockwave";
import { Terrain } from "./Terrain";
import { ViewDirector } from "./ViewDirector";

export default function Scene() {
  const [dpr, setDpr] = useState(1.5);
  return (
    <Canvas
      flat
      dpr={dpr}
      gl={{ antialias: false, powerPreference: "high-performance", alpha: false, stencil: false }}
      camera={{ position: [0, 70, 330], fov: 42, near: 1, far: 5000 }}
      style={{ position: "absolute", inset: 0 }}
    >
      <color attach="background" args={[palette.void]} />
      <PerformanceMonitor onDecline={() => setDpr((d) => Math.max(1, d - 0.25))} onIncline={() => setDpr((d) => Math.min(1.75, d + 0.25))} />
      <ViewDirector />
      <ClusterGlow />
      <Edges />
      <Nodes />
      <Halos />
      <Shockwave />
      <Terrain />
      <HudSync />
      <CameraRig />
      <Effects />
    </Canvas>
  );
}
