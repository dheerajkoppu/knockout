// Writes stage/cues.json, the lines every other script reads, from stage/script.json and the captured facts.
// node lib/cues.mjs
// A line with a "ready" variant uses it once its beat is real (stage/data/facts.json "status", which
// capture/facts.mjs works out and stage/status.json can force). {path.to.fact} is filled in from facts.json,
// and a fact that is missing stops the build instead of reaching the narration as a blank.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const script = JSON.parse(fs.readFileSync(path.join(root, "stage", "script.json"), "utf8"));
const facts = JSON.parse(fs.readFileSync(path.join(root, "stage", "data", "facts.json"), "utf8"));

function fill(text, id) {
  return text.replace(/\{([\w.]+)\}/g, (match, key) => {
    const value = key.split(".").reduce((node, part) => (node == null ? undefined : node[part]), facts);
    if (value === undefined || value === null || value === "") throw new Error(`${id}: no fact for {${key}}; capture it or keep this beat pending`);
    return typeof value === "number" ? value.toLocaleString("en-US") : String(value);
  });
}

// "ready" is one variant or a list; the first whose beat is real wins. A variant with "stop" means the
// captured state needs a person to rewrite the line, so the build halts with that message.
const cues = script.map((line) => {
  const variants = line.ready ? [line.ready].flat() : [];
  const chosen = variants.find((variant) => facts.status?.[variant.when]);
  if (chosen?.stop) throw new Error(`${line.id}: ${chosen.stop}`);
  const variant = chosen ?? line;
  return { id: line.id, at: variant.at ?? line.at, text: fill(variant.text, line.id), variant: chosen ? `ready:${chosen.when}` : variants.length ? "pending" : "only" };
});
fs.writeFileSync(path.join(root, "stage", "cues.json"), JSON.stringify(cues, null, 1) + "\n");
const pending = cues.filter((cue) => cue.variant === "pending").map((cue) => cue.id);
const swapped = cues.filter((cue) => cue.variant.startsWith("ready")).map((cue) => cue.id);
console.log(`wrote stage/cues.json (${cues.length} lines${pending.length ? `; pending wording for ${pending.join(", ")}` : ""}${swapped.length ? `; final wording for ${swapped.join(", ")}` : ""})`);
