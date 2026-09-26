// Mutable, per-frame data for the 3D scene. Lives outside React so that
// 10k nodes never cause a re-render: the stream writes here ~1x/second and
// the renderer reads here every frame.

import type { Cluster, DetectionMsg, Verdict } from "./protocol";
import { unpackF32, unpackI32, unpackU8 } from "./protocol";

export const WORLD_RADIUS = 170;
export const SPAWN_RADIUS = 430;
const Y_SQUASH = 0.62;

// splitmix32-style hash → deterministic pseudo-random per account
function hash(n: number): number {
  n = (n + 0x9e3779b9) | 0;
  n = Math.imul(n ^ (n >>> 16), 0x85ebca6b);
  n = Math.imul(n ^ (n >>> 13), 0xc2b2ae35);
  n ^= n >>> 16;
  return (n >>> 0) / 4294967296;
}

export function homeOf(i: number, out: Float32Array, o: number) {
  const u = hash(i * 3 + 1);
  const v = hash(i * 3 + 2);
  const w = hash(i * 3 + 3);
  const theta = 2 * Math.PI * u;
  const phi = Math.acos(2 * v - 1);
  const r = WORLD_RADIUS * (0.12 + 0.88 * Math.pow(w, 0.55));
  out[o] = r * Math.sin(phi) * Math.cos(theta);
  out[o + 1] = r * Math.cos(phi) * Y_SQUASH;
  out[o + 2] = r * Math.sin(phi) * Math.sin(theta);
}

export function spawnOf(i: number, out: Float32Array, o: number) {
  const u = hash(i * 7 + 11);
  const v = hash(i * 7 + 12);
  const theta = 2 * Math.PI * u;
  const phi = Math.acos(2 * v - 1);
  out[o] = SPAWN_RADIUS * Math.sin(phi) * Math.cos(theta);
  out[o + 1] = SPAWN_RADIUS * Math.cos(phi) * 0.7;
  out[o + 2] = SPAWN_RADIUS * Math.sin(phi) * Math.sin(theta);
}

export type SceneCluster = {
  id: number;
  verdict: Verdict;
  confidence: number;
  watch: boolean;
  level: number | null;
  size: number;
  members: Int32Array;
  centroid: [number, number, number];
  radius: number;
  firstSeen: number; // seconds (client clock) the cluster first appeared as this verdict
};

export const now = () => performance.now() / 1000;

class SceneData {
  capacity = 0;
  n = 0;
  positions = new Float32Array(0);
  homes = new Float32Array(0);
  spawn = new Float32Array(0);
  seed = new Float32Array(0);
  size = new Float32Array(0);
  threatFrom = new Float32Array(0);
  threatTo = new Float32Array(0);
  threatStart = new Float32Array(0);
  organicFrom = new Float32Array(0);
  organicTo = new Float32Array(0);
  organicStart = new Float32Array(0);
  pulseT = new Float32Array(0);
  birthT = new Float32Array(0);
  clusterOf = new Int32Array(0);

  capVersion = 0;
  attrVersion = 0;
  posVersion = 0;

  edges: { i: Int32Array; j: Int32Array; w: Float32Array; bits: Uint8Array; version: number } = {
    i: new Int32Array(0), j: new Int32Array(0), w: new Float32Array(0), bits: new Uint8Array(0), version: 0,
  };
  clusters: SceneCluster[] = [];
  clusterVersion = 0;
  pulseWave = { t: -100, origin: [0, 0, 0] as [number, number, number] };

  private grow(need: number) {
    if (need <= this.capacity) return;
    const cap = Math.max(need, Math.ceil(this.capacity * 1.5) + 512);
    const g = <T extends Float32Array | Int32Array>(a: T, width = 1, fill = 0): T => {
      const b = new (a.constructor as { new (n: number): T })(cap * width);
      if (fill !== 0) b.fill(fill);
      b.set(a);
      return b;
    };
    this.positions = g(this.positions, 3);
    this.homes = g(this.homes, 3);
    this.spawn = g(this.spawn, 3);
    this.seed = g(this.seed);
    this.size = g(this.size);
    this.threatFrom = g(this.threatFrom);
    this.threatTo = g(this.threatTo);
    this.threatStart = g(this.threatStart);
    this.organicFrom = g(this.organicFrom);
    this.organicTo = g(this.organicTo);
    this.organicStart = g(this.organicStart);
    this.pulseT = g(this.pulseT, 1, -100);
    this.birthT = g(this.birthT, 1, -100);
    this.clusterOf = g(this.clusterOf, 1, -1);
    this.capacity = cap;
    this.capVersion++;
  }

  reset() {
    this.n = 0;
    this.capacity = 0;
    this.positions = new Float32Array(0);
    this.homes = new Float32Array(0);
    this.spawn = new Float32Array(0);
    this.seed = new Float32Array(0);
    this.size = new Float32Array(0);
    this.threatFrom = new Float32Array(0);
    this.threatTo = new Float32Array(0);
    this.threatStart = new Float32Array(0);
    this.organicFrom = new Float32Array(0);
    this.organicTo = new Float32Array(0);
    this.organicStart = new Float32Array(0);
    this.pulseT = new Float32Array(0);
    this.birthT = new Float32Array(0);
    this.clusterOf = new Int32Array(0);
    this.edges = { i: new Int32Array(0), j: new Int32Array(0), w: new Float32Array(0), bits: new Uint8Array(0), version: this.edges.version + 1 };
    this.clusters = [];
    this.clusterVersion++;
    this.capVersion++;
  }

  /** Accounts [from, from+count). `streaming` accounts fly in from the edges. */
  addAccounts(from: number, count: number, streaming: boolean) {
    const to = from + count;
    if (to <= this.n) return;
    this.grow(to);
    const t = now();
    for (let i = this.n; i < to; i++) {
      homeOf(i, this.homes, i * 3);
      spawnOf(i, this.spawn, i * 3);
      const src = streaming ? this.spawn : this.homes;
      this.positions[i * 3] = src[i * 3];
      this.positions[i * 3 + 1] = src[i * 3 + 1];
      this.positions[i * 3 + 2] = src[i * 3 + 2];
      this.seed[i] = hash(i * 13 + 5);
      if (this.size[i] === 0) this.size[i] = 0.35 + 0.25 * hash(i * 17 + 3);
      this.birthT[i] = streaming ? t + Math.random() * 0.8 : t - 10;
      this.clusterOf[i] = -1;
    }
    this.n = to;
    this.attrVersion++;
  }

  setActivity(levels: Uint8Array) {
    const m = Math.min(levels.length, this.n);
    for (let i = 0; i < m; i++) this.size[i] = 0.3 + 0.9 * (levels[i] / 255);
    this.attrVersion++;
  }

  pulse(active: Int32Array) {
    const t = now();
    for (let k = 0; k < active.length; k++) {
      const i = active[k];
      if (i < this.n) this.pulseT[i] = t + Math.random() * 0.9; // spread flashes over the tick
    }
    this.attrVersion++;
  }

  private currentThreat(i: number, t: number) {
    const k = Math.min(1, Math.max(0, (t - this.threatStart[i]) / 1.6));
    const s = k * k * (3 - 2 * k);
    return this.threatFrom[i] + (this.threatTo[i] - this.threatFrom[i]) * s;
  }

  private currentOrganic(i: number, t: number) {
    const k = Math.min(1, Math.max(0, (t - this.organicStart[i]) / 1.2));
    return this.organicFrom[i] + (this.organicTo[i] - this.organicFrom[i]) * k;
  }

  applyDetection(msg: DetectionMsg, clusters: Cluster[]) {
    const t = now();
    const threat = new Float32Array(this.n);
    const organic = new Float32Array(this.n);
    const clusterOf = new Int32Array(this.n).fill(-1);
    const prev = new Map(this.clusters.map((c) => [c.id, c]));
    const next: SceneCluster[] = [];
    for (const c of clusters) {
      let target = 0;
      if (c.verdict === "SWARM") {
        const x = Math.min(1, Math.max(0, (c.confidence - 0.55) / 0.35));
        target = 0.35 + 0.65 * x * x * (3 - 2 * x);
      } else if (c.watch) {
        target = 0.1 + 0.25 * Math.min(1, (c.confidence - 0.3) / 0.15);
      }
      for (let k = 0; k < c.members.length; k++) {
        const i = c.members[k];
        if (i >= this.n) continue;
        clusterOf[i] = c.id;
        if (target > threat[i]) threat[i] = target;
        if (c.verdict === "ORGANIC COMMUNITY") organic[i] = 1;
      }
      const old = prev.get(c.id);
      next.push({
        id: c.id, verdict: c.verdict, confidence: c.confidence, watch: c.watch, level: c.level_estimate,
        size: c.size, members: c.members, centroid: old?.centroid ?? [0, 0, 0], radius: old?.radius ?? 10,
        firstSeen: old && old.verdict === c.verdict ? old.firstSeen : t,
      });
    }
    for (let i = 0; i < this.n; i++) {
      if (Math.abs(threat[i] - this.threatTo[i]) > 0.02) {
        this.threatFrom[i] = this.currentThreat(i, t);
        this.threatTo[i] = threat[i];
        this.threatStart[i] = t;
      }
      if (organic[i] !== this.organicTo[i]) {
        this.organicFrom[i] = this.currentOrganic(i, t);
        this.organicTo[i] = organic[i];
        this.organicStart[i] = t;
      }
      this.clusterOf[i] = clusterOf[i];
    }
    this.clusters = next;
    this.clusterVersion++;
    const ei = unpackI32(msg.edges.i);
    const ej = unpackI32(msg.edges.j);
    this.edges = { i: ei, j: ej, w: unpackF32(msg.edges.w), bits: unpackU8(msg.edges.bits), version: this.edges.version + 1 };
    this.attrVersion++;
  }

  /** Centroid + radius of a cluster from current positions (cheap: ≤ a few thousand members). */
  measure(c: SceneCluster) {
    const m = c.members;
    let x = 0, y = 0, z = 0, cnt = 0;
    const P = this.positions;
    for (let k = 0; k < m.length; k++) {
      const i = m[k];
      if (i >= this.n) continue;
      x += P[i * 3]; y += P[i * 3 + 1]; z += P[i * 3 + 2]; cnt++;
    }
    if (!cnt) return;
    x /= cnt; y /= cnt; z /= cnt;
    // robust radius: 75th percentile distance, so stragglers still gliding in
    // do not inflate rings and halos
    const step = Math.max(1, Math.floor(m.length / 300));
    const dist: number[] = [];
    for (let k = 0; k < m.length; k += step) {
      const i = m[k];
      if (i >= this.n) continue;
      const dx = P[i * 3] - x, dy = P[i * 3 + 1] - y, dz = P[i * 3 + 2] - z;
      dist.push(Math.sqrt(dx * dx + dy * dy + dz * dz));
    }
    dist.sort((a, b) => a - b);
    const q = dist.length ? dist[Math.min(dist.length - 1, Math.floor(dist.length * 0.75))] : 8;
    c.centroid = [x, y, z];
    c.radius = Math.min(q * 1.15 + 2, 90);
  }
}

export const scene = new SceneData();
