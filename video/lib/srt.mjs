// Writes exports/<name>-captions.srt for the upload. After a recorded take it follows the voice
// (stage/data/caption-timing.json, from the booth); before that it follows the guide voice's timing.
// node lib/srt.mjs
import { cues, readJson } from "./project.mjs";
import { writeSubtitles } from "../narration/align.mjs";

const recorded = readJson("stage/data/caption-timing.json", {});
const durations = readJson("stage/data/vo-durations.json", {});
const timing = Object.fromEntries(
  cues.map((cue) => [cue.id, recorded[cue.id] ?? { start: cue.at, end: cue.at + (durations[cue.id] ?? 3) }]),
);
writeSubtitles(timing);
console.log(`wrote captions for ${cues.length} lines (${Object.keys(recorded).length} timed to a recording)`);
