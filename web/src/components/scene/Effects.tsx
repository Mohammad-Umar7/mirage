"use client";

import { Bloom, ChromaticAberration, EffectComposer, Noise, Vignette } from "@react-three/postprocessing";
import { useFrame } from "@react-three/fiber";
import { BlendFunction, type ChromaticAberrationEffect } from "postprocessing";
import { useRef } from "react";
import * as THREE from "three";
import { view } from "@/lib/viewState";

const offset = new THREE.Vector2(0, 0);

export function Effects() {
  const ca = useRef<ChromaticAberrationEffect>(null);
  useFrame((_, dt) => {
    // aberration only during transitions (lock-on, view changes), never at rest:
    // a constant offset splits tiny bright points into green-centred fringes
    view.aberration *= Math.exp(-dt * 2.6);
    if (view.aberration < 0.01) view.aberration = 0;
    const k = view.aberration * 0.0032;
    ca.current?.offset.set(k, k * 0.55);
  });
  return (
    <EffectComposer multisampling={0} enableNormalPass={false}>
      <Bloom mipmapBlur intensity={1.15} luminanceThreshold={0.16} luminanceSmoothing={0.3} radius={0.78} />
      <ChromaticAberration ref={ca} offset={offset} radialModulation modulationOffset={0.35} />
      {/* additive grain: soft-light/premultiplied blends evaluate branches that overflow to
          inf on the HDR swarm core and turn it into NaN (blue/green garbage) */}
      <Noise opacity={0.016} blendFunction={BlendFunction.ADD} />
      <Vignette eskil={false} offset={0.22} darkness={0.78} />
    </EffectComposer>
  );
}
