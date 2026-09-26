"use client";

import { decodeClusters, unpackF32, unpackI32, unpackU8, type ServerMsg } from "./protocol";
import { scene } from "./sceneData";
import { useMirage } from "./store";
import { layout } from "./layoutClient";
import { isFresh, LOCK_CONFIDENCE } from "./lock";
import { kickAberration } from "./viewState";

function wsUrl(): string {
  const env = process.env.NEXT_PUBLIC_MIRAGE_WS;
  if (env) return env;
  const host = typeof window !== "undefined" ? window.location.hostname : "127.0.0.1";
  return `ws://${host}:8000/ws`;
}

class MirageSocket {
  private ws: WebSocket | null = null;
  private retry = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private started = false;

  start() {
    if (this.started) return;
    this.started = true;
    this.connect();
  }

  private connect() {
    const st = useMirage.getState();
    st.set({ status: st.world ? "reconnecting" : "connecting" });
    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl());
    } catch {
      this.schedule();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 0;
      useMirage.getState().set({ connected: true });
    };
    ws.onmessage = (ev) => {
      try {
        this.route(JSON.parse(ev.data as string) as ServerMsg);
      } catch (err) {
        console.error("[mirage] bad message", err);
      }
    };
    ws.onclose = () => {
      useMirage.getState().set({ connected: false, status: "reconnecting" });
      this.schedule();
    };
    ws.onerror = () => ws.close();
  }

  private schedule() {
    if (this.timer) return;
    const delay = Math.min(5000, 400 * 2 ** this.retry++);
    this.timer = setTimeout(() => {
      this.timer = null;
      this.connect();
    }, delay);
  }

  send(msg: Record<string, unknown>) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  private route(msg: ServerMsg) {
    const st = useMirage.getState();
    switch (msg.type) {
      case "hello":
        st.set({ levels: msg.levels, rate: msg.rate, chain: msg.chain, embedder: msg.embedder,
                 status: msg.status === "live" ? "live" : msg.status === "error" ? "error" : "warming",
                 progress: msg.progress });
        break;
      case "status":
        st.set({ status: msg.status === "error" ? "error" : msg.status === "live" ? "live" : "warming",
                 progress: msg.progress ?? st.progress });
        break;
      case "snapshot": {
        scene.reset();
        const created = unpackF32(msg.accounts.created);
        scene.addAccounts(0, created.length, false);
        scene.setActivity(unpackU8(msg.accounts.activity));
        layout.reset();
        let clusters = null;
        if (msg.detection) {
          clusters = decodeClusters(msg.detection.clusters);
          scene.applyDetection(msg.detection, clusters);
          layout.graph();
        }
        const { clusters: _c, edges: _e, type: _t, ...rest } = msg.detection ?? ({} as never);
        st.set({
          status: "live", world: msg.world, tick: msg.tick, t: msg.t, clock: msg.clock, rate: msg.rate,
          nAccounts: msg.accounts.n, baselineAccounts: msg.accounts.n, proposals: msg.proposals,
          terrain: msg.terrain, launches: msg.launches, levels: msg.levels, chain: msg.chain,
          detection: msg.detection && clusters ? { ...rest, clusters } : null,
          metrics: msg.detection?.metrics ?? null, feed: [], evidence: null, evidenceFor: null,
          selected: null, lockedCluster: null, acquired: new Uint8Array(0),
        });
        break;
      }
      case "tick": {
        if (msg.world !== st.world) return;
        if (msg.n_accounts > scene.n) {
          scene.addAccounts(scene.n, msg.n_accounts - scene.n, true);
          layout.nodes();
        }
        scene.pulse(unpackI32(msg.active));
        st.set({
          tick: msg.tick, t: msg.t, clock: msg.clock, rate: msg.rate, nAccounts: msg.n_accounts,
          counts: msg.counts, proposals: msg.proposals,
          feed: [...msg.feed.reverse(), ...st.feed].slice(0, 40),
        });
        break;
      }
      case "detection": {
        if (msg.world !== st.world) return;
        const clusters = decodeClusters(msg.clusters);
        scene.applyDetection(msg, clusters);
        layout.graph();
        const { clusters: _c, edges: _e, type: _t, ...rest } = msg;
        const top = clusters.find((c) => c.verdict === "SWARM" && isFresh(c.members, st.acquired));
        const locked = top && top.confidence >= LOCK_CONFIDENCE ? top.id : null;
        if (locked !== null && st.lockedCluster === null) {
          st.fire({ kind: "lock", data: locked });
          const c = scene.clusters.find((x) => x.id === locked);
          if (c) scene.pulseWave = { t: performance.now() / 1000, origin: c.centroid };
          kickAberration(1.4);
        }
        st.set({
          detection: { ...rest, clusters }, metrics: msg.metrics, lockedCluster: locked ?? (top ? st.lockedCluster : null),
          latencyHistory: [...st.latencyHistory.slice(-59), msg.latency_ms],
        });
        if (st.selected !== null && st.evidenceFor === st.selected) this.send({ type: "evidence", cluster: st.selected });
        break;
      }
      case "terrain":
        st.set({ terrain: msg });
        break;
      case "evidence":
        st.set({ evidence: msg, evidenceFor: msg.cluster.id });
        break;
      case "launched": {
        // release the current target so the camera pulls back and the next
        // acquisition is about the swarm that was just launched
        const acquired = new Uint8Array(Math.max(scene.n, st.acquired.length));
        acquired.set(st.acquired);
        for (const c of st.detection?.clusters ?? []) {
          if (c.verdict === "SWARM") for (let k = 0; k < c.members.length; k++) acquired[c.members[k]] = 1;
        }
        const released = st.lockedCluster;
        st.set({
          launches: [...st.launches, msg],
          acquired,
          lockedCluster: null,
          selected: released !== null && st.selected === released ? null : st.selected,
        });
        st.fire({ kind: "launch", data: msg });
        break;
      }
      case "speed":
        st.set({ rate: msg.rate });
        break;
      case "chain": {
        const { type: _t, ...info } = msg;
        st.set({ chain: info });
        break;
      }
    }
  }
}

export const socket = new MirageSocket();

export const commands = {
  launch: (size: number, level: number) => socket.send({ type: "launch", size, level }),
  reset: () => socket.send({ type: "reset" }),
  speed: (rate: number) => socket.send({ type: "speed", rate }),
  evidence: (cluster: number) => socket.send({ type: "evidence", cluster }),
  weightMode: (mode: "one" | "log") => socket.send({ type: "weight_mode", mode }),
};
