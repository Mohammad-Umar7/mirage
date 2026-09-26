# MIRAGE — build progress

Running log of what is done, what is next, and the decisions made along the way.

## Status

| Milestone | State |
|---|---|
| 0. Repo + environment | in progress |
| 1. Simulator, detection engine, metrics (headless CLI) | todo |
| 2. WebSocket streaming | todo |
| 3. 3D scene with real layout | todo |
| 4. Signature detection sequence + HUD | todo |
| 5. Evidence panel, attacker console, metrics strip | todo |
| 6. Governance contract + governance view | todo |
| 7. Pulse Terrain view | todo |
| 8. Demo Mode, sound, polish, perf | todo |

## Decisions

- **Chain tooling: Hardhat instead of Foundry.** Foundry is not installed on the
  build machine and Hardhat installs through npm with the rest of the frontend,
  which keeps "one command starts everything" true on Windows/macOS/Linux.
- **Python env reuses system site-packages** (`venv --system-site-packages`) so an
  existing torch / sentence-transformers install is picked up instead of
  re-downloading gigabytes. The embedder falls back to a hashing + SVD model when
  sentence-transformers is missing, so nothing hard-depends on torch.

## Next

- Simulator core (clock, accounts, events, population).
