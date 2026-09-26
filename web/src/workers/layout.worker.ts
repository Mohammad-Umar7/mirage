/// <reference lib="webworker" />
// Force layout driven by the detector's coordination graph.
//
// Every account springs toward its home in the scattered cloud. When the
// detector puts accounts into a cluster, their target becomes a point in a
// tight ball around the cluster's anchor - swarms collapse hard, organic
// communities gather loosely - and weak springs along the coordination
// edges pull linked accounts together. Positions stream back to the main
// thread as transferable buffers.

type ClusterIn = { id: number; verdict: string; confidence: number; watch: boolean; members: Int32Array };
type Msg =
  | { type: "reset" }
  | { type: "nodes"; from: number; homes: Float32Array; positions: Float32Array }
  | { type: "graph"; i: Int32Array; j: Int32Array; w: Float32Array; bits: Uint8Array; clusters: ClusterIn[] }
  | { type: "buffer"; buf: ArrayBuffer };

const ctx = self as unknown as DedicatedWorkerGlobalScope;

let n = 0;
let cap = 0;
let pos = new Float32Array(0);
let vel = new Float32Array(0);
let home = new Float32Array(0);
let target = new Float32Array(0);
let stiff = new Float32Array(0);
let damp = new Float32Array(0);
let clusterOf = new Int32Array(0);
let ei: Int32Array = new Int32Array(0);
let ej: Int32Array = new Int32Array(0);
let ew: Float32Array = new Float32Array(0);
let eInside = new Uint8Array(0);
const anchors = new Map<number, [number, number, number]>();
const pool: ArrayBuffer[] = [];
let lastPost = 0;

const HOME_OMEGA = 1.6; // rad/s: how briskly accounts settle home
const SWARM_OMEGA = 1.25; // slower, cinematic collapse
const ORGANIC_OMEGA = 0.9;

function grow(need: number) {
  if (need <= cap) return;
  const c = Math.max(need, Math.ceil(cap * 1.5) + 512);
  const g = <T extends Float32Array | Int32Array>(a: T, width = 1, fill = 0): T => {
    const b = new (a.constructor as { new (n: number): T })(c * width);
    if (fill) b.fill(fill);
    b.set(a);
    return b;
  };
  pos = g(pos, 3);
  vel = g(vel, 3);
  home = g(home, 3);
  target = g(target, 3);
  stiff = g(stiff);
  damp = g(damp);
  clusterOf = g(clusterOf, 1, -1);
  cap = c;
}

function setSpring(i: number, omega: number) {
  stiff[i] = omega * omega;
  damp[i] = 2 * omega * 1.05; // slightly over-damped: glide, never wobble
}

// Points spread uniformly through a ball, deterministic per rank.
function ballOffset(rank: number, count: number, radius: number, out: number[]) {
  const golden = Math.PI * (3 - Math.sqrt(5));
  const y = 1 - (2 * (rank + 0.5)) / count;
  const r = Math.sqrt(Math.max(0, 1 - y * y));
  const th = golden * rank;
  const shell = Math.cbrt((rank + 0.5) / count);
  const jitter = 0.85 + 0.3 * (((rank * 2654435761) >>> 0) / 4294967296);
  out[0] = Math.cos(th) * r * radius * shell * jitter;
  out[1] = y * radius * shell * jitter * 0.85;
  out[2] = Math.sin(th) * r * radius * shell * jitter;
}

function swarmAnchor(id: number): [number, number, number] {
  let a = anchors.get(id);
  if (a) return a;
  const k = [...anchors.keys()].filter((x) => x >= 0).length;
  if (k === 0) a = [0, 4, 0];
  else {
    const ang = k * 2.39996;
    a = [Math.cos(ang) * 62, 10 * Math.sin(k * 1.7), Math.sin(ang) * 62];
  }
  anchors.set(id, a);
  return a;
}

function organicAnchor(id: number, members: Int32Array): [number, number, number] {
  let a = anchors.get(-id - 1);
  if (a) return a;
  let best = members[0];
  for (let k = 1; k < members.length; k++) if (members[k] < best) best = members[k];
  a = [home[best * 3] * 0.92, home[best * 3 + 1] * 0.92, home[best * 3 + 2] * 0.92];
  anchors.set(-id - 1, a);
  return a;
}

function applyGraph(m: Extract<Msg, { type: "graph" }>) {
  for (let i = 0; i < n; i++) {
    target[i * 3] = home[i * 3];
    target[i * 3 + 1] = home[i * 3 + 1];
    target[i * 3 + 2] = home[i * 3 + 2];
    setSpring(i, HOME_OMEGA);
    clusterOf[i] = -1;
  }
  const off = [0, 0, 0];
  for (const c of m.clusters) {
    const members = c.members;
    const count = members.length;
    if (!count) continue;
    if (c.verdict === "SWARM" && c.confidence >= 0.55) {
      const a = swarmAnchor(c.id);
      const radius = 8 + 2.7 * Math.cbrt(count);
      const pull = Math.min(1, (c.confidence - 0.5) / 0.4);
      for (let k = 0; k < count; k++) {
        const i = members[k];
        if (i >= n) continue;
        ballOffset(k, count, radius, off);
        // blend between home and the cluster as confidence rises
        const hx = home[i * 3], hy = home[i * 3 + 1], hz = home[i * 3 + 2];
        target[i * 3] = hx + (a[0] + off[0] - hx) * pull;
        target[i * 3 + 1] = hy + (a[1] + off[1] - hy) * pull;
        target[i * 3 + 2] = hz + (a[2] + off[2] - hz) * pull;
        setSpring(i, SWARM_OMEGA);
        clusterOf[i] = c.id;
      }
    } else if (c.verdict === "ORGANIC COMMUNITY") {
      const a = organicAnchor(c.id, members);
      const radius = 4 + 2.6 * Math.cbrt(count);
      for (let k = 0; k < count; k++) {
        const i = members[k];
        if (i >= n) continue;
        ballOffset(k, count, radius, off);
        const hx = home[i * 3], hy = home[i * 3 + 1], hz = home[i * 3 + 2];
        target[i * 3] = hx + (a[0] + off[0] - hx) * 0.85;
        target[i * 3 + 1] = hy + (a[1] + off[1] - hy) * 0.85;
        target[i * 3 + 2] = hz + (a[2] + off[2] - hz) * 0.85;
        setSpring(i, ORGANIC_OMEGA);
        clusterOf[i] = c.id;
      }
    }
  }
  ei = m.i;
  ej = m.j;
  ew = m.w;
  eInside = new Uint8Array(ei.length);
  for (let e = 0; e < ei.length; e++) {
    const a = ei[e], b = ej[e];
    eInside[e] = a < n && b < n && clusterOf[a] >= 0 && clusterOf[a] === clusterOf[b] ? 1 : 0;
  }
}

function step(dt: number) {
  // edge springs: firm inside clusters, a whisper between ordinary accounts
  for (let e = 0; e < ei.length; e++) {
    const a = ei[e], b = ej[e];
    if (a >= n || b >= n) continue;
    const inside = eInside[e] === 1;
    // inside a cluster the targets already form the ball; springs only add
    // a little web-like tension (strong springs would crush it into a point)
    const rest = inside ? 16 : 26;
    const k = (inside ? 0.05 : 0.018) * Math.min(2.5, ew[e]);
    const dx = pos[b * 3] - pos[a * 3];
    const dy = pos[b * 3 + 1] - pos[a * 3 + 1];
    const dz = pos[b * 3 + 2] - pos[a * 3 + 2];
    const d = Math.sqrt(dx * dx + dy * dy + dz * dz) + 1e-6;
    const f = (k * (d - rest)) / d;
    vel[a * 3] += f * dx * dt;
    vel[a * 3 + 1] += f * dy * dt;
    vel[a * 3 + 2] += f * dz * dt;
    vel[b * 3] -= f * dx * dt;
    vel[b * 3 + 1] -= f * dy * dt;
    vel[b * 3 + 2] -= f * dz * dt;
  }
  for (let i = 0; i < n; i++) {
    const k = stiff[i];
    const c = damp[i];
    for (let d = 0; d < 3; d++) {
      const o = i * 3 + d;
      const acc = k * (target[o] - pos[o]) - c * vel[o];
      vel[o] += acc * dt;
      pos[o] += vel[o] * dt;
    }
  }
}

function post() {
  let buf = pool.pop();
  if (!buf || buf.byteLength < n * 12) buf = new ArrayBuffer(Math.max(n * 12, 12));
  const view = new Float32Array(buf, 0, n * 3);
  view.set(pos.subarray(0, n * 3));
  ctx.postMessage({ type: "positions", n, buf }, [buf]);
}

let last = performance.now();
function loop() {
  const t = performance.now();
  let dt = (t - last) / 1000;
  last = t;
  dt = Math.min(dt, 0.05);
  const sub = dt > 0.02 ? 2 : 1;
  for (let s = 0; s < sub; s++) step(dt / sub);
  if (pool.length > 0 || t - lastPost > 100) {
    post();
    lastPost = t;
  }
  setTimeout(loop, 1000 / 60);
}

ctx.onmessage = (ev: MessageEvent<Msg>) => {
  const m = ev.data;
  if (m.type === "reset") {
    n = 0;
    anchors.clear();
    ei = new Int32Array(0);
    ej = new Int32Array(0);
    ew = new Float32Array(0);
    eInside = new Uint8Array(0);
  } else if (m.type === "nodes") {
    const count = m.homes.length / 3;
    const to = m.from + count;
    grow(to);
    home.set(m.homes, m.from * 3);
    pos.set(m.positions, m.from * 3);
    for (let i = m.from; i < to; i++) {
      target[i * 3] = home[i * 3];
      target[i * 3 + 1] = home[i * 3 + 1];
      target[i * 3 + 2] = home[i * 3 + 2];
      vel[i * 3] = vel[i * 3 + 1] = vel[i * 3 + 2] = 0;
      setSpring(i, HOME_OMEGA);
      clusterOf[i] = -1;
    }
    n = Math.max(n, to);
  } else if (m.type === "graph") {
    applyGraph(m);
  } else if (m.type === "buffer") {
    pool.push(m.buf);
  }
};

loop();
