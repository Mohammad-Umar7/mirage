"use client";

import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { palette } from "@/lib/palette";
import { now, scene } from "@/lib/sceneData";
import { view } from "@/lib/viewState";
import { nodeFragment, nodeVertex } from "./shaders";

const PER_NODE = [
  ["aSeed", "seed"],
  ["aSize", "size"],
  ["aThreatFrom", "threatFrom"],
  ["aThreatTo", "threatTo"],
  ["aThreatStart", "threatStart"],
  ["aOrgFrom", "organicFrom"],
  ["aOrgTo", "organicTo"],
  ["aOrgStart", "organicStart"],
  ["aPulse", "pulseT"],
  ["aBirth", "birthT"],
] as const;

export function Nodes() {
  const gl = useThree((s) => s.gl);
  const pointsRef = useRef<THREE.Points>(null);
  const redRef = useRef<THREE.Points>(null);
  const seen = useRef({ cap: -1, attr: -1, pos: -1 });

  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 2000);
    return g;
  }, []);

  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: nodeVertex,
        fragmentShader: nodeFragment,
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending,
        uniforms: {
          uPass: { value: 0 },
          uTime: { value: 0 },
          uPixelRatio: { value: 1 },
          uScale: { value: 4.2 },
          uFocus: { value: 330 },
          uAperture: { value: 0.011 },
          uWaveOrigin: { value: new THREE.Vector3() },
          uWaveT: { value: -100 },
          uDim: { value: 1 },
          uIconPx: { value: 15 },
          uGold: { value: new THREE.Color(palette.gold) },
          uAmber: { value: new THREE.Color(palette.amber) },
          uRed: { value: new THREE.Color(palette.red) },
          uRedGlow: { value: new THREE.Color(palette.redGlow) },
        },
      }),
    [],
  );

  // second pass for flagged accounts: same geometry and uniforms, normal blending
  const redMaterial = useMemo(() => {
    const m = material.clone();
    // uniform objects are shared, so one update per frame drives both passes
    m.uniforms = { ...material.uniforms, uPass: { value: 1 } };
    m.blending = THREE.NormalBlending;
    return m;
  }, [material]);

  useEffect(() => () => {
    geometry.dispose();
    material.dispose();
    redMaterial.dispose();
  }, [geometry, material, redMaterial]);

  useFrame(() => {
    const s = seen.current;
    if (!geometry.getAttribute("position")) s.cap = -1; // fast refresh safety
    if (s.cap !== scene.capVersion) {
      geometry.setAttribute("position", new THREE.BufferAttribute(scene.positions, 3).setUsage(THREE.DynamicDrawUsage));
      for (const [attr, key] of PER_NODE) {
        geometry.setAttribute(attr, new THREE.BufferAttribute(scene[key] as Float32Array, 1).setUsage(THREE.DynamicDrawUsage));
      }
      s.cap = scene.capVersion;
      s.attr = -1;
      s.pos = -1;
    }
    if (s.attr !== scene.attrVersion) {
      for (const [attr] of PER_NODE) geometry.getAttribute(attr).needsUpdate = true;
      s.attr = scene.attrVersion;
    }
    if (s.pos !== scene.posVersion) {
      const p = geometry.getAttribute("position") as THREE.BufferAttribute | undefined;
      if (p) p.needsUpdate = true;
      s.pos = scene.posVersion;
    }
    geometry.setDrawRange(0, scene.n);
    const u = material.uniforms;
    u.uTime.value = now();
    u.uPixelRatio.value = gl.getPixelRatio();
    u.uFocus.value = view.focusDepth;
    u.uDim.value = view.dim;
    u.uWaveT.value = scene.pulseWave.t;
    (u.uWaveOrigin.value as THREE.Vector3).set(...scene.pulseWave.origin);
    const visible = view.terrainMix < 0.98;
    if (pointsRef.current) pointsRef.current.visible = visible;
    if (redRef.current) redRef.current.visible = visible;
  });

  return (
    <>
      <points ref={pointsRef} geometry={geometry} material={material} frustumCulled={false} renderOrder={2} />
      <points ref={redRef} geometry={geometry} material={redMaterial} frustumCulled={false} renderOrder={4} />
    </>
  );
}
