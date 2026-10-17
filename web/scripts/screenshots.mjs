// Full-page screenshots of the home page and one report at desktop and phone widths.
// Usage: node scripts/screenshots.mjs [baseUrl]   (reads the live API when it answers, else the fixture)
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const baseUrl = process.argv[2] || process.env.WEB_URL || "http://localhost:3000";
const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const outputDirectory = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "screenshots");
const themes = (process.env.THEMES || "light").split(",");

async function apiIsLive() {
  try {
    const response = await fetch(`${apiUrl}/api/health`, { signal: AbortSignal.timeout(3000) });
    return response.ok;
  } catch {
    return false;
  }
}

const live = await apiIsLive();
console.log(`API ${live ? "live: the report is shot from the API and from the fixture" : "not reachable: the report is shot from the fixture"}`);

const pages = [
  { name: "home", path: "/" },
  ...(live ? [{ name: "eculizumab", path: "/drug/eculizumab" }] : []),
  { name: "eculizumab-fixture", path: "/drug/eculizumab?fixture=1" },
];
const widths = [
  { label: "1440", width: 1440, height: 900 },
  { label: "390", width: 390, height: 844 },
];

await mkdir(outputDirectory, { recursive: true });
const browser = await chromium.launch();
for (const theme of themes) {
  for (const viewport of widths) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      deviceScaleFactor: 2,
      colorScheme: theme === "dark" ? "dark" : "light",
    });
    const page = await context.newPage();
    for (const target of pages) {
      await page.goto(`${baseUrl}${target.path}`, { waitUntil: "networkidle" });
      await page.waitForSelector("main h1", { timeout: 180000 });
      await page.waitForFunction(() => !document.querySelector('[aria-busy="true"]'), null, { timeout: 180000 });
      await page.evaluate(() => document.fonts.ready);
      const suffix = theme === "light" ? "" : `-${theme}`;
      const file = path.join(outputDirectory, `${target.name}-${viewport.label}${suffix}.png`);
      await page.screenshot({ path: file, fullPage: true });
      console.log(file);
    }
    await context.close();
  }
}
await browser.close();
