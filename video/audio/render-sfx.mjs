// Renders the synthesized sound effects (Web Audio in headless Chromium, seeded, so nothing to license) to sfx.wav.
// node audio/render-sfx.mjs
// Taps come from the footage; everything else is the times listed in audio/sfx.json. Re-run after re-cutting.
import { chromium } from "playwright";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { root, duration, readJson } from "../lib/project.mjs";
import { writeFloatWav } from "./wav.mjs";

const shots = readJson("stage/data/shots.json", []);
const events = readJson("stage/data/events.json", {});

// Same mapping the stage uses to place touch indicators.
function tapTimes() {
  const times = [];
  for (const shot of shots) {
    for (const event of events[shot.scene]?.events ?? []) {
      if (event.kind !== "tap") continue;
      const stageTime = shot.start + (event.t - shot.in) / shot.rate;
      if (stageTime < shot.start + 0.05 || stageTime > shot.end - 0.1) continue;
      times.push(stageTime);
    }
  }
  return times.sort((first, second) => first - second);
}

const settings = {
  whooshes: [],
  pops: [],
  chimes: [],
  risers: [],
  keys: [],
  ...readJson("audio/sfx.json", {}),
  duration: duration + 0.4,
  taps: [...tapTimes(), ...(readJson("audio/sfx.json", {}).taps ?? [])].sort((first, second) => first - second),
};

const CHUNK_FRAMES = 480000;
const browser = await chromium.launch();
const page = await browser.newPage();
page.on("console", (message) => console.log(`[sfx] ${message.text()}`));
page.on("pageerror", (error) => console.error(`[sfx] ${error.message}`));
await page.goto(pathToFileURL(path.join(root, "audio", "sfx.html")).href);

const rendered = await page.evaluate((trackSettings) => window.renderTrack(trackSettings), settings);
const channels = [];
for (let channel = 0; channel < rendered.channelCount; channel++) {
  const samples = new Float32Array(rendered.length);
  for (let start = 0; start < rendered.length; start += CHUNK_FRAMES) {
    const length = Math.min(CHUNK_FRAMES, rendered.length - start);
    const encoded = await page.evaluate(
      ([channelIndex, from, count]) => window.readSamples(channelIndex, from, count),
      [channel, start, length],
    );
    new Uint8Array(samples.buffer, start * 4, length * 4).set(Buffer.from(encoded, "base64"));
  }
  channels.push(samples);
}
writeFloatWav(path.join(root, "audio", "sfx.wav"), channels, rendered.sampleRate);
console.log(
  `sfx.wav  ${(rendered.length / rendered.sampleRate).toFixed(3)} s  peak ${rendered.peakDecibels.toFixed(1)} dBFS  ` +
    `${settings.taps.length} taps, ${settings.keys.length} keys, ${settings.whooshes.length} whooshes, ${settings.pops.length} pops, ${settings.chimes.length} chimes, ${settings.risers.length} risers`,
);
await browser.close();
