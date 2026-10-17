// Finds when each script line was actually spoken, so captions appear with the voice rather than the script.
// The booth runs this after each saved take; node narration/align.mjs re-times the saved take on its own.
// Writes stage/data/caption-timing.json for the stage and exports/<name>-captions.srt for upload.
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { root, cues, subtitles } from "../lib/project.mjs";

const narrationPath = path.join(root, "narration", "narration.wav");

export function alignCaptions() {
  const decoded = spawnSync("ffmpeg", ["-v", "error", "-i", narrationPath, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], { maxBuffer: 1 << 28 });
  const samples = new Float32Array(decoded.stdout.buffer, decoded.stdout.byteOffset, decoded.stdout.length / 4);
  // 20 ms frames, so 50 per second.
  const frameSize = 320;
  const levels = [];
  for (let start = 0; start + frameSize <= samples.length; start += frameSize) {
    let sum = 0;
    for (let index = start; index < start + frameSize; index++) sum += samples[index] * samples[index];
    levels.push(10 * Math.log10(sum / frameSize + 1e-12));
  }
  const sorted = [...levels].sort((first, second) => first - second);
  // Breaths and trailing word endings sit about 30 dB under a speaking voice; they shouldn't start a line.
  const threshold = Math.max(sorted[Math.floor(sorted.length * 0.1)] + 12, sorted[Math.floor(sorted.length * 0.9)] - 30);
  const speaking = levels.map((level) => level > threshold);
  // Bridge short pauses between words and ignore clicks shorter than 120 ms.
  for (let index = 0; index < speaking.length; index++) {
    if (!speaking[index]) continue;
    let gap = index + 1;
    while (gap < speaking.length && !speaking[gap]) gap++;
    if (gap < speaking.length && gap - index <= 13) for (let fill = index; fill < gap; fill++) speaking[fill] = true;
  }
  for (let index = 0; index < speaking.length; ) {
    if (!speaking[index]) { index++; continue; }
    let end = index;
    while (end < speaking.length && speaking[end]) end++;
    if (end - index < 6) for (let clear = index; clear < end; clear++) speaking[clear] = false;
    index = end;
  }
  const timing = {};
  let previousEndFrame = 0;
  cues.forEach((cue, cueIndex) => {
    const windowStart = Math.max(previousEndFrame, Math.floor((cue.at - 1.2) * 50));
    const windowEnd = cueIndex + 1 < cues.length ? cues[cueIndex + 1].at - 0.3 : cue.at + 12;
    let first = -1, last = -1;
    for (let frame = windowStart; frame < Math.min(speaking.length, Math.ceil(windowEnd * 50)); frame++) {
      if (speaking[frame]) { if (first < 0) first = frame; last = frame; }
    }
    // A line still being finished at the next cue ends with its phrase, not at the cue.
    while (last >= 0 && last + 1 < speaking.length && speaking[last + 1]) last++;
    if (first >= 0 && last - first > 15) {
      timing[cue.id] = { start: +(first / 50).toFixed(2), end: +((last + 1) / 50).toFixed(2) };
      previousEndFrame = last + 1;
    }
  });
  fs.writeFileSync(path.join(root, "stage", "data", "caption-timing.json"), JSON.stringify(timing, null, 1));
  writeSubtitles(timing);
  return Object.keys(timing).length;
}

export function writeSubtitles(timing) {
  const stamp = (seconds) => {
    const whole = Math.floor(seconds);
    const milliseconds = Math.round((seconds - whole) * 1000);
    return `${String(Math.floor(whole / 3600)).padStart(2, "0")}:${String(Math.floor((whole % 3600) / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")},${String(milliseconds).padStart(3, "0")}`;
  };
  const entries = [];
  for (const cue of cues) {
    const span = timing[cue.id];
    if (!span) continue;
    const parts = cue.text.split("|").map((part) => part.replace(/\*/g, "").trim());
    const total = parts.reduce((sum, part) => sum + part.length, 0);
    let at = span.start;
    for (const part of parts) {
      const end = at + ((span.end - span.start) * part.length) / total;
      entries.push(`${entries.length + 1}\n${stamp(at)} --> ${stamp(end + 0.2)}\n${part}\n`);
      at = end;
    }
  }
  fs.mkdirSync(path.dirname(subtitles), { recursive: true });
  fs.writeFileSync(subtitles, entries.join("\n"));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) console.log(`${alignCaptions()} of ${cues.length} lines aligned`);
