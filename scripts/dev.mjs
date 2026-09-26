#!/usr/bin/env node
// One command for the whole stack:
//   local chain → MirageGovernance deployment → detection backend → web app
//
//   npm run dev                  everything, Next.js in dev mode
//   npm start                    everything, production build of the web app
//   npm run dev -- --no-chain    skip the chain (tallies are computed off-chain only)
//   npm run chain                only the local chain + contract deployment
//
// Services that are already running on their ports are reused, not restarted.
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import {
  banner, c, fail, findPython, getJson, httpOk, killTree, loadEnv, ROOT, rpc, run, service, until,
} from "./_util.mjs";

loadEnv();
const flags = new Set(process.argv.slice(2));
const PROD = flags.has("--prod");
const CHAIN_ONLY = flags.has("--chain-only");
const NO_CHAIN = !CHAIN_ONLY && (flags.has("--no-chain") || process.env.MIRAGE_CHAIN === "0");
const API_PORT = Number(process.env.MIRAGE_API_PORT ?? 8000);
const WEB_PORT = Number(process.env.MIRAGE_WEB_PORT ?? 3000);
const RPC = "http://127.0.0.1:8545"; // fixed by contracts/hardhat.config.ts
const DEPLOYMENT = path.join(ROOT, "deployments", "local.json");

const children = [];
let stopping = false;
function shutdown(code = 0) {
  if (stopping) return;
  stopping = true;
  console.log(c.dim("\nstopping MIRAGE…"));
  for (const child of children.reverse()) killTree(child);
  setTimeout(() => process.exit(code), 300);
}
process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

function supervise(name, child) {
  children.push(child);
  child.on("exit", (code) => {
    if (!stopping) {
      console.error(c.red(`\n${name} exited (${code ?? "signal"}); shutting down`));
      shutdown(code || 1);
    }
  });
  return child;
}

function need(dir, what) {
  if (!existsSync(path.join(ROOT, dir))) fail(`${what} is missing — run ${c.gold("npm run setup")} first.`);
}

// ------------------------------------------------------------------ chain
async function chain() {
  need("contracts/node_modules", "contracts/node_modules");
  const up = async () => (await rpc(RPC, "eth_chainId")) === "0x7a69";
  if (await up().catch(() => false)) {
    console.log(`${c.violet("chain │")} reusing the node already on ${RPC}`);
  } else {
    banner("starting local chain (Hardhat, chain 31337)");
    supervise("chain", service("chain", c.violet, "npx", ["hardhat", "node", "--hostname", "127.0.0.1", "--port", "8545"], {
      cwd: path.join(ROOT, "contracts"),
      // the node logs every RPC call; keep only its banner line and real problems
      keep: (line) => /Started HTTP|error|warning/i.test(line) && !/eth_|Contract call|Transaction:/.test(line),
    }));
    if (!(await until(up, { timeoutMs: 60_000 }))) fail("the local chain did not come up on :8545");
  }

  // redeploy unless the recorded contract is live on this node
  let live = false;
  if (existsSync(DEPLOYMENT)) {
    const { address } = JSON.parse(readFileSync(DEPLOYMENT, "utf8"));
    const code = await rpc(RPC, "eth_getCode", [address, "latest"]).catch(() => "0x");
    live = !!code && code !== "0x";
  }
  if (live) {
    console.log(`${c.violet("chain │")} MirageGovernance already deployed`);
  } else {
    banner("deploying MirageGovernance");
    const code = await run("npx", ["hardhat", "run", "scripts/deploy.ts", "--network", "localhost"], {
      cwd: path.join(ROOT, "contracts"),
    });
    if (code !== 0) fail("contract deployment failed");
  }
}

// ---------------------------------------------------------------- backend
async function backend() {
  const health = `http://127.0.0.1:${API_PORT}/health`;
  if (await getJson(health).catch(() => null)) {
    console.log(`${c.blue("api   │")} reusing the backend already on :${API_PORT}`);
    return;
  }
  const py = findPython({ venvOnly: true });
  if (!py) fail(`backend/.venv is missing — run ${c.gold("npm run setup")} first.`);
  banner(`starting detection backend on :${API_PORT}`);
  supervise("backend", service("api", c.blue, py.cmd, [...py.args, "-u", "-m", "mirage.server"], {
    cwd: path.join(ROOT, "backend"),
    env: { ...process.env, MIRAGE_CHAIN: NO_CHAIN ? "0" : "1", PYTHONUNBUFFERED: "1" },
  }));
  let last = -1;
  const ok = await until(
    async () => {
      const h = await getJson(health);
      if (!h) return null;
      const pct = Math.round((h.progress ?? 0) * 100);
      if (h.status === "warming" && pct !== last && pct % 10 === 0) {
        last = pct;
        console.log(`${c.blue("api   │")} warming up the world… ${pct}%`);
      }
      return h.status === "live" || h.status === "error" ? h : null;
    },
    { timeoutMs: 600_000, everyMs: 700 },
  );
  if (!ok) fail("the backend did not go live");
  if (ok.status === "error") fail("the backend failed while warming up (see the api │ lines above)");
}

// -------------------------------------------------------------------- web
async function web() {
  need("web/node_modules", "web/node_modules");
  const url = `http://localhost:${WEB_PORT}`;
  if (await httpOk(url).catch(() => false)) {
    console.log(`${c.gold("web   │")} reusing the web app already on :${WEB_PORT}`);
    return url;
  }
  const env = { ...process.env, PORT: String(WEB_PORT) };
  if (API_PORT !== 8000) env.NEXT_PUBLIC_MIRAGE_WS ??= `ws://localhost:${API_PORT}/ws`;
  const cwd = path.join(ROOT, "web");
  if (PROD) {
    banner("building the web app");
    if ((await run("npm", ["run", "build"], { cwd, env })) !== 0) fail("next build failed");
    banner(`serving the web app on :${WEB_PORT}`);
    supervise("web", service("web", c.gold, "npx", ["next", "start", "-p", String(WEB_PORT)], { cwd, env }));
  } else {
    banner(`starting the web app on :${WEB_PORT}`);
    supervise("web", service("web", c.gold, "npx", ["next", "dev", "-p", String(WEB_PORT)], { cwd, env }));
  }
  if (!(await until(() => httpOk(url), { timeoutMs: 180_000 }))) fail("the web app did not come up");
  return url;
}

// ------------------------------------------------------------------- main
const started = Date.now();
if (!NO_CHAIN) await chain();
if (CHAIN_ONLY) {
  console.log(`\n${c.green("●")} chain ready at ${RPC} — Ctrl+C to stop`);
  if (!children.length) process.exit(0);
} else {
  await backend();
  const url = await web();
  const secs = ((Date.now() - started) / 1000).toFixed(0);
  console.log(
    `\n${c.gold("◆ MIRAGE is live")} ${c.dim(`(${secs}s)`)}\n` +
      `  ${c.bold("open")}      ${url}\n` +
      `  ${c.dim("backend")}   ws://localhost:${API_PORT}/ws\n` +
      `  ${c.dim("chain")}     ${NO_CHAIN ? "off (--no-chain)" : `${RPC} · MirageGovernance`}\n` +
      `  ${c.dim("demo")}      press ${c.gold("D")} in the app for the 90-second Demo Mode · ${c.gold("M")} for sound\n` +
      `  ${c.dim("stop")}      Ctrl+C stops every service started here\n`,
  );
  if (!children.length) process.exit(0);
}
