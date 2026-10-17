/* Stage engine. Every frame is a pure function of time: renderAt(t) seeks one paused GSAP timeline,
   then updaters derive clocks, counters, phone footage, and touches from t. stage.js builds the scenes. */
gsap.registerPlugin(CustomEase);
const ENTER = CustomEase.create("enter", ".23,1,.32,1");
const MOVE = CustomEase.create("move", ".77,0,.175,1");
const DRAWER = CustomEase.create("drawer", ".32,.72,0,1");
const SOURCE_FPS = 60;
const SCREEN_WIDTH = 408;
let pointsWidth = 402;
const SVG_NS = "http://www.w3.org/2000/svg";

const tl = gsap.timeline({ paused: true });
const updaters = [];
// Image decodes still in flight; renderAt waits for them so a screenshot never catches a stale frame.
const pending = [];
const $ = (selector) => document.querySelector(selector);

function svg(parent, tag, attributes = {}) {
  const element = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attributes))
    element.setAttribute(key, value);
  parent.appendChild(element);
  return element;
}

function pathData(points) {
  return points
    .map((point, index) => `${index ? "L" : "M"}${point[0]},${point[1]}`)
    .join(" ");
}

const clamp = (value, low = 0, high = 1) =>
  Math.min(high, Math.max(low, value));
const lerp = (from, to, amount) => from + (to - from) * amount;

/* Scenes are stacked in chronological DOM order and own their section's opacity, transform, and filter.
   The incoming scene arrives over the outgoing one, which stays opaque underneath until the move is done.
   "dissolve": blur and slight scale settle; "push": the new scene slides in from the right (dark and light
   grounds meet at a clean edge); "zoom": the new scene drops in from above, for plates and maps.
   Only a scene given a fadeOut fades away; use that for the last one. */
let previousScene = null;
function scene(
  selector,
  start,
  end,
  duration = 0.6,
  fadeOut = 0,
  style = "dissolve",
) {
  const element = $(selector);
  const outgoing = previousScene;
  tl.set(element, { visibility: "visible" }, start);
  if (style === "push") {
    tl.fromTo(
      element,
      { opacity: 1, x: 1920 },
      { x: 0, duration, ease: MOVE },
      start,
    );
    if (outgoing) tl.to(outgoing, { x: -560, duration, ease: MOVE }, start);
  } else if (style === "zoom") {
    tl.fromTo(
      element,
      { opacity: 0, scale: 1.14, filter: "blur(14px)" },
      { opacity: 1, scale: 1, filter: "blur(0px)", duration, ease: ENTER },
      start,
    );
    if (outgoing)
      tl.to(
        outgoing,
        { scale: 0.94, filter: "blur(10px)", duration, ease: ENTER },
        start,
      );
  } else {
    tl.fromTo(
      element,
      { opacity: 0, scale: 1.03, filter: "blur(12px)" },
      { opacity: 1, scale: 1, filter: "blur(0px)", duration, ease: ENTER },
      start,
    );
    if (outgoing)
      tl.to(
        outgoing,
        { scale: 0.985, filter: "blur(6px)", duration, ease: ENTER },
        start,
      );
  }
  if (fadeOut > 0) {
    tl.to(
      element,
      { opacity: 0, duration: fadeOut, ease: "none" },
      end - fadeOut,
    );
    tl.set(element, { visibility: "hidden" }, end);
  } else {
    tl.set(element, { visibility: "hidden" }, end + duration + 0.1);
  }
  previousScene = element;
}

/* Place image point (px, py) at stage point (sx, sy) at the given scale. */
function camera(px, py, scale, sx = 960, sy = 540) {
  return { x: sx - px * scale, y: sy - py * scale, scale };
}

/* A drawable route: stroke progress is a proxy, applied every frame so seeking is exact. */
function drawable(
  parent,
  points,
  { width = 9, casing = 16, className = "route-line", head = false } = {},
) {
  const group = svg(parent, "g");
  const casingPath = casing
    ? svg(group, "path", {
        d: pathData(points),
        class: "route-casing",
        "stroke-width": casing,
      })
    : null;
  const path = svg(group, "path", {
    d: pathData(points),
    class: className,
    "stroke-width": width,
  });
  const length = path.getTotalLength();
  const headDot = head
    ? svg(group, "circle", {
        r: width * 1.15,
        class: "route-head",
        "stroke-width": 4,
      })
    : null;
  const state = { progress: 0, start: 0, opacity: 1 };
  const apply = () => {
    const visible = Math.max(0, state.progress - state.start) * length;
    for (const element of [casingPath, path].filter(Boolean)) {
      element.style.strokeDasharray = `${visible} ${length + 10}`;
      element.style.strokeDashoffset = -state.start * length;
    }
    group.style.opacity = state.opacity;
    if (headDot) {
      const point = path.getPointAtLength(state.progress * length);
      headDot.setAttribute("cx", point.x);
      headDot.setAttribute("cy", point.y);
      headDot.style.opacity =
        state.progress > 0.002 && state.progress < 0.998 ? 1 : 0;
    }
  };
  updaters.push(apply);
  return { group, path, state, length };
}

function pin(parent, point, label, color) {
  const group = svg(parent, "g", {
    transform: `translate(${point[0]},${point[1]})`,
  });
  const inner = svg(group, "g");
  svg(inner, "circle", {
    r: 17,
    fill: color,
    stroke: "#fff",
    "stroke-width": 5,
  });
  const text = svg(inner, "text", {
    class: "pin-label",
    x: 0,
    y: -40,
    "text-anchor": "middle",
  });
  text.textContent = label;
  const width = label.length * 12.5 + 34;
  const capsule = svg(inner, "rect", {
    class: "pin-capsule",
    x: -width / 2,
    y: -67,
    width,
    height: 38,
    rx: 19,
  });
  inner.insertBefore(capsule, text);
  return inner;
}

function tag(parent, point, label, color, textColor = "#fff") {
  const group = svg(parent, "g", {
    transform: `translate(${point[0]},${point[1]})`,
  });
  const inner = svg(group, "g");
  const width = label.length * 11.2 + 40;
  svg(inner, "rect", {
    x: -width / 2,
    y: -21,
    width,
    height: 42,
    rx: 12,
    fill: color,
  });
  const text = svg(inner, "text", {
    class: "tag-text",
    x: 0,
    y: 7,
    "text-anchor": "middle",
    fill: textColor,
  });
  text.textContent = label;
  return inner;
}

/* Captions: each cue splits on "|" into phrases timed by character share of the voice line. */
function buildCaptions(cues, durations, lightRanges) {
  const caption = $("#caption");
  const phrases = [];
  for (const cue of cues) {
    const parts = cue.text.split("|").map((part) => part.trim());
    const total = parts.reduce(
      (sum, part) => sum + part.replace(/\*/g, "").length,
      0,
    );
    let at = cue.at;
    const duration = durations[cue.id] || 3;
    for (const part of parts) {
      const share = part.replace(/\*/g, "").length / total;
      phrases.push({
        start: at,
        end: at + duration * share + 0.25,
        html: part.replace(/\*(.+?)\*/g, '<span class="hi">$1</span>'),
      });
      at += duration * share;
    }
  }
  let current = null;
  updaters.push((t) => {
    const phrase = phrases.find((item) => t >= item.start && t < item.end);
    if (phrase !== current) {
      caption.innerHTML = phrase ? phrase.html : "";
      current = phrase;
    }
    if (!phrase) {
      caption.style.opacity = 0;
      return;
    }
    const fade = Math.min(
      clamp((t - phrase.start) / 0.12),
      clamp((phrase.end - t) / 0.12),
    );
    caption.style.opacity = fade;
    caption.classList.toggle(
      "on-light",
      lightRanges.some(([from, to]) => t >= from && t < to),
    );
  });
}

/* Phone footage: shots map stage time to source frames; touches come from the XCUITest event log.
   A shot is { id, scene, in, start, end, rate, fade?, filter? }: source second `in` plays at stage second
   `start`, at `rate` times real speed, until `end`; `fade` crossfades in from the shot before it. */
function buildPhone(shots, events) {
  const images = [$("#screenA"), $("#screenB")];
  const touches = $("#touches");
  const touchList = [];
  for (const shot of shots) {
    // Footage filmed on a real phone has no XCUITest log, so it has no touches.
    for (const event of events[shot.scene]?.events ?? []) {
      if (event.kind !== "tap") continue;
      const stageTime = shot.start + (event.t - shot.in) / shot.rate;
      if (stageTime < shot.start + 0.05 || stageTime > shot.end - 0.1) continue;
      const element = document.createElement("div");
      element.className = "touch";
      const [x, y, w, h] = event.rect;
      element.style.left = `${((x + w / 2) * SCREEN_WIDTH) / pointsWidth}px`;
      element.style.top = `${((y + h / 2) * SCREEN_WIDTH) / pointsWidth}px`;
      touches.appendChild(element);
      touchList.push({ element, time: stageTime });
    }
  }
  const setFrame = (image, shot, t) => {
    const sourceTime = shot.in + (t - shot.start) * shot.rate;
    const frame = Math.max(
      1,
      Math.round((sourceTime - shot.in) * SOURCE_FPS) + 1,
    );
    const src = `footage/${shot.id}/${String(frame).padStart(5, "0")}.jpg`;
    if (image.getAttribute("src") !== src) {
      image.setAttribute("src", src);
      pending.push(image.decode().catch(() => {}));
    }
  };
  updaters.push((t) => {
    const active = shots.filter(
      (shot) => t >= shot.start - (shot.fade || 0) && t < shot.end,
    );
    const [first, second] = active;
    if (first) {
      setFrame(images[0], first, Math.max(t, first.start));
      images[0].style.opacity = 1;
    } else images[0].style.opacity = 0;
    if (second) {
      setFrame(images[1], second, Math.max(t, second.start));
      images[1].style.opacity = clamp(
        (t - (second.start - (second.fade || 0))) / (second.fade || 0.001),
      );
    } else images[1].style.opacity = 0;
    for (const touch of touchList) {
      const age = t - touch.time;
      if (age < -0.02 || age > 0.55) {
        touch.element.style.opacity = 0;
        continue;
      }
      const press = clamp(age / 0.12);
      const release = clamp((age - 0.18) / 0.37);
      touch.element.style.opacity = press * (1 - release);
      touch.element.style.transform = `scale(${lerp(0.7, 1, press) + release * 0.35})`;
    }
  });
}

/* The presenter's booth camera: frame n of each sequence is stage time n / fps (cut by stage/presenter.mjs).
   The corner window shows inside windowRanges; each wide image is [element, name in project.json's
   presenter.wide] and plays with its scene. */
function buildPresenter(presenter, windowRanges, wideImages = []) {
  const show = (image, folder, [first, last], t) => {
    const frame = Math.min(
      last,
      Math.max(first, Math.round(t * presenter.fps)),
    );
    const src = `footage/${folder}/${String(frame).padStart(5, "0")}.jpg`;
    if (image.getAttribute("src") !== src) {
      image.setAttribute("src", src);
      pending.push(image.decode().catch(() => {}));
    }
  };
  const windowElement = $("#presenterWindow");
  const windowImage = $("#presenterWindowImage");
  const wideShots = wideImages
    .filter(([, name]) => presenter.wide[name])
    .map(([image, name]) => [image, `presenter/${name}`, presenter.wide[name]]);
  updaters.push((t) => {
    const opacity = Math.max(
      0,
      ...windowRanges.map(([from, to]) =>
        Math.min(clamp((t - from) / 0.4), clamp((to - t) / 0.4)),
      ),
    );
    windowElement.style.opacity = opacity;
    if (opacity > 0)
      show(windowImage, "presenter-window", [0, presenter.frames - 1], t);
    for (const [image, folder, range] of wideShots) {
      const frame = t * presenter.fps;
      if (frame >= range[0] && frame <= range[1]) show(image, folder, range, t);
    }
  });
}

function wordsInto(container, text, className = "w") {
  container.innerHTML = "";
  return text.split(" ").map((word) => {
    const span = document.createElement("span");
    const highlighted = word.startsWith("*");
    span.className = className + (highlighted ? " hi" : "");
    span.textContent = word.replace(/\*/g, "");
    container.append(span, " ");
    return span;
  });
}

function formatClock(seconds) {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}
/* Captions follow the recorded narration once caption-timing.json exists, otherwise the script's cue times. */
function timedCaptions(cues, durations, captionTiming) {
  const spoken = (cue) => captionTiming[cue.id];
  return {
    cues: cues.map((cue) =>
      spoken(cue) ? { ...cue, at: spoken(cue).start } : cue,
    ),
    durations: Object.fromEntries(
      cues.map((cue) => [
        cue.id,
        spoken(cue) ? spoken(cue).end - spoken(cue).start : durations[cue.id],
      ]),
    ),
  };
}

async function loadStage() {
  const read = (url, fallback) =>
    fetch(url)
      .then((response) => (response.ok ? response.json() : fallback))
      .catch(() => fallback);
  const [project, cues, durations, events, shots, captionTiming, presenter] =
    await Promise.all([
      read("../project.json", {}),
      read("cues.json", []),
      read("data/vo-durations.json", {}),
      read("data/events.json", {}),
      read("data/shots.json", []),
      read("data/caption-timing.json", {}),
      read("data/presenter.json", null),
    ]);
  pointsWidth = project.device?.pointsWidth ?? pointsWidth;
  const cueAt = Object.fromEntries(cues.map((cue) => [cue.id, cue.at]));
  // lib/project.mjs computes the same length for the audio scripts.
  const END = project.duration ?? cues.at(-1).at + (project.endAfterLastCue ?? 6);
  window.DURATION = END;
  const hidePresenter = new URLSearchParams(location.search).has("nopresenter");
  return {
    project,
    cues,
    cueAt,
    durations,
    events,
    shots,
    captionTiming,
    presenter: hidePresenter ? null : presenter,
    END,
  };
}

window.renderAt = async (t) => {
  tl.seek(t, false);
  for (const update of updaters) update(t);
  await Promise.all(pending.splice(0));
};

/* startStage(build): build({ project, cues, cueAt, durations, events, shots, captionTiming, presenter, END })
   adds every scene to the timeline. The renderer waits on window.ready, then calls renderAt once per frame. */
function startStage(build) {
  const query = new URLSearchParams(location.search);
  if (query.has("clean")) document.body.classList.add("clean");
  if (query.has("nocaptions")) document.body.classList.add("nocaptions");
  window.ready = loadStage().then(async (stage) => {
    await build(stage);
    tl.set({}, {}, stage.END);
    return true;
  });
  if (query.has("play") || query.has("t"))
    window.ready.then(() => preview(query));
}

/* Browser preview: ?t=12.5 holds one frame, ?play runs in real time (with &t= to start partway). */
function preview(query) {
  document.body.classList.add("preview");
  const stage = $("#stage");
  const fit = () => {
    stage.style.transform = `scale(${Math.min(innerWidth / 1920, innerHeight / 1080)})`;
  };
  fit();
  addEventListener("resize", fit);
  const from = Number(query.get("t") || 0);
  if (!query.has("play")) return window.renderAt(from);
  const started = performance.now();
  const tick = async () => {
    const t = from + (performance.now() - started) / 1000;
    await window.renderAt(Math.min(t, window.DURATION));
    if (t < window.DURATION) requestAnimationFrame(tick);
  };
  tick();
}
