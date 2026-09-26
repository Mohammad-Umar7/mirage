import { create } from "zustand";
import type {
  ChainInfo,
  Cluster,
  DetectionMsg,
  EvidenceDetail,
  FeedItem,
  Launch,
  Level,
  Metrics,
  Proposal,
  TerrainMsg,
} from "./protocol";

export type Status = "connecting" | "warming" | "live" | "reconnecting" | "error";
export type View = "network" | "terrain" | "governance";

export type Detection = Omit<DetectionMsg, "clusters" | "edges" | "type"> & { clusters: Cluster[] };

export type DemoState = { active: boolean; step: number; caption: string | null; sub: string | null };

export type FxEvent = { kind: "launch" | "lock" | "pulse" | "flip"; at: number; data?: unknown };

type State = {
  status: Status;
  progress: number;
  connected: boolean;
  world: number;
  tick: number;
  t: number;
  clock: string;
  rate: number;
  nAccounts: number;
  baselineAccounts: number;
  counts: { events: number; posts: number; tick_events: number; tick_posts: number; tick_votes: number };
  levels: Level[];
  launches: Launch[];
  detection: Detection | null;
  metrics: Metrics | null;
  proposals: Proposal[];
  terrain: TerrainMsg | null;
  feed: FeedItem[];
  evidence: EvidenceDetail | null;
  evidenceFor: number | null;
  selected: number | null;
  lockedCluster: number | null;
  /** accounts in swarms acquired before the latest launch; a launch re-arms the lock for fresh targets only */
  acquired: Uint8Array;
  view: View;
  sound: boolean;
  demo: DemoState;
  chain: ChainInfo | null;
  fx: FxEvent[];
  latencyHistory: number[];
  embedder: string;

  set: (p: Partial<State>) => void;
  select: (id: number | null) => void;
  setView: (v: View) => void;
  fire: (e: Omit<FxEvent, "at">) => void;
};

export const useMirage = create<State>((set, get) => ({
  status: "connecting",
  progress: 0,
  connected: false,
  world: 0,
  tick: 0,
  t: 0,
  clock: "DAY 0 · 00:00",
  rate: 1,
  nAccounts: 0,
  baselineAccounts: 0,
  counts: { events: 0, posts: 0, tick_events: 0, tick_posts: 0, tick_votes: 0 },
  levels: [],
  launches: [],
  detection: null,
  metrics: null,
  proposals: [],
  terrain: null,
  feed: [],
  evidence: null,
  evidenceFor: null,
  selected: null,
  lockedCluster: null,
  acquired: new Uint8Array(0),
  view: "network",
  sound: false,
  demo: { active: false, step: 0, caption: null, sub: null },
  chain: null,
  fx: [],
  latencyHistory: [],
  embedder: "",

  set: (p) => set(p),
  select: (id) => set({ selected: id, evidence: id === get().evidenceFor ? get().evidence : null }),
  setView: (v) => set({ view: v }),
  fire: (e) => set({ fx: [...get().fx.slice(-12), { ...e, at: performance.now() / 1000 }] }),
}));
