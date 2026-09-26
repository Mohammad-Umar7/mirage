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
const FADE_NEAR = 12;
const FADE_FAR = 42;
const RED_NEAR = 40;
const RED_FAR = 85;

type Plan = {
  gold: Int32Array; // pairs (i, j) flattened
  goldCount: number;
  goldAlpha: Float32Array;
  goldOrganic: Uint8Array;
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
      goldAlpha.push(organic ? 0.3 : Math.min(0.22, 0.06 + 0.1 * w[e]));
      goldColor.push(organic ? 1 : 0);
    }
  }
  planAlpha = new Float32Array(goldAlpha);
  planColor = new Uint8Array(goldColor);
  return {
    gold: new Int32Array(gold), goldCount: gold.length / 2, goldAlpha: planAlpha, goldOrganic: planColor,
    red: new Int32Array(red), redCount: red.length / 2, redAppear: new Float32Array(appear),
  };
}
let planAlpha = new Float32Array(0);
let planColor = new Uint8Array(0);

export function Edges() {
  const size = useThree((s) => s.size);
  const seen = useRef({ edges: -1, clusters: -1 });
  const current = useRef<Plan | null>(null);

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
    // fast refresh can hand us fresh geometries with a stale "seen" record
    if (!goldGeom.getAttribute("aAlpha")) s.edges = -1;
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
    }
    const p = current.current;
    if (!p) return;
    const P = scene.positions;
    const gp = goldGeom.getAttribute("position") as THREE.BufferAttribute;
    const ga = gp.array as Float32Array;
    const al = goldGeom.getAttribute("aAlpha") as THREE.BufferAttribute;
    const aa = al.array as Float32Array;
    for (let e = 0; e < p.goldCount; e++) {
      const a = p.gold[e * 2] * 3, b = p.gold[e * 2 + 1] * 3, o = e * 6;
      ga[o] = P[a]; ga[o + 1] = P[a + 1]; ga[o + 2] = P[a + 2];
      ga[o + 3] = P[b]; ga[o + 4] = P[b + 1]; ga[o + 5] = P[b + 2];
      // long lines between far-apart accounts read as clutter: fade them by length
      const dx = P[b] - P[a], dy = P[b + 1] - P[a + 1], dz = P[b + 2] - P[a + 2];
      const len = Math.sqrt(dx * dx + dy * dy + dz * dz);
      const k = p.goldOrganic[e]
        ? Math.min(1, Math.max(0, (60 - len) / 35))
        : Math.min(1, Math.max(0, (FADE_FAR - len) / (FADE_FAR - FADE_NEAR)));
      aa[e * 2] = aa[e * 2 + 1] = p.goldAlpha[e] * k;
    }
    gp.needsUpdate = true;
    al.needsUpdate = true;
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
      const t = now();
      const colors = (redGeom.getAttribute("instanceColorStart") as THREE.InterleavedBufferAttribute).data;
      const carr = colors.array as Float32Array;
      for (let e = 0; e < p.redCount; e++) {
        const k = Math.min(1, Math.max(0, (t - p.redAppear[e]) / 0.35));
        // snap: flare bright then settle
        const flare = k < 1 ? k * (1 + 1.5 * (1 - k)) : 1;
        // edges to accounts still gliding in would draw long spikes: fade by length
        const o = e * 6;
        const dx = arr[o + 3] - arr[o], dy = arr[o + 4] - arr[o + 1], dz = arr[o + 5] - arr[o + 2];
        const len = Math.sqrt(dx * dx + dy * dy + dz * dz);
        const f = flare * Math.min(1, Math.max(0, (RED_FAR - len) / (RED_FAR - RED_NEAR)));
        const r = RED.r * 0.95 * f, g = RED.g * 0.95 * f + 0.05 * f, bl = RED.b * 0.9 * f;
        carr[o] = r; carr[o + 1] = g; carr[o + 2] = bl;
        carr[o + 3] = r; carr[o + 4] = g; carr[o + 5] = bl;
      }
      colors.needsUpdate = true;
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
