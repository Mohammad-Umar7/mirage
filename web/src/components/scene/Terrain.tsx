"use client";

import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { palette } from "@/lib/palette";
import type { TerrainLane } from "@/lib/protocol";
import { useMirage } from "@/lib/store";
import { view } from "@/lib/viewState";

export const TERRAIN = { width: 460, depth: 300, height: 34 };
const MAX_LANES = 40;
const BINS = 144;

type Lane = {
  line: Line2;
  mat: LineMaterial;
  ribbon: THREE.Mesh;
  geom: LineGeometry;
  current: Float32Array;
  target: Float32Array;
  kind: TerrainLane["kind"];
  positions: Float32Array;
};

function laneColor(kind: TerrainLane["kind"]) {
  if (kind === "swarm") return new THREE.Color(palette.red);
  if (kind === "organic") return new THREE.Color(palette.goldSoft);
  return new THREE.Color(palette.gold);
}

export function Terrain() {
  const size = useThree((s) => s.size);
  const group = useRef<THREE.Group>(null);
  const terrain = useMirage((s) => s.terrain);

  const ribbonMat = useMemo(
    () => new THREE.MeshBasicMaterial({ color: new THREE.Color(palette.void), side: THREE.DoubleSide, transparent: true, opacity: 1 }),
    [],
  );

  const lanes = useMemo<Lane[]>(() => {
    return Array.from({ length: MAX_LANES }, () => {
      const geom = new LineGeometry();
      const positions = new Float32Array(BINS * 3);
      geom.setPositions(positions);
      const mat = new LineMaterial({ color: new THREE.Color(palette.gold), linewidth: 1.1, transparent: true, worldUnits: false });
      mat.depthTest = true;
      mat.depthWrite = false;
      const line = new Line2(geom, mat);
      line.frustumCulled = false;
      line.renderOrder = 11;
      const rgeo = new THREE.BufferGeometry();
      rgeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(BINS * 2 * 3), 3));
      const idx: number[] = [];
      for (let b = 0; b < BINS - 1; b++) {
        const a = b * 2;
        idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
      }
      rgeo.setIndex(idx);
      const ribbon = new THREE.Mesh(rgeo, ribbonMat);
      ribbon.frustumCulled = false;
      ribbon.renderOrder = 10;
      line.visible = false;
      ribbon.visible = false;
      return { line, mat, ribbon, geom, current: new Float32Array(BINS), target: new Float32Array(BINS), kind: "normal", positions };
    });
  }, [ribbonMat]);

  const grid = useMemo(() => {
    const g = new THREE.GridHelper(TERRAIN.width, 24, new THREE.Color(palette.gold), new THREE.Color("#3a2a12"));
    g.position.set(0, -1.2, 0);
    g.scale.set(1, 1, TERRAIN.depth / TERRAIN.width);
    const mats = Array.isArray(g.material) ? g.material : [g.material];
    for (const m of mats) {
      m.transparent = true;
      m.opacity = 0.14;
      m.depthWrite = false;
    }
    return g;
  }, []);

  useEffect(() => {
    for (const l of lanes) l.mat.resolution.set(size.width, size.height);
  }, [lanes, size]);

  useEffect(() => {
    if (!terrain) return;
    const data = terrain.lanes.slice(0, MAX_LANES);
    lanes.forEach((lane, k) => {
      const d = data[k];
      if (!d) {
        lane.target.fill(0);
        lane.kind = "normal";
        return;
      }
      const vals = d.values;
      const off = Math.max(0, vals.length - BINS);
      for (let b = 0; b < BINS; b++) lane.target[b] = vals[off + b] ?? 0;
      if (lane.kind !== d.kind) {
        lane.kind = d.kind;
        lane.mat.color = laneColor(d.kind);
        lane.mat.linewidth = d.kind === "swarm" ? 2.6 : d.kind === "organic" ? 1.6 : 1.05;
      }
    });
  }, [terrain, lanes]);

  useFrame((_, dt) => {
    const mix = view.terrainMix;
    const g = group.current;
    if (!g) return;
    g.visible = mix > 0.02;
    if (!g.visible) return;
    const count = Math.min(MAX_LANES, terrain?.lanes.length ?? 0);
    const k = 1 - Math.exp(-dt * 3);
    const rise = THREE.MathUtils.smoothstep(mix, 0.2, 1);
    for (let li = 0; li < MAX_LANES; li++) {
      const lane = lanes[li];
      const on = li < count;
      lane.line.visible = on;
      lane.ribbon.visible = on;
      if (!on) continue;
      const z = (li / Math.max(1, count - 1) - 0.5) * TERRAIN.depth;
      const P = lane.positions;
      const R = lane.ribbon.geometry.getAttribute("position") as THREE.BufferAttribute;
      const RA = R.array as Float32Array;
      for (let b = 0; b < BINS; b++) {
        lane.current[b] += (lane.target[b] - lane.current[b]) * k;
        const x = (b / (BINS - 1) - 0.5) * TERRAIN.width;
        const h = lane.current[b] * TERRAIN.height * rise;
        P[b * 3] = x;
        P[b * 3 + 1] = h + 0.25;
        P[b * 3 + 2] = z;
        RA[b * 6] = x; RA[b * 6 + 1] = h; RA[b * 6 + 2] = z + 0.1;
        RA[b * 6 + 3] = x; RA[b * 6 + 4] = -1; RA[b * 6 + 5] = z + 0.1;
      }
      // update segment endpoints in place (setPositions would reallocate every frame)
      const seg = lane.geom.getAttribute("instanceStart") as THREE.InterleavedBufferAttribute;
      const SA = seg.data.array as Float32Array;
      for (let b = 0; b < BINS - 1; b++) {
        const o = b * 6, a = b * 3;
        SA[o] = P[a]; SA[o + 1] = P[a + 1]; SA[o + 2] = P[a + 2];
        SA[o + 3] = P[a + 3]; SA[o + 4] = P[a + 4]; SA[o + 5] = P[a + 5];
      }
      seg.data.needsUpdate = true;
      R.needsUpdate = true;
      lane.mat.opacity = (lane.kind === "normal" ? 0.62 : 1) * mix;
    }
    ribbonMat.opacity = mix;
  });

  return (
    <group ref={group} visible={false}>
      {lanes.map((l, i) => (
        <group key={i}>
          <primitive object={l.ribbon} />
          <primitive object={l.line} />
        </group>
      ))}
      <primitive object={grid} />
    </group>
  );
}
