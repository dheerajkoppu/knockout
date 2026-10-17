// Speaks every cue with macOS `say` as a guide track, so scenes can be timed before anyone records.
// node audio/guide-vo.mjs [--voice=Samantha] [--rate=175] [--force]
// Writes audio/vo/<id>.aiff, stage/data/vo-durations.json (how long each line takes to say), and audio/vo.wav
// (every line at its cue time). A recording dropped in at audio/vo/<id>.aiff is used as is and never replaced.
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { root, cues, duration, parseArguments } from "../lib/project.mjs";
import { writeFloatWav } from "./wav.mjs";

const args = parseArguments();
const SAMPLE_RATE = 48000;
const voDirectory = path.join(root, "audio", "vo");
const spokenPath = path.join(voDirectory, ".guide.json");
fs.mkdirSync(voDirectory, { recursive: true });
// What `say` was last asked for, per line. A file with no entry here is someone's own recording.
const spoken = fs.existsSync(spokenPath) ? JSON.parse(fs.readFileSync(spokenPath, "utf8")) : {};
const plain = (text) => text.replace(/[*|]/g, "").replace(/\s+/g, " ").trim();

function decodeMono(file) {
  const result = spawnSync("ffmpeg", ["-v", "error", "-i", file, "-ac", "1", "-ar", String(SAMPLE_RATE), "-f", "f32le", "-"], { maxBuffer: 1 << 30 });
  if (result.status !== 0) throw new Error(`could not decode ${file}:\n${result.stderr}`);
  const bytes = result.stdout;
  return new Float32Array(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.length));
}

const voice = new Float32Array(Math.round(duration * SAMPLE_RATE));
const durations = {};
const warnings = [];
let previous = null;
for (const cue of cues) {
  const file = path.join(voDirectory, `${cue.id}.aiff`);
  const request = `${args.voice || ""}|${args.rate || ""}|${plain(cue.text)}`;
  const generated = !fs.existsSync(file) || cue.id in spoken;
  if (generated && (args.force || spoken[cue.id] !== request || !fs.existsSync(file))) {
    const sayArguments = ["-o", file];
    if (args.voice) sayArguments.push("-v", args.voice);
    if (args.rate) sayArguments.push("-r", args.rate);
    const result = spawnSync("say", [...sayArguments, plain(cue.text)], { encoding: "utf8" });
    if (result.status !== 0) throw new Error(`say failed for ${cue.id}: ${result.stderr}`);
    spoken[cue.id] = request;
  }
  const samples = decodeMono(file);
  const length = samples.length / SAMPLE_RATE;
  durations[cue.id] = +length.toFixed(3);
  const offset = Math.round(cue.at * SAMPLE_RATE);
  const count = Math.max(0, Math.min(samples.length, voice.length - offset));
  for (let index = 0; index < count; index++) voice[offset + index] += samples[index];
  const end = cue.at + length;
  if (previous && cue.at < previous.end) warnings.push(`${previous.id} runs ${(previous.end - cue.at).toFixed(2)} s into ${cue.id}: start ${cue.id} at ${(previous.end + 0.4).toFixed(1)} or shorten ${previous.id}`);
  if (end > duration) warnings.push(`${cue.id} runs past the end of the video (${duration.toFixed(1)} s)`);
  console.log(`  ${cue.id.padEnd(14)} ${cue.at.toFixed(2).padStart(7)} – ${end.toFixed(2).padStart(7)} s  ${generated ? "" : "(recording)"}`);
  previous = { id: cue.id, end };
}
fs.writeFileSync(spokenPath, JSON.stringify(spoken, null, 1));
fs.writeFileSync(path.join(root, "stage", "data", "vo-durations.json"), JSON.stringify(durations, null, 2) + "\n");
writeFloatWav(path.join(root, "audio", "vo.wav"), [voice, voice], SAMPLE_RATE);
for (const warning of warnings) console.warn(`  warning: ${warning}`);
console.log(`wrote audio/vo.wav and stage/data/vo-durations.json (${cues.length} lines, ${duration.toFixed(1)} s video)`);
