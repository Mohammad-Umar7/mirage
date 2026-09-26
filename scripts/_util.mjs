// Small cross-platform helpers shared by setup / dev / test scripts.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const WIN = process.platform === "win32";

const tty = process.stdout.isTTY && !process.env.NO_COLOR;
const paint = (code) => (s) => (tty ? `\x1b[${code}m${s}\x1b[0m` : String(s));
export const c = {
  gold: paint("38;5;214"),
  red: paint("38;5;203"),
  dim: paint("2"),
  bold: paint("1"),
  green: paint("38;5;114"),
  blue: paint("38;5;110"),
  violet: paint("38;5;141"),
};

export function banner(text) {
  console.log(`\n${c.gold("◆")} ${c.bold(text)}`);
}

export function fail(message) {
  console.error(`\n${c.red("✖")} ${message}\n`);
  process.exit(1);
}

/** KEY=VALUE lines from the repo .env; real environment variables win. */
export function loadEnv(file = path.join(ROOT, ".env")) {
  if (!existsSync(file)) return;
  for (const raw of readFileSync(file, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const i = line.indexOf("=");
    const key = line.slice(0, i).trim();
    const value = line.slice(i + 1).trim().replace(/^['"]|['"]$/g, "");
    if (key && value && process.env[key] === undefined) process.env[key] = value;
  }
}

/** The backend venv interpreter if present, else a system Python >= 3.10. */
export function findPython({ venvOnly = false } = {}) {
  const venv = path.join(ROOT, "backend", ".venv", WIN ? "Scripts/python.exe" : "bin/python");
  if (existsSync(venv)) return { cmd: venv, args: [] };
  if (venvOnly) return null;
  return systemPython();
}

export function systemPython() {
  const candidates = [];
  if (process.env.PYTHON) candidates.push({ cmd: process.env.PYTHON, args: [] });
  if (WIN) candidates.push({ cmd: "py", args: ["-3.11"] }, { cmd: "py", args: ["-3"] });
  candidates.push({ cmd: "python3", args: [] }, { cmd: "python", args: [] });
  for (const cand of candidates) {
    const r = spawnSync(cand.cmd, [...cand.args, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"], {
      encoding: "utf8",
    });
    if (r.status !== 0 || !r.stdout) continue;
    const [major, minor] = r.stdout.trim().split(".").map(Number);
    if (major === 3 && minor >= 10) return { ...cand, version: r.stdout.trim() };
  }
  return null;
}

/** Run a command to completion, streaming output. Resolves with the exit code. */
export function run(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, { stdio: "inherit", shell: WIN && !cmd.endsWith(".exe"), ...opts });
    child.on("exit", (code) => resolve(code ?? 1));
    child.on("error", () => resolve(127));
  });
}

/** Start a long-running service whose output lines are tagged with its name.
 *  `keep` optionally filters which lines are shown. */
export function service(name, color, cmd, args, { keep, ...opts } = {}) {
  const child = spawn(cmd, args, {
    stdio: ["ignore", "pipe", "pipe"],
    shell: WIN && !cmd.endsWith(".exe"),
    detached: !WIN,
    ...opts,
  });
  const tag = color(`${name.padEnd(5)} │`);
  const pipe = (stream, sink) => {
    let buf = "";
    stream.setEncoding("utf8");
    stream.on("data", (chunk) => {
      buf += chunk;
      const lines = buf.split(/\r?\n/);
      buf = lines.pop() ?? "";
      for (const line of lines) if (line.trim() && (!keep || keep(line))) sink.write(`${tag} ${line}\n`);
    });
  };
  pipe(child.stdout, process.stdout);
  pipe(child.stderr, process.stderr);
  return child;
}

/** Kill a child and everything it spawned (npm → node → next, venv launcher → python). */
export function killTree(child) {
  if (!child || child.exitCode !== null || child.pid === undefined) return;
  try {
    if (WIN) spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    else process.kill(-child.pid, "SIGTERM");
  } catch {
    /* already gone */
  }
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Poll `probe` until it returns a truthy value or the deadline passes. */
export async function until(probe, { timeoutMs = 120_000, everyMs = 500, onTick } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const v = await probe();
      if (v) return v;
    } catch {
      /* not up yet */
    }
    onTick?.();
    await sleep(everyMs);
  }
  return null;
}

export async function rpc(url, method, params = []) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
    signal: AbortSignal.timeout(2000),
  });
  const body = await res.json();
  return body.result;
}

export async function getJson(url) {
  const res = await fetch(url, { signal: AbortSignal.timeout(2000) });
  if (!res.ok) return null;
  return res.json();
}

export async function httpOk(url) {
  const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
  return res.status < 500;
}
