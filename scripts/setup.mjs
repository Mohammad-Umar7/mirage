#!/usr/bin/env node
// One-time setup: Python venv + backend deps, npm deps, contract compile,
// and a warm local copy of the embedding model so later runs work offline.
//
//   npm run setup                 everything (includes sentence-transformers + faiss)
//   npm run setup -- --light      core only: hashing embedder, no torch download
import { existsSync, readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { banner, c, fail, findPython, ROOT, run, systemPython } from "./_util.mjs";

const flags = new Set(process.argv.slice(2));
const LIGHT = flags.has("--light");
const t0 = Date.now();

const [major] = process.versions.node.split(".").map(Number);
if (major < 18) fail(`Node ${process.versions.node} is too old — MIRAGE needs Node 18 or newer.`);

// ---------------------------------------------------------------- python
banner("Python backend");
let py = findPython({ venvOnly: true });
if (!py) {
  const sys = systemPython();
  if (!sys) fail("Python 3.10+ was not found. Install it (3.11 recommended) or set PYTHON=/path/to/python.");
  console.log(c.dim(`creating backend/.venv with Python ${sys.version}`));
  if ((await run(sys.cmd, [...sys.args, "-m", "venv", path.join(ROOT, "backend", ".venv")])) !== 0) {
    fail("could not create the virtual environment");
  }
  py = findPython({ venvOnly: true });
}
const pip = (...args) => run(py.cmd, [...py.args, "-m", "pip", ...args], { cwd: path.join(ROOT, "backend") });
await pip("install", "--upgrade", "pip", "--quiet");

let requirements = path.join(ROOT, "backend", "requirements.txt");
if (LIGHT) {
  // drop the optional embedding stack; the hashing embedder takes over
  const core = readFileSync(requirements, "utf8")
    .split(/\r?\n/)
    .filter((l) => !/^(sentence-transformers|faiss-cpu)\b/.test(l.trim()))
    .join("\n");
  requirements = path.join(mkdtempSync(path.join(tmpdir(), "mirage-")), "requirements-core.txt");
  writeFileSync(requirements, core);
  console.log(c.dim("--light: skipping sentence-transformers and faiss (hashing embedder + sklearn kNN)"));
}
if ((await pip("install", "-r", requirements)) !== 0) fail("pip install failed");

if (!LIGHT) {
  banner("caching the MiniLM embedding model for offline runs");
  const warm = "from mirage.detect.embed import make_embedder; e = make_embedder('auto'); print('embedder:', e.name, e.dim)";
  if ((await run(py.cmd, [...py.args, "-c", warm], { cwd: path.join(ROOT, "backend") })) !== 0) {
    console.log(c.dim("model download failed — MIRAGE will fall back to the hashing embedder"));
  }
}

// ------------------------------------------------------------------ node
for (const dir of ["contracts", "web"]) {
  banner(`npm dependencies · ${dir}`);
  const cwd = path.join(ROOT, dir);
  const cmd = existsSync(path.join(cwd, "package-lock.json")) ? "ci" : "install";
  if ((await run("npm", [cmd, "--no-audit", "--no-fund"], { cwd })) !== 0) fail(`npm ${cmd} failed in ${dir}/`);
}

banner("compiling MirageGovernance");
if ((await run("npx", ["hardhat", "compile"], { cwd: path.join(ROOT, "contracts") })) !== 0) fail("contract compile failed");

const secs = ((Date.now() - t0) / 1000).toFixed(0);
console.log(`\n${c.gold("◆ setup complete")} ${c.dim(`(${secs}s)`)} — now run ${c.gold("npm run dev")}\n`);
