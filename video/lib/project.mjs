// Shared settings for every script: project.json, the cue list, and the video's length.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const project = JSON.parse(fs.readFileSync(path.join(root, "project.json"), "utf8"));
export const cues = JSON.parse(fs.readFileSync(path.join(root, "stage", "cues.json"), "utf8"));
export const cueAt = Object.fromEntries(cues.map((cue) => [cue.id, cue.at]));
// The stage computes the same length, so picture and sound always end together.
export const duration = project.duration ?? cues.at(-1).at + project.endAfterLastCue;
export const baseVideo = path.join(root, "renders", `${project.name}.mp4`);
export const narratedVideo = path.join(root, "renders", `${project.name}-narrated.mp4`);
export const subtitles = path.join(root, "exports", `${project.name}-captions.srt`);

export function readJson(relativePath, fallback) {
  const file = path.join(root, relativePath);
  return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : fallback;
}

export function parseArguments(list = process.argv.slice(2)) {
  return Object.fromEntries(list.map((argument) => {
    const [key, value = "true"] = argument.replace(/^--/, "").split("=");
    return [key, value];
  }));
}
