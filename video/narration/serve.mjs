// Recording booth server: node narration/serve.mjs, then open http://localhost:4400/narration/booth.html
// Serves the project folder and saves each take. Saving mixes the voice over the music right away, then
// re-renders the video in the background with captions timed to how the take was actually spoken.
// Needs renders/<name>.mp4 first (node render.mjs --final --audio=audio/soundtrack.wav).
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { root, project, baseVideo, narratedVideo, parseArguments } from "../lib/project.mjs";
import { alignCaptions } from "./align.mjs";
import { splicePickup } from "./pickup.mjs";

const port = Number(parseArguments().port || 4400);
const takesDirectory = path.join(root, "narration", "takes");
const narrationPath = path.join(root, "narration", "narration.wav");
const cameraPath = path.join(root, "narration", "camera.mp4");
const narratedAudio = path.join(root, "audio", "soundtrack-narrated.wav");
const relative = (file) => path.relative(root, file);
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".jpg": "image/jpeg", ".png": "image/png", ".mp4": "video/mp4", ".wav": "audio/wav", ".m4a": "audio/mp4", ".webm": "audio/webm" };
fs.mkdirSync(takesDirectory, { recursive: true });

let job = { state: "idle", message: "" };

function run(command, list) {
  const result = spawnSync(command, list, { cwd: root, encoding: "utf8", maxBuffer: 1 << 28 });
  if (result.status !== 0) throw new Error(result.stderr || result.stdout);
  return result.stdout;
}

function renderWithCaptions() {
  job = { state: "rendering", message: "Re-rendering the video with captions timed to the voice. This takes a few minutes." };
  const temporary = narratedVideo.replace(".mp4", ".rendering.mp4");
  const child = spawn("node", ["render.mjs", "--final", `--audio=${relative(narratedAudio)}`, `--out=${relative(temporary)}`], { cwd: root, stdio: "ignore" });
  child.on("exit", (code) => {
    if (code === 0) {
      fs.renameSync(temporary, narratedVideo);
      job = { state: "done", message: `Done. Captions now follow the voice in ${relative(narratedVideo)}.` };
    } else {
      job = { state: "failed", message: "The captioned render failed; the narrated video without re-timed captions is still saved." };
    }
    console.log(job.message);
  });
}

function serveFile(request, response) {
  const filePath = path.join(root, decodeURIComponent(new URL(request.url, "http://localhost").pathname));
  if (!filePath.startsWith(root) || !fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    response.writeHead(404);
    response.end("Not found");
    return;
  }
  const size = fs.statSync(filePath).size;
  const range = request.headers.range?.match(/bytes=(\d*)-(\d*)/);
  const headers = { "Content-Type": types[path.extname(filePath)] || "application/octet-stream", "Accept-Ranges": "bytes", "Cache-Control": "no-store" };
  if (range) {
    const start = range[1] ? Number(range[1]) : 0;
    const end = range[2] ? Number(range[2]) : size - 1;
    response.writeHead(206, { ...headers, "Content-Range": `bytes ${start}-${end}/${size}`, "Content-Length": end - start + 1 });
    fs.createReadStream(filePath, { start, end }).pipe(response);
  } else {
    response.writeHead(200, { ...headers, "Content-Length": size });
    fs.createReadStream(filePath).pipe(response);
  }
}

function saveTake(request, response) {
  const url = new URL(request.url, "http://localhost");
  const leadSeconds = Number(url.searchParams.get("lead") || 0);
  // A pickup take carries the ids of the lines it covers and the video time the booth started playing from.
  const lines = (url.searchParams.get("line") || "").split(",").filter(Boolean);
  const playFrom = Number(url.searchParams.get("from") || 0);
  const contentType = request.headers["content-type"] || "";
  const hasVideo = contentType.startsWith("video/");
  const extension = contentType.includes("mp4") ? (hasVideo ? ".mp4" : ".m4a") : ".webm";
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const takePath = path.join(takesDirectory, `take-${stamp}${extension}`);
  const chunks = [];
  request.on("data", (chunk) => chunks.push(chunk));
  request.on("end", () => {
    try {
      if (job.state === "rendering") throw new Error("The previous take is still rendering. Wait for it to finish, then save again.");
      if (!fs.existsSync(baseVideo)) throw new Error(`${relative(baseVideo)} is missing. Render it first: node render.mjs --final --audio=audio/soundtrack.wav`);
      fs.writeFileSync(takePath, Buffer.concat(chunks));
      if (lines.length) {
        if (!fs.existsSync(narrationPath)) throw new Error("Record the whole script once before recording single lines.");
        for (const line of lines) {
          const splice = splicePickup({ takePath, leadSeconds, playFrom, line, hasVideo });
          console.log(`pickup "${line}" spliced at ${splice.from.toFixed(2)}–${splice.to.toFixed(2)} s, ${splice.gainDecibels} dB to match the full take`);
        }
        if (hasVideo && fs.existsSync(cameraPath)) run("node", ["stage/presenter.mjs"]);
      } else {
        // The recorder starts a moment before the video; trimming that lead puts the voice at video time 0.
        run("ffmpeg", ["-hide_banner", "-y", "-i", takePath, "-af", `atrim=start=${Math.max(0, leadSeconds)},asetpts=PTS-STARTPTS`, "-ar", "48000", "-ac", "1", narrationPath]);
        if (hasVideo) {
          // The camera footage, trimmed to line up with the video, for the corner window and the wide shots.
          run("ffmpeg", ["-hide_banner", "-y", "-ss", String(Math.max(0, leadSeconds)), "-i", takePath, "-c:v", "libx264", "-crf", "17", "-preset", "fast", "-r", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", cameraPath]);
          run("node", ["stage/presenter.mjs"]);
        }
      }
      run("node", ["audio/soundtrack.mjs", `--narration=${relative(narrationPath)}`, `--out=${relative(narratedAudio)}`]);
      run("ffmpeg", ["-hide_banner", "-y", "-i", baseVideo, "-i", narratedAudio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", narratedVideo]);
      const aligned = alignCaptions();
      renderWithCaptions();
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ take: relative(takePath), video: relative(narratedVideo), camera: hasVideo ? relative(cameraPath) : null, alignedLines: aligned }));
      console.log("saved", takePath, `(${aligned} lines aligned); captioned render started`);
    } catch (error) {
      response.writeHead(500, { "Content-Type": "text/plain" });
      response.end(String(error.message || error));
    }
  });
}

http
  .createServer((request, response) => {
    if (request.method === "POST" && request.url.startsWith("/save")) return saveTake(request, response);
    if (request.url.startsWith("/status")) {
      response.writeHead(200, { "Content-Type": "application/json" });
      return response.end(JSON.stringify(job));
    }
    if (request.url.startsWith("/project")) {
      response.writeHead(200, { "Content-Type": "application/json" });
      return response.end(JSON.stringify({ name: project.name, video: `../${relative(baseVideo)}`, narrated: relative(narratedVideo) }));
    }
    serveFile(request, response);
  })
  .listen(port, () => console.log(`Recording booth: http://localhost:${port}/narration/booth.html`));
