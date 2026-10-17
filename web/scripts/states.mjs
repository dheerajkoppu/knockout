// Screenshots of the loading and API-unreachable states, made by holding or failing the report request.
// Usage: node scripts/states.mjs [baseUrl]
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const baseUrl = process.argv[2] || "http://localhost:3000";
const outputDirectory = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "screenshots");
const browser = await chromium.launch();

for (const width of [1440, 390]) {
  const context = await browser.newContext({ viewport: { width, height: width > 500 ? 900 : 844 }, deviceScaleFactor: 2 });
  const page = await context.newPage();
  await page.route("**/api/drugs/*/report*", () => {});
  await page.goto(`${baseUrl}/drug/eculizumab`);
  await page.waitForSelector('[aria-busy="true"]');
  await page.waitForTimeout(2200);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: path.join(outputDirectory, `state-loading-${width}.png`) });
  await page.unroute("**/api/drugs/*/report*");

  await page.route("**/api/**", (route) => route.abort("connectionrefused"));
  await page.goto(`${baseUrl}/drug/eculizumab`);
  await page.waitForSelector('[role="alert"]');
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: path.join(outputDirectory, `state-offline-${width}.png`) });
  await context.close();
}
await browser.close();
console.log("done");
