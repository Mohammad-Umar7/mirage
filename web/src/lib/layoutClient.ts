"use client";

import { scene } from "./sceneData";

// Main-thread side of the layout worker: forwards nodes and the coordination
// graph, receives positions and hands the buffer back for reuse.
class LayoutClient {
  private worker: Worker | null = null;
  private sentNodes = 0;
  private pendingGraph = false;

  start() {
    if (this.worker || typeof window === "undefined") return;
    this.worker = new Worker(new URL("../workers/layout.worker.ts", import.meta.url), { type: "module" });
    this.worker.onmessage = (ev: MessageEvent<{ type: string; n: number; buf: ArrayBuffer }>) => {
      const { n, buf } = ev.data;
      const m = Math.min(n, scene.n);
      scene.positions.set(new Float32Array(buf, 0, m * 3));
      scene.posVersion++;
      this.worker?.postMessage({ type: "buffer", buf }, [buf]);
    };
    this.nodes();
    if (this.pendingGraph) this.graph();
  }

  reset() {
    this.sentNodes = 0;
    this.worker?.postMessage({ type: "reset" });
    this.nodes();
  }

  nodes() {
    if (!this.worker) return;
    const from = this.sentNodes;
    const to = scene.n;
    if (to <= from) return;
    this.worker.postMessage({
      type: "nodes",
      from,
      homes: scene.homes.slice(from * 3, to * 3),
      positions: scene.positions.slice(from * 3, to * 3),
    });
    this.sentNodes = to;
  }

  graph() {
    if (!this.worker) {
      this.pendingGraph = true;
      return;
    }
    this.nodes();
    this.worker.postMessage({
      type: "graph",
      i: scene.edges.i.slice(),
      j: scene.edges.j.slice(),
      w: scene.edges.w.slice(),
      bits: scene.edges.bits.slice(),
      clusters: scene.clusters.map((c) => ({
        id: c.id, verdict: c.verdict, confidence: c.confidence, watch: c.watch, members: c.members.slice(),
      })),
    });
  }
}

export const layout = new LayoutClient();
