# MIRAGE: build progress

A running log of what's done, what was measured, and the decisions made along the way.

## Status

| Milestone | State |
|---|---|
| 0. Repo + environment | done |
| 1. Simulator, detection engine, metrics (headless CLI) | done |
| 2. WebSocket streaming | done |
| 3. 3D scene with real layout | done |
| 4. Signature detection sequence + HUD | done |
| 5. Evidence panel, attacker console, metrics strip | done |
| 6. Governance contract + governance view | done |
| 7. Pulse Terrain view | done |
| 8. Demo Mode, sound, polish, perf | done |
| 9. One-command start, README, DEMO, final verification | done |

## Spec checklist

- [x] **Simulator.**
  - 3,000 real users with hidden profiles: rhythm, interests, money, ties, style.
  - Hard-negative organic communities: a club, a friend group with intra-group funding, a working group that votes as a bloc.
  - Swarm levels 1–5 attacking a treasury proposal.
- [x] **Signals.** Timing (band-pass DoG + PCA), content (MiniLM, centred), style (stylometry), behaviour (session n-grams + co-actions, SVD), funding (ancestry with exchange hubs), social (mutual follows).
- [x] **Graph and communities.**
  - FAISS kNN per signal, z-scored against a live random-pair baseline.
  - Fused graph with single-signal down-weighting.
  - Leiden communities, then CPM refinement and consolidation.
- [x] **Scoring.** Family strengths feed a noisy-OR confidence, behind a corroboration gate that needs a behavioural *and* a coordination family. Verdicts are SWARM / ORGANIC COMMUNITY / NORMAL, with a level estimate.
- [x] **Evidence and speed.** Plain-language evidence with numbers against baselines. Under 1 s per run at 5k accounts (p50 0.58 s).
- [x] **Metrics.** Precision, recall, F1, hard-negative FP, detection latency and per-swarm recall.
- [x] **Label isolation.** Four checks: static imports, object graph, tripwire and label-scramble invariance.
- [x] **Streaming.** FastAPI WebSocket with per-client queues that drop stale ticks when a client lags.
- [x] **Frontend.**
  - 10k+ node WebGL network with a worker force layout.
  - Lock-on sequence with the HUD ring and readout.
  - Evidence panel (timeline, funding tree, heatmap, posts).
  - Pulse Terrain and the governance view with the on-chain flip.
  - Attacker console with per-launch "% flagged", metrics strip with a LIVE indicator and a latency sparkline.
  - Demo Mode (live, not scripted) and synthesized sound.
- [x] **Governance.** `MirageGovernance.sol` on a local chain:
  - registration and EIP-191 per-account signed votes;
  - oracle epochs with incremental cluster tallies;
  - naive and weighted tallies (ONE / LOG, on-chain `ln`);
  - 9 contract tests.
- [x] **One command.**
  - `npm run setup`, then `npm run dev` (or `npm start` for a production build), which starts chain → deploy → backend → web.
  - Works offline after setup.
- [x] **Docs.** README (problem, mermaid architecture, results, cost model, honest limits) and DEMO.md (3-minute pitch plus judge Q&A).
- [x] **Tests.** `npm test` runs backend pytest (41 tests, plus the machine-dependent latency test with `--slow`), the 9 contract tests and the web type-check. ESLint is clean.

## Measured (seed 7, 3,000 real users + 1,000-agent swarm, 36 h)

| level | precision | recall | hard-neg FP | detected after |
| --- | ---: | ---: | ---: | ---: |
| 1 | 100% | 100% | 0 | ~3 h |
| 2 | 100% | 100% | 0 | ~3 h |
| 3 | 100% | 100% | 0 | ~7 h |
| 4 | 100% | 94.6% | 0 | ~5 h |
| 5 | — | 0% | 0 | not detected (by design: see the README cost model) |

Pipeline latency:

- quiet 5,127-account world: p50 0.58 s, p95 0.66 s;
- with a 1,000-agent swarm (~6,100 accounts): p50 0.79 s, p95 1.06 s.

Laptop with an RTX 4070 Laptop GPU; embedding overlaps the CPU signals.

Frontend: 10,375 nodes (a 7,000-agent swarm) at a steady 60 fps, 1920×1080. The p95 frame is 16.7 ms, with one frame over 33 ms in a 10 s window and no long tasks.

## Decisions

- **Chain tooling: Hardhat instead of Foundry.** Foundry isn't installed on the
  build machine, and Hardhat installs through npm with the rest of the frontend,
  which keeps "one command starts everything" true on Windows, macOS and Linux.
- **The Python env can reuse system site-packages** (`venv --system-site-packages`),
  so an existing torch / sentence-transformers install is picked up instead of
  re-downloading gigabytes. The embedder falls back to a hashing + random
  projection model when sentence-transformers is missing, so nothing
  hard-depends on torch (`npm run setup -- --light`).
- **Timing is band-passed, not raw.** Everyone sleeps at night. Raw activity
  correlation made a giant "real users" cluster. A difference-of-Gaussians
  band-pass keeps the operator's triggers and removes the shared day/night cycle.
- **Corroboration gate over thresholds.** Real communities share topics,
  styles and even funding (the friend group). Requiring a behavioural family
  *and* a coordination family is what keeps every hard negative unflagged.
- **Re-weight, don't ban.** A flagged cluster keeps its accounts and loses its
  multiplier. That bounds the cost of a false positive and is simple to verify on-chain.
- **24 h maturity + evidence memory.** No verdict before a cluster has been observed
  for a day, and evidence decays with a 24 h half-life. Together they stop early
  flicker on small real groups and keep quiet swarms flagged.
- **Oracle epochs, not per-vote oracle calls.** Cluster membership is attested
  in chunks per epoch, and the contract maintains per-cluster yes/no counts
  incrementally, so reading a weighted tally loops over flagged clusters, not voters.
- **Proposal ids are salted per backend session and world**, so restarting the
  backend or resetting the world never collides with votes already on-chain.
- **Demo Mode is a director, not an animation.** It resets to a seeded world,
  issues the same commands a user would, and waits on real events (lock,
  evidence), so the story always matches the live numbers.
- **Target lock follows fresh swarms.** A new launch releases the current
  target. Swarms already caught stay red but don't steal the lock, because
  "already acquired" is decided by member overlap, which survives cluster re-identification.

## Next (beyond the hackathon)

- Several independent detectors, threshold-signed attestations and a dispute window (see README, *Honest limits*).
- Calibrate the baseline on a real indexer feed (Farcaster / Snapshot / on-chain transfers).
- Longer-horizon lifecycle signals to raise the cost of level 4 further.
