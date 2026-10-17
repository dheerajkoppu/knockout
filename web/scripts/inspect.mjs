// Screenshots of single elements, for checking details: node scripts/inspect.mjs <url> <selector> <width> <file> [dark]
import { chromium } from "playwright";

const [url, selector, width, file, theme] = process.argv.slice(2);
const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: Number(width), height: 900 },
  deviceScaleFactor: 2,
  colorScheme: theme === "dark" ? "dark" : "light",
});
const page = await context.newPage();
await page.goto(url, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);
await page.locator(selector).first().screenshot({ path: file });
await browser.close();
