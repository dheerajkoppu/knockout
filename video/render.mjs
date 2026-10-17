// Renders stage/stage.html frame by frame in headless Chromium, then encodes with ffmpeg.
// node render.mjs --serve                      live preview at http://localhost:4401/stage/stage.html?play
// node render.mjs --stills=1,5.5,12            stills into renders/stills
// node render.mjs [--from=0 --to=20] [--audio=audio/soundtrack.wav]      1080p30 draft into renders/draft.mp4
// node render.mjs --final [--audio=...]        project.json's render settings into renders/<name>.mp4
// node render.mjs --sfx                        writes audio/sfx.json from the stage's effect times
// Other flags: --fps --scale --workers --crf --preset --out --query=nocaptions --dir --keepFrames
import { chromium } from "playwright";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { root, project, parseArguments } from "./lib/project.mjs";

const args = parseArguments();
const final = args.final ? project.render : {};
const fps = Number(args.fps || final.fps || 30);
const scale = Number(args.scale || final.scale || 1);
const workers = Number(args.workers || final.workers || 4);
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".jpg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml", ".mp4": "video/mp4", ".wav": "audio/wav" };

const server = http.createServer((request, response) => {
  const file = path.join(root, decodeURIComponent(new URL(request.url, "http://x").pathname));
  if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    response.writeHead(404);
    response.end();
    return;
  }
  response.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream", "Cache-Control": args.serve ? "no-store" : "max-age=3600" });
  fs.createReadStream(file).pipe(response);
});
await new Promise((resolve) => server.listen(args.serve ? Number(args.port || 4401) : 0, resolve));
const url = `http://127.0.0.1:${server.address().port}/stage/stage.html${args.query ? "?" + args.query : ""}`;

if (args.serve) {
  console.log(`preview: ${url}?play   (add &t=12.5 to start there, or use ?t=12.5 to hold one frame)`);
  await new Promise(() => {});
}

const browser = await chromium.launch({ args: ["--font-render-hinting=none", "--disable-gpu-vsync"] });
async function openPage() {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: scale });
  page.on("pageerror", (error) => console.error("page error:", error.message));
  await page.goto(url);
  await page.evaluate(() => window.ready);
  await page.evaluate(() => document.fonts.ready);
  return page;
}

if (args.sfx) {
  // The stage records when each effect belongs (window.SFX), so the sound follows the picture's own cue math.
  const page = await openPage();
  const effects = await page.evaluate(() => window.SFX);
  const rounded = Object.fromEntries(Object.entries(effects).map(([kind, times]) => [kind, times.map((time) => (Array.isArray(time) ? time.map((value) => +value.toFixed(3)) : +time.toFixed(3))).sort((first, second) => (Array.isArray(first) ? first[0] - second[0] : first - second))]));
  fs.writeFileSync(path.join(root, "audio", "sfx.json"), JSON.stringify(rounded, null, 1) + "\n");
  console.log("wrote audio/sfx.json:", Object.entries(rounded).map(([kind, times]) => `${times.length} ${kind}`).join(", "));
} else if (args.stills) {
  const page = await openPage();
  const directory = path.join(root, args.dir || "renders/stills");
  fs.mkdirSync(directory, { recursive: true });
  for (const time of args.stills.split(",").map(Number)) {
    await page.evaluate((t) => window.renderAt(t), time);
    await page.screenshot({ path: path.join(directory, `t${time.toFixed(2).padStart(6, "0")}.jpg`), type: "jpeg", quality: 88 });
  }
  console.log("stills in", directory);
} else {
  const page0 = await openPage();
  const duration = await page0.evaluate(() => window.DURATION);
  await page0.close();
  const out = path.join(root, args.out || (args.final ? `renders/${project.name}.mp4` : "renders/draft.mp4"));
  const from = Number(args.from || 0);
  const to = Math.min(Number(args.to || duration), duration);
  const first = Math.round(from * fps);
  const last = Math.round(to * fps);
  const frameDirectory = path.join(root, "frames", path.basename(out, ".mp4"));
  fs.rmSync(frameDirectory, { recursive: true, force: true });
  fs.mkdirSync(frameDirectory, { recursive: true });
  let next = first;
  let done = 0;
  const started = Date.now();
  await Promise.all(Array.from({ length: workers }, async () => {
    const page = await openPage();
    while (next < last) {
      const frame = next++;
      await page.evaluate((t) => window.renderAt(t), frame / fps);
      await page.screenshot({ path: path.join(frameDirectory, `${String(frame - first).padStart(6, "0")}.jpg`), type: "jpeg", quality: 93 });
      if (++done % (fps * 5) === 0) process.stdout.write(`\r${done}/${last - first} frames, ${((Date.now() - started) / done).toFixed(0)} ms/frame`);
    }
    await page.close();
  }));
  console.log(`\nrendered ${done} frames in ${((Date.now() - started) / 1000).toFixed(0)} s`);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  const ffmpegArgs = ["-y", "-v", "error", "-framerate", String(fps), "-i", path.join(frameDirectory, "%06d.jpg")];
  if (args.audio) ffmpegArgs.push("-ss", String(from), "-i", path.join(root, args.audio));
  ffmpegArgs.push("-c:v", "libx264", "-preset", args.preset || final.preset || "medium", "-crf", String(args.crf || final.crf || 16), "-pix_fmt", "yuv420p", "-movflags", "+faststart");
  // The picture sets the length: a soundtrack that ran short would otherwise cut frames off the end.
  if (args.audio) ffmpegArgs.push("-c:a", "aac", "-b:a", "256k", "-af", "apad", "-t", ((last - first) / fps).toFixed(6));
  ffmpegArgs.push(out);
  await new Promise((resolve, reject) => spawn("ffmpeg", ffmpegArgs, { stdio: "inherit" }).on("exit", (code) => (code ? reject(new Error(`ffmpeg ${code}`)) : resolve())));
  // A final cut leaves gigabytes of frames behind, and they are only needed for the encode.
  if (!args.keepFrames) fs.rmSync(frameDirectory, { recursive: true, force: true });
  console.log("wrote", out);
}
await browser.close();
server.close();
