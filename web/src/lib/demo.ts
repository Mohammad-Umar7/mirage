"use client";

// Demo Mode: a ~90 second story told by the REAL pipeline. The director only
// issues commands (reset, launch, change view, open evidence) and waits for
// the live detector to deliver; nothing on screen is scripted animation.
import { commands } from "./socket";
import { useMirage } from "./store";
import { view as viewState } from "./viewState";

let controller: AbortController | null = null;

class Aborted extends Error {}

function sleep(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new Aborted());
    });
  });
}

function waitFor(pred: () => boolean, timeoutMs: number, signal: AbortSignal) {
  return new Promise<boolean>((resolve, reject) => {
    if (pred()) return resolve(true);
    const started = Date.now();
    const unsub = useMirage.subscribe(() => {
      if (pred()) {
        cleanup();
        resolve(true);
      }
    });
    const t = setInterval(() => {
      if (Date.now() - started > timeoutMs) {
        cleanup();
        resolve(false);
      }
    }, 200);
    const cleanup = () => {
      unsub();
      clearInterval(t);
    };
    signal.addEventListener("abort", () => {
      cleanup();
      reject(new Aborted());
    });
  });
}

function caption(text: string | null, sub: string | null = null, step?: number) {
  const st = useMirage.getState();
  st.set({ demo: { ...st.demo, caption: text, sub, step: step ?? st.demo.step } });
}

function lockLine() {
  const st = useMirage.getState();
  const c = st.detection?.clusters.find((x) => x.id === st.lockedCluster);
  if (!c || !st.detection) return "swarm detected";
  const launch = st.launches[st.launches.length - 1];
  const hours = launch ? Math.max(1, Math.round(((c.flagged_since ?? st.detection.t) - launch.t) / 60)) : null;
  const when = hours !== null ? ` · flagged ${hours} sim-hours after launch` : "";
  return `${c.size.toLocaleString()} accounts · confidence ${c.confidence.toFixed(2)}${when}`;
}

function fadeLine() {
  const st = useMirage.getState();
  const launch = [...st.launches].reverse().find((l) => l.level === 5);
  const score = launch && st.metrics?.per_swarm?.find((p) => p.swarm === launch.swarm);
  const flagged = score && score.recall !== null ? `level-5 swarm: ${Math.round(score.recall * 100)}% flagged · ` : "";
  return `${flagged}each identity costs ~$48 instead of $1.20 — independence is the expensive part`;
}

async function story(signal: AbortSignal) {
  const st = useMirage.getState;
  st().set({ view: "network", selected: null });
  viewState.cameraOverride = null;

  // 0 — a fresh, identical world
  const before = st().world;
  commands.reset();
  await waitFor(() => st().world !== before, 15000, signal);
  st().set({ demo: { active: true, step: 0, caption: "MIRAGE", sub: "intro" } });
  await sleep(3800, signal);

  // 1 — the network as it is
  caption("3,000 people. Each one independent.", "every gold point is a real account — its own rhythm, interests, money and voice", 1);
  await sleep(6000, signal);

  // 2 — the attack
  caption("An operator launches 1,000 AI agents.", "level 3 · multi-hop funding · persona-diverse LLM text · fake circadian rhythms", 2);
  commands.launch(1000, 3);
  const launchedAt = Date.now();
  // the live detector sets the pace: if it hasn't locked yet, say what we're looking at
  if (!(await waitFor(() => st().lockedCluster !== null, 6500, signal))) {
    caption("Each one looks like an ordinary person.", "nothing on the map looks wrong — yet", 2);
    await waitFor(() => st().lockedCluster !== null, 40000, signal);
  }
  const shown = Date.now() - launchedAt;
  if (shown < 3200) await sleep(3200 - shown, signal);

  // 3 — detection: the caption follows the locked cluster as the swarm keeps arriving
  const lockedAt = Date.now();
  while (Date.now() - lockedAt < 7000) {
    caption("Together, they're a mirage.", lockLine(), 3);
    await sleep(400, signal);
  }

  // 4 — evidence
  const locked = st().lockedCluster;
  if (locked !== null) {
    st().select(locked);
    commands.evidence(locked);
  }
  caption("One budget. One generator. One clock.", "funding ancestry, writing fingerprint, synchronized waves — every flag comes with numbers", 4);
  await sleep(12500, signal);
  st().select(null);

  // 5 — pulse terrain
  st().setView("terrain");
  caption("Their pulse gives them away.", "real people make gentle waves · one operator makes synchronized ridges", 5);
  await sleep(8500, signal);

  // 6 — governance flip
  st().setView("governance");
  caption("One account, one vote: the swarm wins.", "proposal: transfer the community treasury to the attacker", 6);
  await sleep(6000, signal);
  st().fire({ kind: "flip" });
  caption("Correlation-weighted: 1,000 puppets count as one voice.", "the honest result wins · tallied on-chain by the MirageGovernance contract", 6);
  await sleep(8000, signal);

  // 7 — escalate to level 5, honestly (the launch releases the old target)
  st().setView("network");
  caption("Level 5: truly independent agents.", "separate budgets · separate generators · no shared triggers", 7);
  commands.launch(1000, 5);
  await sleep(9000, signal);
  const fadedAt = Date.now();
  while (Date.now() - fadedAt < 9000) {
    caption("Detection fades — and that's the honest answer.", fadeLine(), 7);
    await sleep(500, signal);
  }

  // 8 — the line
  caption("Faking one person is cheap.", "Faking ten thousand independent people isn't.", 8);
  await sleep(7000, signal);
}

export async function startDemo() {
  stopDemo();
  const ctl = new AbortController();
  controller = ctl;
  useMirage.getState().set({ demo: { active: true, step: 0, caption: null, sub: null } });
  try {
    await story(ctl.signal);
  } catch (err) {
    if (!(err instanceof Aborted)) console.error("[mirage] demo failed", err);
  } finally {
    if (controller === ctl) {
      controller = null;
      viewState.cameraOverride = null;
      useMirage.getState().set({ demo: { active: false, step: 0, caption: null, sub: null } });
    }
  }
}

export function stopDemo() {
  if (controller) {
    controller.abort();
    controller = null;
  }
  viewState.cameraOverride = null;
  useMirage.getState().set({ demo: { active: false, step: 0, caption: null, sub: null } });
}

export function demoRunning() {
  return controller !== null;
}
