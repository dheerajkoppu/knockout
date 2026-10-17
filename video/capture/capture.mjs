// Captures the running report page for the video: the home page with a drug typed into its search, and
// full-page screenshots of each report with the page position of every element a scene points at.
// node capture/capture.mjs [--web=http://127.0.0.1:3300] [--api=http://127.0.0.1:8800] [--only=home,eculizumab]
// The web build calls the API it was built with (NEXT_PUBLIC_API_URL, http://localhost:8000 by default);
// with --api set to another address, those calls are forwarded there, so a capture never needs port 8000.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { root, parseArguments } from "../lib/project.mjs";

const args = parseArguments();
const webUrl = (args.web || "http://127.0.0.1:3300").replace(/\/$/, "");
const apiUrl = (args.api || "http://127.0.0.1:8800").replace(/\/$/, "");
const builtApiUrl = (args.builtApi || "http://localhost:8000").replace(/\/$/, "");
const only = args.only ? new Set(args.only.split(",")) : null;
const raw = path.join(root, "capture", "raw");
fs.mkdirSync(raw, { recursive: true });

const VIEWPORT = { width: 1440, height: 900 };
const SCALE = 2;

// Everything a scene can point at, by name. Each entry lists every match with its page rectangle.
const TARGETS = {
  header: ".running-header",
  masthead: "header.masthead",
  title: ".masthead-title",
  deck: ".masthead-deck",
  meta: ".masthead-meta",
  fixtureBand: ".fixture-band",
  fixtureTag: ".fixture-tag",
  problems: "section.problems",
  chainSection: "section[aria-labelledby=chain-title]",
  chain: ".chain",
  chainNodes: ".chain .node",
  effectsSection: "section[aria-labelledby=effects-title]",
  ledger: ".ledger",
  entries: ".entry",
  unchecked: ".unchecked",
  labelQuote: ".label-quote",
  terms: ".terms",
  statistic: ".statistic",
  criteria: ".criteria",
  twoByTwo: ".two-by-two",
  monitoringSection: "section[aria-labelledby=monitoring-title]",
  monitorRun: ".monitor-run",
  trend: ".trend",
  alerts: ".alerts",
  notUsedSection: "section[aria-labelledby=not-used-title]",
  caveats: "#caveats",
  footer: "footer",
};

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: SCALE, colorScheme: "light", reducedMotion: "reduce" });
const apiCalls = [];
if (apiUrl !== builtApiUrl) {
  await context.route(`${builtApiUrl}/**`, async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "GET,POST,OPTIONS" } });
    }
    const forwarded = request.url().replace(builtApiUrl, apiUrl);
    const response = await route.fetch({ url: forwarded, timeout: 600000 });
    apiCalls.push(`${request.method()} ${forwarded} -> ${response.status()}`);
    await route.fulfill({ response, headers: { ...response.headers(), "access-control-allow-origin": "*" } });
  });
}
const page = await context.newPage();
page.on("pageerror", (error) => console.error("page error:", error.message));

async function settle() {
  await page.waitForSelector("main h1", { timeout: 600000 });
  await page.waitForFunction(() => !document.querySelector('[aria-busy="true"]'), null, { timeout: 600000 });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
}

async function rects() {
  return page.evaluate((targets) => {
    const found = {};
    for (const [name, selector] of Object.entries(targets)) {
      found[name] = [...document.querySelectorAll(selector)].map((element) => {
        const box = element.getBoundingClientRect();
        return {
          x: Math.round(box.left + scrollX),
          y: Math.round(box.top + scrollY),
          w: Math.round(box.width),
          h: Math.round(box.height),
          id: element.id || undefined,
          text: element.innerText.replace(/\s+/g, " ").trim().slice(0, 240),
        };
      });
    }
    return found;
  }, TARGETS);
}

async function shoot(file, options = {}) {
  await page.screenshot({ path: path.join(raw, file), type: "jpeg", quality: 92, ...options });
  return file;
}

const capturedAt = new Date().toISOString();
const manifest = fs.existsSync(path.join(raw, "pages.json")) ? JSON.parse(fs.readFileSync(path.join(raw, "pages.json"), "utf8")) : {};

/* The home page, then the drug typed into the search one key at a time, then Predict. */
if (!only || only.has("home")) {
  await page.goto(`${webUrl}/`, { waitUntil: "networkidle" });
  await settle();
  const frames = [await shoot("home-00.jpg")];
  const input = page.locator("#drug");
  await input.click();
  const drug = "eculizumab";
  for (let index = 0; index < drug.length; index++) {
    await page.keyboard.type(drug[index]);
    frames.push(await shoot(`home-${String(index + 1).padStart(2, "0")}.jpg`));
  }
  const homeRects = await rects();
  const search = await page.evaluate(() => {
    const box = document.querySelector(".search").getBoundingClientRect();
    const button = document.querySelector(".search-submit").getBoundingClientRect();
    return { search: { x: box.left, y: box.top, w: box.width, h: box.height }, button: { x: button.left, y: button.top, w: button.width, h: button.height } };
  });
  await Promise.all([page.waitForURL(/\/drug\/eculizumab/), page.locator(".search-submit").click()]);
  await settle();
  frames.push(await shoot("home-report.jpg"));
  manifest.home = { url: `${webUrl}/`, capturedAt, viewport: VIEWPORT, scale: SCALE, frames, rects: homeRects, ...search };
  console.log("home", frames.length, "frames");
}

/* Full reports, live and the labelled development fixture. */
const reports = [
  { name: "eculizumab", path: "/drug/eculizumab" },
  { name: "eculizumab-fixture", path: "/drug/eculizumab?fixture=1" },
  { name: "ibrutinib", path: "/drug/ibrutinib" },
];
for (const report of reports) {
  if (only && !only.has(report.name)) continue;
  await page.goto(`${webUrl}${report.path}`, { waitUntil: "networkidle" });
  await settle();
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  const file = await shoot(`${report.name}-full.jpg`, { fullPage: true });
  const sourceState = await page.evaluate(() => document.querySelector(".source-state")?.textContent?.trim() ?? null);
  manifest[report.name] = { url: `${webUrl}${report.path}`, capturedAt, viewport: VIEWPORT, scale: SCALE, height, file, sourceState, rects: await rects() };
  console.log(report.name, `${VIEWPORT.width}x${height}`, sourceState);
}

/* The API's own answers, so every number a scene shows is read from them. */
async function readApi(route) {
  const response = await fetch(`${apiUrl}${route}`, { signal: AbortSignal.timeout(600000) });
  return response.ok ? response.json() : { error: response.status };
}
manifest.api = {
  capturedAt,
  url: apiUrl,
  health: await readApi("/api/health"),
  eculizumab: await readApi("/api/drugs/eculizumab/report"),
  trend: await readApi("/api/drugs/eculizumab/trend"),
  alerts: await readApi("/api/drugs/eculizumab/alerts"),
  ibrutinib: await readApi("/api/drugs/ibrutinib/report"),
};
manifest.apiCalls = apiCalls;
fs.writeFileSync(path.join(raw, "pages.json"), JSON.stringify(manifest, null, 1));
console.log("wrote capture/raw/pages.json");
await browser.close();
