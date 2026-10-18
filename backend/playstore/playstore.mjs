// node playstore.mjs top <CATEGORY> [n] | search <term> | app <appId>   → JSON on stdout
import gplay from "google-play-scraper";

const strip = (s) => (s || "").replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]+>/g, "")
  .replace(/&amp;/g, "&").replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").trim();

const brief = (a) => ({
  appId: a.appId, title: a.title, developer: a.developer, icon: a.icon, score: a.score ?? null,
  installs: a.installs ?? a.maxInstalls ?? null, genre: a.genre ?? null, free: a.free ?? true,
  summary: [...strip(a.summary)].slice(0, 500).join(""),  // by code point: never split an emoji
});

const [cmd, arg, n] = process.argv.slice(2);
let out;
if (cmd === "top") {
  const list = await gplay.list({ collection: gplay.collection.TOP_FREE, category: gplay.category[arg] ?? arg, num: Number(n) || 24 });
  out = list.map(brief);
} else if (cmd === "search") {
  out = (await gplay.search({ term: arg, num: Number(n) || 24 })).map(brief);
} else if (cmd === "app") {
  const a = await gplay.app({ appId: arg });
  let reviews = [];
  try { reviews = (await gplay.reviews({ appId: arg, sort: gplay.sort.HELPFULNESS, num: 40 })).data; } catch {}
  out = {
    ...brief(a), description: strip(a.description), screenshots: a.screenshots, ratings: a.ratings, version: a.version,
    updated: a.updated, url: a.url,
    reviews: reviews.map((r) => ({ score: r.score, text: (r.text || "").slice(0, 600) })),
  };
} else {
  console.error("usage: playstore.mjs top <CATEGORY> [n] | search <term> [n] | app <appId>");
  process.exit(2);
}
process.stdout.write(JSON.stringify(out));
