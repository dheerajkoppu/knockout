// Builds the soundtrack: an optional music bed, the synthesized sound effects, and optional narration.
// node audio/soundtrack.mjs [--music=audio/tracks/track.mp3 --drop=15.25 --align=13.6] [--narration=narration/narration.wav]
//                           [--loudness=-24] [--raw] [--out=audio/soundtrack.wav]
// --drop is where the track's beat comes in and --align is the video moment it should land on, usually the
// title reveal. Both default to project.json's music settings. A drop earlier than --align delays the music.
// --narration must already start at video time 0 (the recording booth and guide-vo.mjs save it that way).
// --raw skips the microphone clean-up, for a guide voice that needs none.
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { root, project, duration, parseArguments } from "../lib/project.mjs";

const args = parseArguments();
const audioDirectory = path.join(root, "audio");
const musicFile = args.music ?? project.music?.file;
const music = musicFile ? path.resolve(root, musicFile) : null;
const offset = Number(args.drop ?? project.music?.drop ?? 0) - Number(args.align ?? project.music?.alignTo ?? 0);
const narration = args.narration ? path.resolve(root, args.narration) : null;
const effects = path.join(audioDirectory, "sfx.wav");
const output = path.resolve(root, args.out || "audio/soundtrack.wav");
// The soundtrack runs a little past the picture so the encode never ends on a cut-off tail.
const DURATION = duration + 0.4;
// A bed sits well under a voice at about -24 LUFS; without narration the music plays a little fuller.
const MUSIC_LOUDNESS = Number(args.loudness ?? (narration ? -24 : -18));
const VOICE_LOUDNESS = -15;
const EFFECTS_GAIN = narration ? 0.7 : 1.0;

function ffmpeg(list) {
  const result = spawnSync("ffmpeg", ["-hide_banner", "-nostdin", "-y", ...list], { encoding: "utf8", maxBuffer: 1 << 26 });
  if (result.status !== 0) throw new Error(result.stderr);
  return result.stderr;
}

function loudnessFilter(file, target) {
  const log = ffmpeg(["-i", file, "-af", `loudnorm=I=${target}:TP=-2:LRA=20:print_format=json`, "-f", "null", "-"]);
  const stats = JSON.parse(log.slice(log.lastIndexOf("{"), log.lastIndexOf("}") + 1));
  return `loudnorm=I=${target}:TP=-2:LRA=20:measured_I=${stats.input_i}:measured_TP=${stats.input_tp}:measured_LRA=${stats.input_lra}:measured_thresh=${stats.input_thresh}:offset=${stats.target_offset}:linear=true`;
}

const temporaryFiles = [];
const temporary = (name) => {
  const file = path.join(audioDirectory, `.${name}.wav`);
  temporaryFiles.push(file);
  return file;
};
const fit = `apad=whole_dur=${DURATION},atrim=0:${DURATION}`;
const inputs = [];
const graph = [];
const mixed = [];

try {
  let bedInput = -1;
  if (music) {
    const bed = temporary("bed");
    ffmpeg(["-i", music, "-af", [
      offset >= 0
        ? `atrim=start=${offset},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,afade=t=in:st=0.3:d=1.5`
        : `aresample=48000,aformat=channel_layouts=stereo,adelay=${Math.round(-offset * 1000)}:all=1`,
      `afade=t=out:st=${DURATION - 3.2}:d=3.0,${fit}`,
    ].join(","), "-c:a", "pcm_f32le", bed]);
    const levelledBed = temporary("bed-levelled");
    // loudnorm resamples internally and can shorten a file by a fraction of a second, so pad back to length after it.
    ffmpeg(["-i", bed, "-af", `${loudnessFilter(bed, MUSIC_LOUDNESS)},aresample=48000,${fit}`, "-ar", "48000", "-c:a", "pcm_f32le", levelledBed]);
    bedInput = inputs.push(levelledBed) - 1;
  }
  if (fs.existsSync(effects)) {
    const effectsInput = inputs.push(effects) - 1;
    graph.push(`[${effectsInput}:a]aresample=48000,aformat=channel_layouts=stereo,volume=${EFFECTS_GAIN},${fit}[effects]`);
    mixed.push("[effects]");
  }
  if (narration) {
    const voice = temporary("voice");
    // Studio pass for a laptop mic: repair clipped peaks, trim rumble and hiss, pull down boxiness,
    // add presence and air, tame sibilance, then even out the level.
    const studio = [
      "adeclip",
      "highpass=f=85:p=2",
      "afftdn=nr=8:nf=-60:tn=1",
      "equalizer=f=400:t=q:w=1.2:g=-3",
      "equalizer=f=3500:t=q:w=1.2:g=4.5",
      "highshelf=f=8000:g=4",
      "deesser=i=0.4:m=0.5:f=0.5",
      "acompressor=threshold=0.1:ratio=3:attack=5:release=80:knee=3:makeup=2",
    ].join(",");
    ffmpeg(["-i", narration, "-af", ["aresample=48000", ...(args.raw ? [] : [studio]), fit].join(","), "-ac", "2", "-c:a", "pcm_f32le", voice]);
    const levelledVoice = temporary("voice-levelled");
    ffmpeg(["-i", voice, "-af", `${loudnessFilter(voice, VOICE_LOUDNESS)},aresample=48000,${fit}`, "-ar", "48000", "-c:a", "pcm_f32le", levelledVoice]);
    const voiceInput = inputs.push(levelledVoice) - 1;
    if (music) {
      // A gentle extra dip while the voice is up; the bed is already quiet, so this only clears room for consonants.
      graph.push(`[${voiceInput}:a]asplit=2[voice][key]`, `[${bedInput}:a][key]sidechaincompress=threshold=0.03:ratio=4:attack=30:release=500:mix=0.6[bed]`);
    } else {
      graph.push(`[${voiceInput}:a]anull[voice]`);
    }
    mixed.push("[voice]");
  } else if (music) {
    graph.push(`[${bedInput}:a]anull[bed]`);
  }
  if (music) mixed.unshift("[bed]");
  if (!mixed.length) throw new Error("Nothing to mix: give --music or --narration, or run audio/render-sfx.mjs first.");
  graph.push(`${mixed.join("")}amix=inputs=${mixed.length}:normalize=0:duration=longest,alimiter=limit=0.84:level=false,${fit}[mixed]`);
  ffmpeg([...inputs.flatMap((file) => ["-i", file]), "-filter_complex", graph.join(";"), "-map", "[mixed]", "-ar", "48000", "-c:a", "pcm_s24le", output]);
} finally {
  for (const file of temporaryFiles) fs.rmSync(file, { force: true });
}
const check = ffmpeg(["-nostats", "-i", output, "-af", "ebur128=peak=true", "-f", "null", "-"]);
const summary = check.slice(check.lastIndexOf("Summary:"));
console.log(`wrote ${path.relative(root, output)}`, summary.match(/I:\s+(-?[\d.]+) LUFS/)[0], summary.match(/Peak:\s+(-?[\d.]+) dBFS/)[0]);
