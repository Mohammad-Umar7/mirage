// Wire types for the MIRAGE backend stream (see backend/mirage/server).

export type Packed = { dtype: "i4" | "f4" | "u1"; n: number; b64: string };

export type Verdict = "SWARM" | "ORGANIC COMMUNITY" | "NORMAL";

export type Evidence = {
  family: string;
  title: string;
  text: string;
  value: number | null;
  baseline: number | null;
  strength: number | null;
};

export type ClusterWire = {
  id: number;
  verdict: Verdict;
  confidence: number;
  level_estimate: number | null;
  size: number;
  metrics: Record<string, number | string | null>;
  strengths: Record<string, number | null>;
  evidence: Evidence[];
  first_seen: number;
  flagged_since: number | null;
  members: Packed;
  watch: boolean;
};

export type Cluster = Omit<ClusterWire, "members"> & { members: Int32Array };

export type Metrics = {
  precision: number | null;
  recall: number | null;
  f1: number | null;
  hard_negative_fp: number;
  flagged: number;
  tp: number;
  fp: number;
  fn: number;
  detection_latency_min: number | null;
  pipeline_latency_ms: number;
  per_swarm?: SwarmScore[];
};

export type SwarmScore = { swarm: number; level: number; size: number; recall: number | null; latency_min: number | null };

export type Tally = { yes: number; no: number };

export type Proposal = {
  id: number;
  title: string;
  recipient: string;
  amount: number;
  created_at: number;
  closes_at: number;
  open: boolean;
  naive: Tally;
  weighted: Tally;
  votes: number;
};

export type Level = { level: number; name: string; summary: string; cost_per_identity: number };

export type FeedItem = {
  post: number;
  account: number;
  handle: string;
  text: string;
  t: number;
  reply: boolean;
  verdict: Verdict | null;
};

export type Launch = {
  swarm: number;
  level: number;
  size: number;
  proposal: number;
  t: number;
  clock: string;
  name: string;
  cost_per_identity: number;
};

export type DetectionMsg = {
  type: "detection";
  world: number;
  run: number;
  t: number;
  clock: string;
  latency_ms: number;
  stages: Record<string, number>;
  n_accounts: number;
  n_active: number;
  n_candidates: number;
  embedder: string;
  knn: string;
  clusters: ClusterWire[];
  edges: { i: Packed; j: Packed; w: Packed; bits: Packed };
  metrics: Metrics;
  weight_mode: "one" | "log";
};

export type TerrainLane = { kind: "swarm" | "organic" | "normal"; cluster: number; size: number; values: number[] };
export type TerrainMsg = { type: "terrain"; bin_minutes: number; end: number; lanes: TerrainLane[] };

export type TickMsg = {
  type: "tick";
  world: number;
  tick: number;
  t: number;
  clock: string;
  n_accounts: number;
  new_from: number;
  new_created: number[];
  active: Packed;
  counts: { events: number; posts: number; tick_events: number; tick_posts: number; tick_votes: number };
  feed: FeedItem[];
  proposals: Proposal[];
  rate: number;
};

export type ChainTx = { hash: string; kind: string; detail: string; block: number | null; t: number };
export type ChainInfo = {
  connected: boolean;
  rpc: string;
  chain_id: number | null;
  address: string | null;
  oracle: string | null;
  block: number | null;
  mode: "one" | "log";
  txs: ChainTx[];
  onchain: Record<string, { naive: Tally; weighted: Tally; epoch: number }>;
  error?: string | null;
  world?: number;
  pid_base?: number;
};

export type SnapshotMsg = {
  type: "snapshot";
  world: number;
  status: string;
  tick: number;
  t: number;
  clock: string;
  rate: number;
  accounts: { n: number; created: Packed; activity: Packed };
  proposals: Proposal[];
  detection: DetectionMsg | null;
  terrain: TerrainMsg | null;
  launches: Launch[];
  levels: Level[];
  chain: ChainInfo | null;
};

export type EvidenceDetail = {
  type: "evidence";
  cluster: Omit<ClusterWire, "members" | "watch">;
  timeline: { bin_minutes: number; end: number; cluster: number[]; baseline: number[] };
  funding: {
    nodes: { id: number; kind: "account" | "wallet" | "root" | "hub"; label: string; depth: number }[];
    edges: [number, number][];
    accounts: number;
    roots: number;
    max_depth: number;
  };
  heatmap: { size: number; split: number; values: number[] };
  posts: { handle: string; text: string; t: number }[];
};

export type ServerMsg =
  | { type: "hello"; status: string; progress: number; levels: Level[]; rate: number; tick_minutes: number; embedder: string; max_swarm: number; chain: ChainInfo | null }
  | { type: "status"; status: string; progress?: number }
  | SnapshotMsg
  | TickMsg
  | DetectionMsg
  | TerrainMsg
  | EvidenceDetail
  | ({ type: "launched" } & Launch)
  | { type: "speed"; rate: number }
  | ({ type: "chain" } & ChainInfo)
  | { type: "pong"; t: number };

function bytes(b64: string): Uint8Array<ArrayBuffer> {
  const bin = atob(b64);
  const out = new Uint8Array(new ArrayBuffer(bin.length));
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export function unpackI32(p: Packed): Int32Array<ArrayBuffer> {
  const u8 = bytes(p.b64);
  return new Int32Array(u8.buffer, u8.byteOffset, u8.byteLength / 4);
}

export function unpackF32(p: Packed): Float32Array<ArrayBuffer> {
  const u8 = bytes(p.b64);
  return new Float32Array(u8.buffer, u8.byteOffset, u8.byteLength / 4);
}

export function unpackU8(p: Packed): Uint8Array<ArrayBuffer> {
  return bytes(p.b64);
}

export function decodeClusters(list: ClusterWire[]): Cluster[] {
  return list.map((c) => ({ ...c, members: unpackI32(c.members) }));
}
