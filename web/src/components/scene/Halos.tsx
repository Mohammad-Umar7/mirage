"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { palette } from "@/lib/palette";
import { now, scene } from "@/lib/sceneData";
import { view } from "@/lib/viewState";
import { haloFragment, haloVertex } from "./shaders";

const MAX = 24;

// Soft gold rings around organic communities: "seen, understood, not flagged".
export function Halos() {
  const group = useRef<THREE.Group>(null);
  const meshes = useMemo(() => {
    const geo = new THREE.PlaneGeometry(1, 1);
    return Array.from({ length: MAX }, () => {
      const mat = new THREE.ShaderMaterial({
        vertexShader: haloVertex,
        fragmentShader: haloFragment,
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending,
        uniforms: { uColor: { value: new THREE.Color(palette.gold) }, uOpacity: { value: 0 }, uTime: { value: 0 } },
      });
      const m = new THREE.Mesh(geo, mat);
      m.visible = false;
      m.renderOrder = 6;
      m.frustumCulled = false;
      return m;
    });
  }, []);

  useFrame(({ camera }) => {
    const organics = scene.clusters.filter((c) => c.verdict === "ORGANIC COMMUNITY").slice(0, MAX);
    const t = now();
    for (let k = 0; k < MAX; k++) {
      const m = meshes[k];
      const c = organics[k];
      if (!c) {
        m.visible = false;
        continue;
      }
      scene.measure(c);
      m.visible = view.terrainMix < 0.98;
      m.position.set(...c.centroid);
      m.quaternion.copy(camera.quaternion);
      m.scale.setScalar(Math.max(8, c.radius * 2.3));
      const mat = m.material as THREE.ShaderMaterial;
      const fadeIn = Math.min(1, (t - c.firstSeen) / 1.5);
      mat.uniforms.uOpacity.value = 0.55 * fadeIn * view.dim * (1 - view.terrainMix);
      mat.uniforms.uTime.value = t;
    }
  });

  return (
    <group ref={group}>
      {meshes.map((m, k) => (
        <primitive key={k} object={m} />
      ))}
    </group>
  );
}
