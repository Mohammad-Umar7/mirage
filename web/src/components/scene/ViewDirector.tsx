"use client";

import { useFrame } from "@react-three/fiber";
import { useMirage } from "@/lib/store";
import { kickAberration, view } from "@/lib/viewState";

// Eases global view parameters toward the current UI view.
export function ViewDirector() {
  useFrame((_, dt) => {
    const st = useMirage.getState();
    const wantTerrain = st.view === "terrain" ? 1 : 0;
    const wantDim = st.view === "governance" ? 0.28 : st.selected !== null ? 0.82 : 1;
    const k = 1 - Math.exp(-dt * 2.2);
    const before = view.terrainMix;
    view.terrainMix += (wantTerrain - view.terrainMix) * k;
    if (Math.abs(view.terrainMix - wantTerrain) < 0.002) view.terrainMix = wantTerrain;
    if ((before < 0.5) !== (view.terrainMix < 0.5)) kickAberration(1);
    view.dim += (wantDim - view.dim) * k;
  });
  return null;
}
