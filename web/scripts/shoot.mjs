// Full-resolution screenshots of the running UI, driven by a small plan.
//
//   node scripts/shoot.mjs --plan "wait:6,reset,wait:3,shot:network,launch:3,wait:9,shot:lock" --out ../docs/screenshots
//
// Plan steps: wait:<s> | reset | launch:<level>[:<size>] | key:<k> | click:<text> | shot:<name>
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { chromium } from "playwright";

const argv = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 ? argv[i + 1] : fallback;
};
const url = opt("url", "http://localhost:3000");
const out = resolve(opt("out", "shots"));
const plan = opt("plan", "wait:6,shot:network").split(",");
const width = Number(opt("width", 1920));
const height = Number(opt("height", 1080));
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist", "--enable-webgl"],
});
const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
page.on("pageerror", (err) => console.error("[pageerror]", err.message));
await page.goto(url, { waitUntil: "domcontentloaded" });

for (const step of plan) {
  const [kind, a, b] = step.split(":");
  if (kind === "wait") await page.waitForTimeout(Number(a) * 1000);
  else if (kind === "reset") await page.getByRole("button", { name: "Reset" }).click();
  else if (kind === "launch") {
    if (a) {
      await page.getByRole("button", { name: new RegExp(`^${a}\\s`) }).first().click();
    }
    if (b) await page.evaluate((size) => window.__mirageLaunchSize?.(Number(size)), b);
    await page.getByText("Launch swarm").click();
  } else if (kind === "key") await page.keyboard.press(a);
  else if (kind === "click") await page.getByText(a, { exact: false }).first().click();
  else if (kind === "wheel") {
    const [x, y, dy] = step.split(":").slice(1).map(Number);
    await page.mouse.move(x, y);
    await page.mouse.wheel(0, dy);
  }
  else if (kind === "shot") {
    const file = resolve(out, `${a}.png`);
    await page.screenshot({ path: file });
    console.log("saved", file);
  }
}
await browser.close();
