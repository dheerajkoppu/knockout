# The demo video

`out/knockout-demo.mp4` is the 3:00 video (exactly 180.0 s), with burned-in captions, and
`out/knockout-demo-captions.srt` is the same captions for YouTube or Vimeo. Until someone records the
narration, the voice is the macOS guide voice; record a person before submitting (below).

- `STORYBOARD.md`: what the video is for, the requirements and where each lands, the look, the scene list, where
  every number comes from, and which beats are still pending.
- `NARRATION.md`: the timed script for the narrator, generated from `stage/script.json`.

The video is a web page rendered frame by frame (the `demo-video` kit): `stage/stage.html`, `stage.css` and
`stage.js` draw every frame as a function of time; `render.mjs` screenshots each frame in headless Chromium and
encodes with ffmpeg. Every number on screen is read from `capture/raw/` and the repository by
`capture/facts.mjs`.

## Set up once

```bash
cd video
npm install                        # gsap and playwright, pinned in package.json
npx playwright install chromium    # skip if ~/Library/Caches/ms-playwright already has chromium-1243
```

Needs Node, ffmpeg and ImageMagick (`magick`). Capturing also needs the repository's `.venv`, `agents/.venv`,
the built web page (`web/.next`) and Docker for the local TimescaleDB, as set up in `RUNBOOK.md`.

## Re-render after something changes

Two commands. The first reads the running app, the second builds the video from what was read.

```bash
capture/capture-all.sh --serve     # starts the API on :8800 and the web build on :3300, captures, stops them
./build.sh                         # about 3 minutes: facts, lines, voice, effects, music, picture, out/
```

`capture-all.sh` without `--serve` uses an API and web build that are already running (`API_URL`, `WEB_URL`;
`BUILT_API_URL` is the `NEXT_PUBLIC_API_URL` the web build was made with, and calls to it are forwarded to
`API_URL`). `./build.sh --draft` writes a quicker `renders/draft.mp4` instead of `out/`. Both scripts stop with a
message if a line runs into the next one, a fact a line needs is missing, or the file is not exactly 180.0 s.

### When each pending beat becomes real

`capture/facts.mjs` works out each beat from the capture and prints which are real. The stage swaps the picture
and `lib/cues.mjs` swaps the wording by itself; `NARRATION.md` lists both wordings.

| To make this real                                     | Do this, then `capture/capture-all.sh --serve && ./build.sh`                                                                                                                                                                                                                                                                                                            |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The report page's evidence (now the labelled fixture) | Set `GEMINI_API_KEY` in the root `.env`, `make warm` (RUNBOOK §4), then capture. If the meningococcal prediction comes back `on_label` with its quote, the live page replaces the fixture and the narration uses the live counts. If it does not, the build stops and asks for `report-2` and `report-3` in `stage/script.json` to be rewritten for what the page shows |
| The agents in ASI:One (now a pending card) | Register the agents (`agents/README.md`), ask "What side effects should a C5 blocker cause?" in ASI:One, screen-record it with QuickTime and save it as `capture/raw/asi-one.mp4`. `capture/prepare.sh` turns it into frames; set `"asiOneIn": <second>` in `stage/status.json` to start from the moment the question is sent |
| The benchmark numbers (now "not measured")            | `.venv/bin/python -m benchmark.score --generate-mappings` (RUNBOOK §4). The beat turns real once `benchmark/results/results.json` is complete under the drug set's protocol version                                                                                                                                                                                     |
| A candidate new signal (now a pending card)           | After scoring, a person picks one from `benchmark/results/RESULTS.md` and writes it into `stage/status.json`: `{"candidateChoice": {"drug": "<generic name>", "hpo_id": "HP:..."}}`. Read its caveats before choosing; it is shown as a candidate, never a finding                                                                                                      |
| The Creao scheduled run (now a pending card)          | Build the agent from `creao/AGENT.md`, let it run on its schedule against the public API, and save a screen recording or screenshot of the run as `capture/raw/creao-run.mp4` (or `.png`; `"creaoIn"` in `stage/status.json` sets the start). It counts once the trend's term came from a report, not `--term`                                                                                                             |

`stage/status.json` can force a beat back to pending (`{"asiOne": "pending"}`), for example to cut a recording
that came out badly. A beat shown from footage cannot be forced ready without its footage.

After a beat changes, re-record the lines whose wording changed (`NARRATION.md`, "Wording that changes") as
pickups in the booth.

## Record the narration

Do this last, once the script and the cut are settled.

```bash
./build.sh                         # makes renders/knockout-demo.mp4, the picture with music and effects only
node narration/serve.mjs           # or double-click "Start Recording Booth.command"
```

Open http://localhost:4400/narration/booth.html in Chrome, with headphones on, in a quiet small room, with the
best microphone available:

1. **Turn on microphone** and allow it. Untick "Film the presenter too" unless you want a corner camera.
2. **Record**: after a three-second countdown the video plays and each line appears as it should be said. Read
   from `NARRATION.md` if that is easier. Say "fixture" clearly in `report-2`.
3. **Listen to take** to check it; record again as often as needed.
4. **Use this take** saves `narration/narration.wav`, mixes it, re-times the captions to the voice and re-renders
   in the background (`renders/knockout-demo-narrated.mp4`).
5. Run `./build.sh` once more: it finds `narration/narration.wav` and `stage/data/caption-timing.json` and writes
   `out/knockout-demo.mp4` and `out/knockout-demo-captions.srt` with the real voice.

To fix one line, pick it in the booth's "Record" menu: it plays from three seconds before the line and splices
only that line into the saved take. `narration/*.wav` is not committed; keep a copy of the take.

## Music

The bed is synthesized (`audio/score.html`, adapted from the kit's example score; seeded Web Audio, nothing to
license), with its sections placed on the scene times. There are two options:

```bash
./build.sh --draft --music=a       # D major, brighter (the default in project.json)
./build.sh --draft --music=b       # starts in B minor, more sombre
```

Pick one and set `music.file` in `project.json` to `audio/music-a.wav` or `audio/music-b.wav`, so the booth's
mix uses it too. A licensed track can replace it: record it in `audio/tracks/SOURCES.md`, set `music.file`,
`drop` and `alignTo` in `project.json`, and change the `--music` lines in `build.sh`.

## Change the script or the picture

- A line's words or time: `stage/script.json` (both wordings of a line live there), then `./build.sh --draft`.
  Times are absolute seconds; the build warns when a line runs into the next.
- A scene: `stage/stage.js` places every tween against a cue time (`cueAt["report-3"]`), so moving a line moves
  its picture. Check stills before a full render:
  `node render.mjs --stills=84.5,88,95.5 --dir=renders/stills && ./sheet.sh renders/sheet.jpg renders/stills/*.jpg`.
- Live preview in a browser: `node render.mjs --serve`, then open the printed URL with `?play` or `?t=84`.
- Check the length: `ffprobe -v error -show_entries format=duration -of csv=p=0 out/knockout-demo.mp4` prints
  `180.000000`.

## Files

| Path                                                  | What                                                                                                                                                                             |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `capture/capture.mjs`                                 | Playwright: the home page and its search one key at a time, full-page screenshots of the live report, the fixture and ibrutinib, every element's position, and the API's answers |
| `capture/handcheck.py`                                | The engine's own label match and FAERS counts for one hand-chosen term, and the catalog size                                                                                     |
| `capture/capture-all.sh`                              | All captures in order, including one local agents chat, a watch dry run and the trigger demo                                                                                     |
| `capture/prepare.sh`                                  | Crops the typing frames into `stage/footage/`                                                                                                                                    |
| `capture/facts.mjs`                                   | Every fact the video shows, and which beats are real, into `stage/data/facts.json`                                                                                               |
| `capture/raw/`                                        | What was captured on 17 Oct 2026 (committed, so anyone can re-render)                                                                                                            |
| `stage/script.json`                                   | The narration, with the final wording of each pending line                                                                                                                       |
| `lib/cues.mjs`, `lib/narration-md.mjs`, `lib/srt.mjs` | The lines in use, `NARRATION.md`, the captions file                                                                                                                              |
| `stage/`                                              | The stage: markup, look, scenes, the kit's engine, IBM Plex fonts                                                                                                                |
| `audio/`                                              | Guide voice, effects (`sfx.html`), music (`score.html`), the mix                                                                                                                 |
| `narration/`                                          | The recording booth                                                                                                                                                              |
| `build.sh`                                            | Everything after capture, ending in `out/`                                                                                                                                       |
