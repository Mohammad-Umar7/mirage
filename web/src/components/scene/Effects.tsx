"use client";

import { Bloom, ChromaticAberration, EffectComposer, Noise, Vignette } from "@react-three/postprocessing";
import { useFrame } from "@react-three/fiber";
import { BlendFunction, type ChromaticAberrationEffect } from "postprocessing";
import { useRef } from "react";
import * as THREE from "three";
import { view } from "@/lib/viewState";

const offset = new THREE.Vector2(0.0004, 0.0004);

export function Effects() {
  const ca = useRef<ChromaticAberrationEffect>(null);
  useFrame((_, dt) => {
    view.aberration *= Math.exp(-dt * 2.6);
    const k = 0.00035 + view.aberration * 0.0045;
    ca.current?.offset.set(k, k * 0.6);
  });
  return (
    <EffectComposer multisampling={0} enableNormalPass={false}>
      <Bloom mipmapBlur intensity={1.35} luminanceThreshold={0.12} luminanceSmoothing={0.35} radius={0.82} />
      <ChromaticAberration ref={ca} offset={offset} radialModulation modulationOffset={0.35} />
      <Noise premultiply opacity={0.9} blendFunction={BlendFunction.SOFT_LIGHT} />
      <Vignette eskil={false} offset={0.22} darkness={0.78} />
    </EffectComposer>
  );
}
