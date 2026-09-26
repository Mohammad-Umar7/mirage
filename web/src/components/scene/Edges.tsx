"use client";

import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { palette } from "@/lib/palette";
import { now, scene } from "@/lib/sceneData";
import { view } from "@/lib/viewState";
import { edgeFragment, edgeVertex } from "./shaders";

const GOLD = new THREE.Color(palette.gold);
const GOLD_SOFT = new THREE.Color(palette.goldSoft);
const RED = new THREE.Color(palette.red);

type Plan = {
  gold: Int32Array; // pairs (i, j) flattened
  goldCount: number;
  red: Int32Array;
  redCount: number;
  redAppear: Float32Array; // per red segment: when it snaps in
};

function plan(): Plan {
  const { i, j, w } = scene.edges;
  const verdict = new Map(scene.clusters.map((c) => [c.id, c]));
  const gold: number[] = [];
  const red: number[] = [];
  const appear: number[] = [];
  const goldAlpha: number[] = [];
  const goldColor: number[] = [];
  for (let e = 0; e < i.length; e++) {
    const a = i[e], b = j[e];
    if (a >= scene.n || b >= scene.n) continue;
    const ca = scene.clusterOf[a];
    const c = ca >= 0 && ca === scene.clusterOf[b] ? verdict.get(ca) : undefined;
    if (c && c.verdict === "SWARM" && c.confidence >= 0.55) {
      red.push(a, b);
      appear.push(c.firstSeen + 0.4 + Math.random() * 1.1);
    } else {
      gold.push(a, b);
      const organic = c && c.verdict === "ORGANIC COMMUNITY";
      goldAlpha.push(organic ? 0.34 : Math.min(0.2, 0.045 + 0.09 * w[e]));
      goldColor.push(organic ? 1 : 0);
    }
  }
  planAlpha = new Float32Array(goldAlpha);
  planColor = new Uint8Array(goldColor);
  return {
    gold: new Int32Array(gold), goldCount: gold.length / 2,
    red: new Int32Array(red), redCount: red.length / 2, redAppear: new Float32Array(appear),
  };
}
let planAlpha = new Float32Array(0);
let planColor = new Uint8Array(0);

export function Edges() {
  const size = useThree((s) => s.size);
  const seen = useRef({ edges: -1, clusters: -1 });
  const current = useRef<Plan | null>(null);
  const redSnapDone = useRef(false);

  const goldGeom = useMemo(() => new THREE.BufferGeometry(), []);
  const goldMat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: edgeVertex,
        fragmentShader: edgeFragment,
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending,
        uniforms: { uFocus: { value: 330 }, uDim: { value: 1 } },
      }),
    [],
  );
  const goldLines = useMemo(() => {
    const l = new THREE.LineSegments(goldGeom, goldMat);
    l.frustumCulled = false;
    l.renderOrder = 1;
    return l;
  }, [goldGeom, goldMat]);

  const redGeom = useMemo(() => new LineSegmentsGeometry(), []);
  const redMat = useMemo(() => {
    const m = new LineMaterial({
      color: 0xffffff,
      linewidth: 1.7,
      vertexColors: true,
      transparent: true,
      depthWrite: false,
      depthTest: false,
      worldUnits: false,
    });
    m.blending = THREE.AdditiveBlending;
    return m;
  }, []);
  const redLines = useMemo(() => {
    const l = new LineSegments2(redGeom, redMat);
    l.frustumCulled = false;
    l.renderOrder = 3;
    return l;
  }, [redGeom, redMat]);

  useEffect(() => {
    redMat.resolution.set(size.width, size.height);
  }, [size, redMat]);

  useEffect(() => () => {
    goldGeom.dispose();
    goldMat.dispose();
    redGeom.dispose();
    redMat.dispose();
  }, [goldGeom, goldMat, redGeom, redMat]);

  useFrame(() => {
    const s = seen.current;
    if (s.edges !== scene.edges.version || s.clusters !== scene.clusterVersion) {
      const p = plan();
      current.current = p;
      s.edges = scene.edges.version;
      s.clusters = scene.clusterVersion;
      goldGeom.setAttribute("position", new THREE.BufferAttribute(new Float32Array(p.goldCount * 6), 3));
      const alpha = new Float32Array(p.goldCount * 2);
      const color = new Float32Array(p.goldCount * 6);
      for (let e = 0; e < p.goldCount; e++) {
        alpha[e * 2] = alpha[e * 2 + 1] = planAlpha[e];
        const c = planColor[e] ? GOLD_SOFT : GOLD;
        color.set([c.r, c.g, c.b, c.r, c.g, c.b], e * 6);
      }
      goldGeom.setAttribute("aAlpha", new THREE.BufferAttribute(alpha, 1));
      goldGeom.setAttribute("aColor", new THREE.BufferAttribute(color, 3));
      if (p.redCount > 0) {
        redGeom.setPositions(new Float32Array(p.redCount * 6));
        redGeom.setColors(new Float32Array(p.redCount * 6));
      }
      redLines.visible = p.redCount > 0;
      redSnapDone.current = false;
    }
    const p = current.current;
    if (!p) return;
    const P = scene.positions;
    const gp = goldGeom.getAttribute("position") as THREE.BufferAttribute;
    const ga = gp.array as Float32Array;
    for (let e = 0; e < p.goldCount; e++) {
      const a = p.gold[e * 2] * 3, b = p.gold[e * 2 + 1] * 3, o = e * 6;
      ga[o] = P[a]; ga[o + 1] = P[a + 1]; ga[o + 2] = P[a + 2];
      ga[o + 3] = P[b]; ga[o + 4] = P[b + 1]; ga[o + 5] = P[b + 2];
    }
    gp.needsUpdate = true;
    goldMat.uniforms.uFocus.value = view.focusDepth;
    goldMat.uniforms.uDim.value = view.dim * (1 - view.terrainMix);
    goldLines.visible = view.terrainMix < 0.98;

    if (p.redCount > 0) {
      const start = redGeom.getAttribute("instanceStart") as THREE.InterleavedBufferAttribute;
      const arr = start.data.array as Float32Array;
      for (let e = 0; e < p.redCount; e++) {
        const a = p.red[e * 2] * 3, b = p.red[e * 2 + 1] * 3, o = e * 6;
        arr[o] = P[a]; arr[o + 1] = P[a + 1]; arr[o + 2] = P[a + 2];
        arr[o + 3] = P[b]; arr[o + 4] = P[b + 1]; arr[o + 5] = P[b + 2];
      }
      start.data.needsUpdate = true;
      if (!redSnapDone.current) {
        const t = now();
        const colors = (redGeom.getAttribute("instanceColorStart") as THREE.InterleavedBufferAttribute).data;
        const carr = colors.array as Float32Array;
        let pending = false;
        for (let e = 0; e < p.redCount; e++) {
          const k = Math.min(1, Math.max(0, (t - p.redAppear[e]) / 0.35));
          if (k < 1) pending = true;
          // snap: flare bright then settle
          const flare = k < 1 ? k * (1 + 1.5 * (1 - k)) : 1;
          const r = RED.r * 0.95 * flare, g = RED.g * 0.95 * flare + 0.05 * flare, bl = RED.b * 0.9 * flare;
          carr[e * 6] = r; carr[e * 6 + 1] = g; carr[e * 6 + 2] = bl;
          carr[e * 6 + 3] = r; carr[e * 6 + 4] = g; carr[e * 6 + 5] = bl;
        }
        colors.needsUpdate = true;
        if (!pending) redSnapDone.current = true;
      }
      redMat.opacity = 0.55 * view.dim * (1 - view.terrainMix);
      redLines.visible = view.terrainMix < 0.98;
    }
  });

  return (
    <>
      <primitive object={goldLines} />
      <primitive object={redLines} />
    </>
  );
}
