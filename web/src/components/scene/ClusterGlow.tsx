"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo } from "react";
import * as THREE from "three";
import { palette } from "@/lib/palette";
import { now, scene } from "@/lib/sceneData";
import { view } from "@/lib/viewState";

const MAX = 4;

const vertex = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const fragment = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  varying vec2 vUv;
  void main() {
    vec2 p = (vUv - 0.5) * 2.0;
    float r2 = dot(p, p);
    float glow = exp(-r2 * 3.2) * 0.8 + exp(-r2 * 12.0) * 0.5;
    gl_FragColor = vec4(uColor * glow, glow * uOpacity);
  }
`;

// Soft volumetric red glow behind flagged clusters: reads as one dense mass
// while the points on top stay individually visible.
export function ClusterGlow() {
  const meshes = useMemo(() => {
    const geo = new THREE.PlaneGeometry(1, 1);
    return Array.from({ length: MAX }, () => {
      const mat = new THREE.ShaderMaterial({
        vertexShader: vertex,
        fragmentShader: fragment,
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending,
        uniforms: { uColor: { value: new THREE.Color(palette.red) }, uOpacity: { value: 0 } },
      });
      const m = new THREE.Mesh(geo, mat);
      m.visible = false;
      m.frustumCulled = false;
      m.renderOrder = 1;
      return m;
    });
  }, []);

  useFrame(({ camera }) => {
    const swarms = scene.clusters.filter((c) => c.verdict === "SWARM" && c.confidence >= 0.6).slice(0, MAX);
    const t = now();
    for (let k = 0; k < MAX; k++) {
      const m = meshes[k];
      const c = swarms[k];
      if (!c) {
        m.visible = false;
        continue;
      }
      m.visible = view.terrainMix < 0.98;
      m.position.set(...c.centroid);
      m.quaternion.copy(camera.quaternion);
      m.scale.setScalar(Math.max(20, c.radius * 3.4));
      const fade = Math.min(1, (t - c.firstSeen) / 2);
      (m.material as THREE.ShaderMaterial).uniforms.uOpacity.value = 0.32 * fade * view.dim * (1 - view.terrainMix);
    }
  });

  return (
    <>
      {meshes.map((m, k) => (
        <primitive key={k} object={m} />
      ))}
    </>
  );
}
