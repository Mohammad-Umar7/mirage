#!/usr/bin/env node
// Every test suite in one go: backend (pytest), contracts (hardhat), web (types).
//   npm test               fast suites
//   npm test -- --slow     also the machine-dependent 5k-account latency test
import path from "node:path";
import { banner, c, fail, findPython, ROOT, run } from "./_util.mjs";

const slow = process.argv.includes("--slow");
const py = findPython({ venvOnly: true });
if (!py) fail(`backend/.venv is missing — run ${c.gold("npm run setup")} first.`);

const suites = [
  ["backend · pytest", py.cmd, [...py.args, "-m", "pytest", "-q", ...(slow ? ["-m", "slow or not slow"] : [])], "backend"],
  ["contracts · hardhat test", "npx", ["hardhat", "test"], "contracts"],
  ["web · type-check", "npx", ["tsc", "--noEmit", "-p", "."], "web"],
];

const results = [];
for (const [name, cmd, args, dir] of suites) {
  banner(name);
  const t = Date.now();
  const code = await run(cmd, args, { cwd: path.join(ROOT, dir) });
  results.push({ name, ok: code === 0, secs: ((Date.now() - t) / 1000).toFixed(1) });
}

console.log("");
for (const r of results) console.log(`  ${r.ok ? c.green("✓") : c.red("✖")} ${r.name} ${c.dim(`${r.secs}s`)}`);
console.log("");
process.exit(results.every((r) => r.ok) ? 0 : 1);
