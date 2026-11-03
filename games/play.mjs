// Game tester: plays a game's web preview in a phone-sized headless browser and saves screenshots.
// usage: node play.mjs <url> <out-folder> [seconds]
// Installed with Playwright into ~/vibeapping/tools/game-tester by backend/vibe/games.py.
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

process.env.PLAYWRIGHT_BROWSERS_PATH = join(dirname(fileURLToPath(import.meta.url)), "browsers");
const { chromium } = await import("playwright");

const [url, out, seconds = "12"] = process.argv.slice(2);
if (!url || !out) {
  console.log("usage: node play.mjs <url> <out-folder> [seconds]");
  process.exit(2);
}
mkdirSync(out, { recursive: true });
const W = 390, H = 844;
// software WebGL: works without a GPU; frame rates here say nothing about the phone
const browser = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: W, height: H } });
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(e.message));
await page.goto(url, { waitUntil: "networkidle", timeout: 180000 });
await page.waitForTimeout(4000);
await page.screenshot({ path: join(out, "0-start.png") });

// press, then hold and weave left and right like a player steering; a screenshot every few seconds
const x = W / 2, y = H * 0.7, t0 = Date.now(), shots = 4;
await page.mouse.click(x, y);
await page.mouse.move(x, y);
await page.mouse.down();
for (let k = 1; k <= shots; k++) {
  while (Date.now() - t0 < (Number(seconds) * 1000 * k) / shots) {
    await page.mouse.move(x + Math.sin((Date.now() - t0) / 700) * W * 0.3, y);
    await page.waitForTimeout(80);
  }
  await page.screenshot({ path: join(out, `${k}-play.png`) });
}
await page.mouse.up();
await page.mouse.click(x, y); // taps for tap-to-play games and end screens
await page.waitForTimeout(1500);
await page.screenshot({ path: join(out, `${shots + 1}-after-tap.png`) });
await browser.close();
console.log(`screenshots in ${out}: 0-start.png, 1..${shots}-play.png, ${shots + 1}-after-tap.png`);
console.log(errors.length ? `browser errors:\n${errors.slice(0, 20).join("\n")}` : "no browser errors");
