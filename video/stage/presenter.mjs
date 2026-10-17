// Cuts the booth's camera footage (narration/camera.mp4) into frames for the stage: a head-and-shoulders square
// for the corner window that runs through the video, and wide shots that play beside a scene's type.
// Frame n of every sequence is stage time n / 30. The booth runs this after each saved take.
// project.json's presenter sets the crops (ffmpeg w:h:x:y on the 1920×1080 camera frame), an optional grade,
// and the wide shots: "wide": { "intro": ["intro-0.5", "purpose+1"] } spans cue times, plus or minus seconds.
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { root, project, cueAt } from "../lib/project.mjs";

const camera = path.join(root, "narration", "camera.mp4");
const footage = path.join(root, "stage", "footage");
const fps = 30;
const settings = { windowCrop: "960:960:480:20", wideCrop: "1260:1080:330:0", grade: "", wide: {}, ...project.presenter };
const chain = (...filters) => filters.filter(Boolean).join(",");

function run(command, list) {
  const result = spawnSync(command, list, { encoding: "utf8", maxBuffer: 1 << 28 });
  if (result.status !== 0) throw new Error(result.stderr || result.stdout);
  return result.stdout;
}

function extract(folder, filter, first, last) {
  const directory = path.join(footage, folder);
  fs.rmSync(directory, { recursive: true, force: true });
  fs.mkdirSync(directory, { recursive: true });
  run("ffmpeg", ["-v", "error", "-i", camera, "-vf", chain(`select='between(n,${first},${last})'`, filter), "-fps_mode", "passthrough", "-q:v", "3", "-start_number", String(first), path.join(directory, "%05d.jpg")]);
}

// "intro-0.5" is half a second before the intro cue; a bare number is a video time in seconds.
function videoTime(value) {
  if (typeof value === "number") return value;
  const [, id, shift] = value.match(/^(.+?)([+-]\d+(?:\.\d+)?)?$/);
  if (!(id in cueAt)) throw new Error(`presenter.wide refers to "${id}", which is not a cue id`);
  return cueAt[id] + Number(shift || 0);
}

const frames = Number(run("ffprobe", ["-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", camera]).trim());
const span = ([from, to]) => [Math.max(0, Math.floor(videoTime(from) * fps)), Math.min(frames - 1, Math.ceil(videoTime(to) * fps))];
const wide = Object.fromEntries(Object.entries(settings.wide).map(([name, range]) => [name, span(range)]));

extract("presenter-window", chain(`crop=${settings.windowCrop}`, "scale=480:480", settings.grade), 0, frames - 1);
fs.rmSync(path.join(footage, "presenter"), { recursive: true, force: true });
for (const [name, [first, last]] of Object.entries(wide)) extract(path.join("presenter", name), chain(`crop=${settings.wideCrop}`, settings.grade), first, last);
fs.writeFileSync(path.join(root, "stage", "data", "presenter.json"), JSON.stringify({ fps, frames, wide }, null, 1));
console.log(`presenter: ${frames} window frames, wide shots ${JSON.stringify(wide)}`);
