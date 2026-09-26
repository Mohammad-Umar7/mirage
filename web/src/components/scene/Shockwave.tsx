"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { palette } from "@/lib/palette";
import { now, scene } from "@/lib/sceneData";
import { shellFragment, shellVertex } from "./shaders";

const DURATION = 3.2;
const SPEED = 175; // world units / second - matches the node flare in the vertex shader

export function Shockwave() {
  const mesh = useRef<THREE.Mesh>(null);
  const ring = useRef<THREE.Mesh>(null);
  const shellMat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: shellVertex,
        fragmentShader: shellFragment,
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
        uniforms: { uColor: { value: new THREE.Color(palette.redGlow) }, uOpacity: { value: 0 } },
      }),
    [],
  );
  const ringMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(palette.goldSoft),
        transparent: true,
        opacity: 0,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        depthTest: false,
        side: THREE.DoubleSide,
      }),
    [],
  );

  useFrame(({ camera }) => {
    const age = now() - scene.pulseWave.t;
    const active = age > 0 && age < DURATION;
    if (!mesh.current || !ring.current) return;
    mesh.current.visible = active;
    ring.current.visible = active;
    if (!active) return;
    const r = Math.max(0.01, age * SPEED);
    const fade = 1 - age / DURATION;
    const [x, y, z] = scene.pulseWave.origin;
    mesh.current.position.set(x, y, z);
    mesh.current.scale.setScalar(r);
    shellMat.uniforms.uOpacity.value = fade * fade * 0.55;
    ring.current.position.set(x, y, z);
    ring.current.quaternion.copy(camera.quaternion);
    ring.current.scale.setScalar(r * 1.02);
    ringMat.opacity = fade * 0.5;
  });

  return (
    <>
      <mesh ref={mesh} material={shellMat} visible={false} renderOrder={4}>
        <icosahedronGeometry args={[1, 5]} />
      </mesh>
      <mesh ref={ring} material={ringMat} visible={false} renderOrder={5}>
        <ringGeometry args={[0.985, 1, 128]} />
      </mesh>
    </>
  );
}
