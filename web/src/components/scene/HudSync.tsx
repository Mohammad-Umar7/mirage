"use client";

import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";
import { hudBus, type ScreenCluster } from "@/lib/hudBus";
import { scene } from "@/lib/sceneData";
import { view } from "@/lib/viewState";

const v = new THREE.Vector3();
const edge = new THREE.Vector3();
const right = new THREE.Vector3();

// Projects cluster centroids to screen coordinates for the DOM HUD.
export function HudSync() {
  const frame = useRef(0);
  useFrame(({ camera, size }) => {
    frame.current++;
    if (process.env.NODE_ENV !== "production" && frame.current === 1) {
      (window as unknown as Record<string, unknown>).__mirageCamera = camera;
    }
    view.width = size.width;
    view.height = size.height;
    const out: ScreenCluster[] = [];
    right.set(1, 0, 0).applyQuaternion(camera.quaternion);
    for (const c of scene.clusters) {
      const shown = c.verdict === "SWARM" || c.verdict === "ORGANIC COMMUNITY" || c.watch;
      if (!shown) continue;
      if (c.verdict !== "ORGANIC COMMUNITY" || frame.current % 2 === 0) scene.measure(c);
      v.set(...c.centroid);
      const depth = v.distanceTo(camera.position);
      v.project(camera);
      const x = (v.x * 0.5 + 0.5) * size.width;
      const y = (-v.y * 0.5 + 0.5) * size.height;
      edge.set(...c.centroid).addScaledVector(right, c.radius).project(camera);
      const ex = (edge.x * 0.5 + 0.5) * size.width;
      const ey = (-edge.y * 0.5 + 0.5) * size.height;
      const r = Math.hypot(ex - x, ey - y);
      out.push({ id: c.id, verdict: c.verdict, x, y, r, visible: v.z < 1 && view.terrainMix < 0.5, depth });
    }
    hudBus.publish(out);
  });
  return null;
}
