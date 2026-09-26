"use client";

import { OrbitControls } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { scene } from "@/lib/sceneData";
import { commands } from "@/lib/socket";
import { useMirage } from "@/lib/store";
import { view } from "@/lib/viewState";

const HOME_TARGET = new THREE.Vector3(0, 0, 0);
const TERRAIN_POS = new THREE.Vector3(0, 210, 430);
const TERRAIN_TARGET = new THREE.Vector3(0, -6, -30);
const tmp = new THREE.Vector3();
const dir = new THREE.Vector3();
const viewProj = new THREE.Matrix4();

function pick(x: number, y: number, camera: THREE.Camera, w: number, h: number): number {
  viewProj.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
  const e = viewProj.elements;
  const P = scene.positions;
  let best = -1;
  let bestScore = 1e9;
  for (let i = 0; i < scene.n; i++) {
    const px = P[i * 3], py = P[i * 3 + 1], pz = P[i * 3 + 2];
    const cw = e[3] * px + e[7] * py + e[11] * pz + e[15];
    if (cw <= 0) continue;
    const sx = ((e[0] * px + e[4] * py + e[8] * pz + e[12]) / cw * 0.5 + 0.5) * w;
    const sy = (-(e[1] * px + e[5] * py + e[9] * pz + e[13]) / cw * 0.5 + 0.5) * h;
    const d = Math.hypot(sx - x, sy - y);
    if (d < 16) {
      const score = d + cw * 0.01;
      if (score < bestScore) {
        bestScore = score;
        best = i;
      }
    }
  }
  return best;
}

export function CameraRig() {
  const controls = useRef<OrbitControlsImpl>(null);
  const { camera, gl, size } = useThree();
  const idleAt = useRef(0);

  useEffect(() => {
    const el = gl.domElement;
    let down: { x: number; y: number } | null = null;
    const onDown = (ev: PointerEvent) => {
      down = { x: ev.clientX, y: ev.clientY };
    };
    const onUp = (ev: PointerEvent) => {
      if (!down) return;
      const moved = Math.hypot(ev.clientX - down.x, ev.clientY - down.y);
      down = null;
      if (moved > 5 || view.terrainMix > 0.5) return;
      const rect = el.getBoundingClientRect();
      const i = pick(ev.clientX - rect.left, ev.clientY - rect.top, camera, rect.width, rect.height);
      const st = useMirage.getState();
      if (i < 0) {
        st.select(null);
        return;
      }
      const cid = scene.clusterOf[i];
      const c = scene.clusters.find((x) => x.id === cid);
      if (c && (c.verdict !== "NORMAL" || c.watch)) {
        st.select(c.id);
        commands.evidence(c.id);
      } else {
        st.select(null);
        view.focusTarget.set(scene.positions[i * 3], scene.positions[i * 3 + 1], scene.positions[i * 3 + 2]);
        view.focusDistance = 120;
        idleAt.current = performance.now() + 5000;
      }
    };
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointerup", onUp);
    return () => {
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointerup", onUp);
    };
  }, [camera, gl]);

  useEffect(() => {
    const c = controls.current;
    if (!c) return;
    const start = () => {
      view.userBusy = true;
    };
    const end = () => {
      view.userBusy = false;
      idleAt.current = performance.now() + 6000;
    };
    c.addEventListener("start", start);
    c.addEventListener("end", end);
    return () => {
      c.removeEventListener("start", start);
      c.removeEventListener("end", end);
    };
  }, []);

  useFrame((_, dt) => {
    const c = controls.current;
    if (!c) return;
    const st = useMirage.getState();
    const k = 1 - Math.exp(-dt * 1.4);
    const terrain = view.terrainMix > 0.5;
    const idle = !view.userBusy && performance.now() > idleAt.current;

    if (view.cameraOverride) {
      const o = view.cameraOverride;
      const kk = 1 - Math.exp(-dt * o.speed);
      camera.position.lerp(o.position, kk);
      c.target.lerp(o.target, kk);
    } else if (terrain) {
      camera.position.lerp(TERRAIN_POS, k);
      c.target.lerp(TERRAIN_TARGET, k);
    } else if (idle) {
      const focusId = st.selected ?? st.lockedCluster;
      const cl = focusId !== null ? scene.clusters.find((x) => x.id === focusId) : undefined;
      if (cl) {
        view.focusTarget.set(...cl.centroid);
        view.focusDistance = THREE.MathUtils.clamp(cl.radius * 5.5, 175, 300);
      } else if (performance.now() > idleAt.current + 4000) {
        view.focusTarget.lerp(HOME_TARGET, k);
        view.focusDistance += (330 - view.focusDistance) * k;
      }
      c.target.lerp(view.focusTarget, k);
      dir.subVectors(camera.position, c.target);
      const dist = dir.length();
      const next = dist + (view.focusDistance - dist) * k * 0.8;
      camera.position.copy(tmp.copy(c.target).addScaledVector(dir.normalize(), next));
    }
    c.autoRotate = !terrain && !view.cameraOverride && !view.userBusy;
    c.autoRotateSpeed = st.lockedCluster !== null ? 0.18 : 0.3;
    c.enableRotate = !terrain;
    view.focusDepth = camera.position.distanceTo(c.target);
    c.update();
  });

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      enableDamping
      dampingFactor={0.06}
      rotateSpeed={0.5}
      zoomSpeed={0.7}
      minDistance={30}
      maxDistance={720}
      enablePan={false}
      autoRotate
      autoRotateSpeed={0.3}
    />
  );
}

export function useViewportWidth() {
  return useThree((s) => s.size.width);
}
