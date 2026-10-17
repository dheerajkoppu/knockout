// Renders the synthesized music bed (audio/score.html, seeded Web Audio in headless Chromium, nothing to license)
// with its sections placed at the same cue times the stage uses.
// node audio/render-score.mjs [--variant=a|b|all]   writes audio/music-<variant>.wav
import { chromium } from "playwright";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { root, cueAt, duration, readJson, parseArguments } from "../lib/project.mjs";
import { writeFloatWav } from "./wav.mjs";

const args = parseArguments();
const durations = readJson("stage/data/vo-durations.json", {});
const endOf = (id) => cueAt[id] + (durations[id] ?? 3);
// The same moments stage.js builds its scenes on.
const settings = {
  duration: duration + 0.4,
  videoEnd: duration,
  tempo: 100,
  matchAt: cueAt["hook-4"] + 0.25,
  titleAt: endOf("hook-4") + 0.8,
  demoStart: cueAt["agents-1"] - 0.5,
  howStart: cueAt["bench-1"] - 0.5,
  breakdownStart: cueAt["signal-1"] - 0.5,
  liftStart: cueAt["watch-1"] - 0.5,
  close: cueAt.close + 0.05,
};
const variants = !args.variant || args.variant === "all" ? ["a", "b"] : [args.variant];

const CHUNK_FRAMES = 480000;
const browser = await chromium.launch();
const page = await browser.newPage();
page.on("pageerror", (error) => console.error(`[score] ${error.message}`));
await page.goto(pathToFileURL(path.join(root, "audio", "score.html")).href);
for (const variant of variants) {
  const started = Date.now();
  const rendered = await page.evaluate((trackSettings) => window.renderTrack("music", trackSettings), { ...settings, variant });
  const channels = [];
  for (let channel = 0; channel < rendered.channelCount; channel++) {
    const samples = new Float32Array(rendered.length);
    for (let start = 0; start < rendered.length; start += CHUNK_FRAMES) {
      const length = Math.min(CHUNK_FRAMES, rendered.length - start);
      const encoded = await page.evaluate(([channelIndex, from, count]) => window.readSamples(channelIndex, from, count), [channel, start, length]);
      new Uint8Array(samples.buffer, start * 4, length * 4).set(Buffer.from(encoded, "base64"));
    }
    channels.push(samples);
  }
  const file = path.join(root, "audio", `music-${variant}.wav`);
  writeFloatWav(file, channels, rendered.sampleRate);
  console.log(`music-${variant}.wav  ${(rendered.length / rendered.sampleRate).toFixed(2)} s  peak ${rendered.peakDecibels.toFixed(1)} dBFS  ${((Date.now() - started) / 1000).toFixed(0)} s`);
}
await browser.close();
