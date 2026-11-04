// Side by side: a play-test screenshot next to a store screenshot of the original, in one image the agent can look at.
// usage: node compare.mjs <ours.png> <original.png> <out.png>
// Installed next to play.mjs in ~/vibeapping/tools/game-tester by backend/vibe/games.py.
import { readFileSync } from "node:fs";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

process.env.PLAYWRIGHT_BROWSERS_PATH = join(dirname(fileURLToPath(import.meta.url)), "browsers");
const { chromium } = await import("playwright");

const [ours, original, out] = process.argv.slice(2);
if (!ours || !original || !out) {
  console.log("usage: node compare.mjs <ours.png> <original.png> <out.png>");
  process.exit(2);
}
const TYPES = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp" };
const data = (file) => `data:${TYPES[extname(file).toLowerCase()] ?? "image/png"};base64,${readFileSync(file).toString("base64")}`;
const H = 900; // both pictures scaled to this height
const panel = (title, src) =>
  `<figure><figcaption>${title}</figcaption><img src="${src}"></figure>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: H + 60 } });
await page.setContent(`<html><body>
<style>
  body { margin: 0; background: #222; display: flex; gap: 16px; padding: 12px; width: max-content; font: 600 20px sans-serif; color: #fff; }
  figure { margin: 0; } figcaption { margin-bottom: 8px; } img { height: ${H}px; display: block; }
</style>
${panel("Your game", data(ours))}${panel("The original (store screenshot)", data(original))}
</body></html>`);
await page.waitForFunction(() => [...document.images].every((i) => i.complete));
await page.locator("body").screenshot({ path: out });
await browser.close();
console.log(`saved ${out}`);
