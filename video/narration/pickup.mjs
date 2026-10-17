// Splices a one-line pickup take into the saved narration and camera footage, so a new or fixed line can be
// recorded without redoing the whole video. The window runs from 0.35 s before the line's cue to 0.35 s before
// the next cue, or 3.2 s past the last line's cue; everything outside it stays from the full take.
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { root, cues } from "../lib/project.mjs";

const SAMPLE_RATE = 48000;
const FPS = 30;
const CROSSFADE = 0.08;
const DISSOLVE = 0.25;

function run(command, list, input) {
  const result = spawnSync(command, list, { input, maxBuffer: 1 << 30 });
  if (result.status !== 0) throw new Error(String(result.stderr || result.stdout));
  return result.stdout;
}

function decode(file) {
  const bytes = run("ffmpeg", ["-v", "error", "-i", file, "-ac", "1", "-ar", String(SAMPLE_RATE), "-f", "f32le", "-"]);
  return new Float32Array(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.length));
}

// Loudness of the voice itself: the mean power of the loudest fifth of 20 ms frames, so pauses don't count.
function speechLevel(samples) {
  const frame = SAMPLE_RATE / 50;
  const powers = [];
  for (let start = 0; start + frame <= samples.length; start += frame) {
    let sum = 0;
    for (let index = start; index < start + frame; index++) sum += samples[index] * samples[index];
    powers.push(sum / frame);
  }
  powers.sort((first, second) => second - first);
  const loudest = powers.slice(0, Math.max(1, Math.floor(powers.length / 5)));
  return loudest.reduce((sum, power) => sum + power, 0) / loudest.length;
}

export function pickupWindow(line) {
  const index = cues.findIndex((cue) => cue.id === line);
  if (index < 0) throw new Error(`No line "${line}" in the script.`);
  const snap = (seconds) => Math.round(seconds * FPS) / FPS;
  const end = index + 1 < cues.length ? cues[index + 1].at - 0.35 : cues[index].at + 3.2;
  return { from: snap(cues[index].at - 0.35), to: snap(end) };
}

export function splicePickup({
  takePath,
  leadSeconds,
  playFrom,
  line,
  hasVideo,
  narrationPath = path.join(root, "narration", "narration.wav"),
  cameraPath = path.join(root, "narration", "camera.mp4"),
}) {
  const { from, to } = pickupWindow(line);
  const takeTime = (videoTime) => leadSeconds + videoTime - playFrom;
  if (takeTime(from - DISSOLVE) < 0) throw new Error("The pickup started too late; record again from the countdown.");

  const narration = decode(narrationPath);
  const take = decode(takePath);
  const first = Math.round(from * SAMPLE_RATE);
  const last = Math.round(to * SAMPLE_RATE);
  const offset = Math.round(takeTime(0) * SAMPLE_RATE);
  if (last + offset > take.length) throw new Error("The pickup stopped before the end of the line; record again.");
  const pickup = take.subarray(first + offset, last + offset);
  const gain = Math.min(4, Math.max(0.25, Math.sqrt(speechLevel(narration) / speechLevel(pickup))));
  const fade = Math.round(CROSSFADE * SAMPLE_RATE);
  const spliced = new Float32Array(Math.max(narration.length, last));
  spliced.set(narration);
  for (let index = first; index < last; index++) {
    const position = index - first;
    const blend = Math.min(1, position / fade, (last - index) / fade);
    spliced[index] = (index < narration.length ? narration[index] : 0) * (1 - blend) + pickup[position] * gain * blend;
  }
  run("ffmpeg", ["-v", "error", "-y", "-f", "f32le", "-ar", String(SAMPLE_RATE), "-ac", "1", "-i", "-", "-c:a", "pcm_s16le", narrationPath], Buffer.from(spliced.buffer));

  if (hasVideo && fs.existsSync(cameraPath)) {
    const [width, height] = String(run("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", cameraPath])).trim().split(",");
    const length = to - from + 2 * DISSOLVE;
    const temporary = cameraPath.replace(".mp4", ".splicing.mp4");
    // The pickup dissolves in and out over the full take, which hides a small change in how the presenter sits.
    run("ffmpeg", [
      "-v", "error", "-y", "-i", cameraPath, "-ss", takeTime(from - DISSOLVE).toFixed(3), "-t", length.toFixed(3), "-i", takePath,
      "-filter_complex",
      `[1:v]fps=${FPS},scale=${width}:${height}:force_original_aspect_ratio=increase,crop=${width}:${height},format=yuva420p,` +
        `fade=t=in:st=0:d=${DISSOLVE}:alpha=1,fade=t=out:st=${(length - DISSOLVE).toFixed(3)}:d=${DISSOLVE}:alpha=1,` +
        `setpts=PTS-STARTPTS+${(from - DISSOLVE).toFixed(3)}/TB[pickup];[0:v][pickup]overlay=eof_action=pass,format=yuv420p[video]`,
      "-map", "[video]", "-map", "0:a", "-c:v", "libx264", "-crf", "17", "-preset", "fast", "-r", String(FPS), "-c:a", "copy", temporary,
    ]);
    fs.renameSync(temporary, cameraPath);
  }
  return { from, to, gainDecibels: +(20 * Math.log10(gain)).toFixed(1) };
}
