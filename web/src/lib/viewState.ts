// Per-frame view parameters shared between the camera rig, the renderer and
// the DOM HUD. Mutable on purpose: read/written every frame, never rendered.
import * as THREE from "three";

export const view = {
  focusTarget: new THREE.Vector3(0, 0, 0),
  focusDistance: 330,
  autoRotate: true,
  userBusy: false,
  dim: 1, // global brightness of the network (dimmed behind panels)
  aberration: 0, // chromatic aberration kick (decays)
  terrainMix: 0, // 0 = network, 1 = pulse terrain
  cameraOverride: null as null | { position: THREE.Vector3; target: THREE.Vector3; speed: number },
  focusDepth: 330, // world distance of the focal plane (depth of field)
  width: 1,
  height: 1,
};

export function kickAberration(amount = 1) {
  view.aberration = Math.max(view.aberration, amount);
}
