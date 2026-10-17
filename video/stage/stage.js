/* Knockout's demo, scene by scene. Every scene and tween is placed against cue times, so re-timing a line in
   script.json moves its picture with it. Facts come from stage/data/facts.json and capture/raw/pages.json;
   nothing on screen is typed in here except labels and the rules the protocol states. */
const AMBER = "#eeac53";
const WHITE = "#ffffff";
const SFX = {
  whooshes: [],
  pops: [],
  chimes: [],
  taps: [],
  keys: [],
  risers: [],
};
window.SFX = SFX;

startStage(
  async ({ cues, cueAt, durations, captionTiming, presenter, END }) => {
    const [facts, pages] = await Promise.all([
      fetch("data/facts.json").then((response) => response.json()),
      fetch("../capture/raw/pages.json").then((response) => response.json()),
    ]);
    await Promise.all(
      [
        '400 20px "IBM Plex Sans"',
        '500 20px "IBM Plex Sans"',
        '600 20px "IBM Plex Sans"',
        '400 20px "IBM Plex Mono"',
        '500 20px "IBM Plex Mono"',
        '600 20px "IBM Plex Mono"',
      ].map((font) => document.fonts.load(font)),
    );
    const status = facts.status;
    const spoken = (id) => durations[id] || 3;
    const at = (id, share) => cueAt[id] + spoken(id) * share;
    const endOf = (id) => cueAt[id] + spoken(id);
    const rise = (y = 30, duration = 0.7) => [
      { opacity: 0, y },
      { opacity: 1, y: 0, duration, ease: ENTER },
    ];
    const enter = (target, time, y = 30, duration = 0.7) =>
      tl.fromTo(target, ...rise(y, duration), time);
    const leave = (target, time, duration = 0.3) =>
      tl.to(target, { opacity: 0, y: -12, duration, ease: "power2.in" }, time);
    const html = (selector, value) => ($(selector).innerHTML = value);
    const escape = (text) =>
      text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const bold = (text) =>
      escape(text.replace(/^_(.*)_$/, "$1")).replace(
        /\*\*(.+?)\*\*/g,
        "<b>$1</b>",
      );
    const drawPath = (element, time, duration, ease = MOVE) => {
      const length = element.getTotalLength();
      gsap.set(element, { strokeDasharray: length, strokeDashoffset: length });
      tl.to(element, { strokeDashoffset: 0, duration, ease }, time);
    };
    const wipe = (element, time, duration) =>
      tl.fromTo(
        element,
        { clipPath: "inset(-10% 100% -10% 0)" },
        { clipPath: "inset(-10% 0% -10% 0)", duration, ease: "none" },
        time,
      );
    const decodeAll = (images) =>
      Promise.all(images.map((image) => image.decode().catch(() => {})));

    /* ---------- Hook: the genetic knockout and the chemical one land on the same disease ---------- */
    const hook = facts.hook;
    const titleStart = endOf("hook-4") + 0.6;
    scene("#hook", 0, titleStart, 0.01);
    $("#hookGene").textContent = hook.gene;
    $("#hookGeneMeta").textContent = `${hook.disease} · IUIS classification`;
    const [cases, of] = hook.frequency.split("/");
    const phenotypeMatch = hook.phenotype.replace(
      /(Neisseria meningitidis infection)/,
      '<span class="match">$1</span>',
    );
    html("#hookPhenotype", phenotypeMatch);
    $("#hookPhenotypeMeta").textContent =
      `${hook.hpoId} · ${cases} of ${of} reported cases · HPO annotations, ${hook.omim}`;
    $("#hookDrugName").textContent = hook.drug;
    $("#hookBlocks").textContent = `blocks ${hook.gene}`;
    $("#hookDrugMeta").textContent =
      `ChEMBL ${hook.chemblId} · ${hook.action} of ${hook.protein} (${hook.accession})`;
    html(
      "#hookBoxedText",
      facts.label.title.replace(
        /(MENINGOCOCCAL INFECTIONS)/,
        '<span class="match">$1</span>',
      ),
    );
    $("#hookLabelMeta").textContent =
      `${hook.drug} label, boxed warning · effective ${facts.label.effective} · openFDA`;

    enter("#hookRoleA", cueAt["hook-1"] - 0.1, 16);
    enter("#hookGenetic .hook-subject", cueAt["hook-1"] + 0.1, 30, 0.8);
    enter("#hookGeneMeta", cueAt["hook-1"] + 0.7, 14);
    drawPath($("#hookArrowA path:first-child"), at("hook-1", 0.45), 0.5);
    tl.fromTo(
      "#hookArrowA path:last-child",
      { opacity: 0 },
      { opacity: 1, duration: 0.2 },
      at("hook-1", 0.45) + 0.4,
    );
    enter("#hookPhenotype", at("hook-1", 0.5), 24, 0.8);
    enter("#hookPhenotypeMeta", at("hook-1", 0.72), 14);

    enter("#hookRoleB", cueAt["hook-2"] - 0.2, 16);
    enter("#hookDrug .hook-subject", cueAt["hook-2"], 30, 0.8);
    tl.fromTo(
      "#hookBlocks",
      { opacity: 0, x: -16 },
      { opacity: 1, x: 0, duration: 0.6, ease: ENTER },
      at("hook-2", 0.62),
    );
    enter("#hookDrugMeta", at("hook-2", 0.8), 14);

    drawPath($("#hookArrowB path:first-child"), cueAt["hook-3"] + 0.1, 0.5);
    tl.fromTo(
      "#hookArrowB path:last-child",
      { opacity: 0 },
      { opacity: 1, duration: 0.2 },
      cueAt["hook-3"] + 0.5,
    );
    drawPath($("#hookBoxedRule"), cueAt["hook-3"] + 0.35, 0.8);
    wipe($("#hookBoxedText"), at("hook-3", 0.42), spoken("hook-3") * 0.5);
    enter("#hookLabelMeta", endOf("hook-3") - 0.2, 14);
    SFX.pops.push(cueAt["hook-3"] + 1.1);

    const matchAt = cueAt["hook-4"] + 0.25;
    tl.to(
      "#hook .match",
      { color: AMBER, duration: 0.6, ease: "power1.inOut" },
      matchAt,
    );
    tl.to(
      "#hookBoxedRule",
      { stroke: AMBER, duration: 0.6, ease: "power1.inOut" },
      matchAt,
    );
    drawPath($("#hookBracketPath"), matchAt + 0.15, 0.7);
    tl.fromTo(
      "#hookSame",
      { opacity: 0, x: -12 },
      { opacity: 1, x: 0, duration: 0.6, ease: ENTER },
      matchAt + 0.55,
    );
    SFX.chimes.push(matchAt + 0.05);

    /* ---------- Title ---------- */
    const methodStart = cueAt["method-1"] - 0.3;
    scene("#title", titleStart, methodStart, 0.5);
    enter("#titleWord", titleStart + 0.15, 30, 0.8);
    enter("#titleKicker", titleStart + 0.7, 18);
    SFX.pops.push(titleStart + 0.2);

    /* ---------- Method: the idea in one sentence ---------- */
    const agentsStart = cueAt["agents-1"] - 0.5;
    scene("#method", methodStart, agentsStart, 0.75, 0, "push");
    SFX.whooshes.push(methodStart + 0.35);
    enter("#methodKicker", cueAt["method-1"], 20);
    const methodWords = wordsInto(
      $("#methodText"),
      "A drug that blocks a protein is a *chemical* *knockout.*",
    );
    methodWords.forEach((word, index) =>
      tl.fromTo(
        word,
        ...rise(26, 0.55),
        cueAt["method-2"] +
          0.05 +
          index * ((spoken("method-2") * 0.48) / methodWords.length),
      ),
    );
    enter("#methodSub", at("method-2", 0.58), 22);

    /* ---------- Agents: the five Fetch.ai agents answer one question, run locally ---------- */
    const agents = facts.agents;
    const reportStart = cueAt["report-1"] - 0.6;
    scene("#agents", agentsStart, reportStart, 0.6);
    $("#agentsRunAt").textContent =
      `${agents.ranAt.replace("T", " ").replace("Z", " UTC")} · local run, live API`;
    const shortAddress = (text) =>
      text.replace(/agent1q\w{8,}/g, (address) => `${address.slice(0, 12)}…`);
    const terminalLines = [
      {
        kind: "prompt",
        text: `python -m knockout_agents.ask "${agents.question}"`,
      },
      ...agents.events.map((event) => ({
        kind: "log",
        agent: event.agent,
        html: `<b>[${event.agent}]</b> ${escape(shortAddress(event.message.replace(`${event.agent}: `, "")))}`,
      })),
      { kind: "blank" },
      ...agents.reply
        .filter(
          (line, index, list) => line.trim() || (list[index - 1] ?? "").trim(),
        )
        .map((line) => ({
          kind: line.trim() ? "reply" : "blank",
          html: bold(line),
        })),
    ];
    const agentsBody = $("#agentsBody");
    const lineElements = terminalLines.map((line) => {
      const element = document.createElement("div");
      element.className = `line ${line.kind}`;
      if (line.kind === "prompt") element.textContent = line.text;
      else if (line.html) element.innerHTML = line.html;
      agentsBody.appendChild(element);
      return element;
    });
    const lineIndex = (test) => terminalLines.findIndex(test);
    const promptLine = lineElements[0];
    tl.set(promptLine, { opacity: 1 }, agentsStart + 0.6);
    wipe(promptLine, cueAt["agents-1"] + 0.3, 2.4);
    for (let index = 0; index < 34; index++)
      SFX.keys.push(cueAt["agents-1"] + 0.3 + (index * 2.4) / 34);
    // The run took six seconds; the lines arrive in their real order, quickly, before the narration walks through them.
    const firstReply = lineIndex((line) => line.kind === "reply");
    const runStart = at("agents-1", 0.92);
    lineElements
      .slice(1, firstReply)
      .forEach((element, index) =>
        tl.to(
          element,
          { opacity: 1, duration: 0.12 },
          runStart + 0.15 + index * 0.09,
        ),
      );
    lineElements
      .slice(firstReply)
      .forEach((element, index) =>
        tl.to(
          element,
          { opacity: 1, duration: 0.12 },
          runStart + 1.1 + index * 0.05,
        ),
      );
    const terminalWindowHeight = 820 - 50;
    const bodyHeight = agentsBody.scrollHeight;
    const scrollTo = (element, time, duration = 0.9) => {
      const target = Math.max(
        -(bodyHeight - terminalWindowHeight + 10),
        Math.min(0, -(element.offsetTop - 30)),
      );
      tl.to(agentsBody, { y: target, duration, ease: MOVE }, time);
    };
    const focusLines = (indexes, time) => {
      lineElements.forEach((element, index) => {
        if (index === 0) return;
        tl.to(
          element,
          { opacity: indexes.includes(index) ? 1 : 0.32, duration: 0.4 },
          time,
        );
      });
    };
    const replyIndex = (pattern) =>
      lineIndex((line) => line.kind === "reply" && pattern.test(line.html));
    const logIndexes = (agent) =>
      terminalLines
        .map((line, index) => (line.agent === agent ? index : -1))
        .filter((index) => index >= 0);

    enter("#agentsHead", cueAt["agents-1"], 20);
    $("#agentOrchestratorResult").textContent =
      `${agents.drugCount} approved drugs block ${facts.hook.protein} → ${agents.chosen}`;
    $("#agentOthers").textContent = `Also: ${agents.others.join(", ")}`;
    enter("#agentOrchestrator", cueAt["agents-2"], 24);
    tl.set(
      "#agentOrchestrator",
      { attr: { class: "agent agent-orchestrator lit" } },
      cueAt["agents-2"] + 0.3,
    );
    focusLines(
      [...logIndexes("knockout-orchestrator"), firstReply],
      cueAt["agents-2"] + 0.2,
    );
    scrollTo(lineElements[1], cueAt["agents-2"] + 0.2);
    SFX.pops.push(cueAt["agents-2"] + 0.15);

    const specialists = [
      {
        id: "#agentTarget",
        cue: "agents-4",
        agent: "target-agent",
        result: `${facts.hook.protein} · ${facts.hook.action}, so it ${facts.hook.effect} its activity`,
        state: agents.target,
        reply: /lowers the activity/,
      },
      {
        id: "#agentGenetics",
        cue: "agents-5",
        agent: "genetics-agent",
        result: `${facts.hook.disease}: ${facts.report.predictionCount} symptoms, each in ${cases} of ${of} cases`,
        state: agents.genetics,
        reply: /People born with/,
      },
      {
        id: "#agentLabel",
        cue: "agents-6",
        agent: "label-agent",
        result: "Boxed warning, warnings and adverse reactions, word for word",
        state: agents.labelAgent,
        reply: /Could not run/,
      },
      {
        id: "#agentSignal",
        cue: "agents-6",
        agent: "signal-agent",
        result: "PRR and the Evans criteria on FAERS counts",
        state: agents.signal,
        reply: /Could not run/,
      },
    ];
    specialists.forEach((specialist, index) => {
      const appear = cueAt[specialist.cue] + (index === 3 ? 0.35 : 0);
      $(`${specialist.id}Result`).textContent = specialist.result;
      enter(specialist.id, appear, 24);
      tl.set(specialist.id, { attr: { class: "agent lit" } }, appear + 0.3);
      SFX.pops.push(appear + 0.1);
      const statusElement = $(`${specialist.id}Status`);
      const known = specialist.state === "ok";
      statusElement.textContent = specialist.state;
      statusElement.classList.toggle("unknown", !known);
      const statusAt = known
        ? appear + 0.9
        : cueAt["agents-7"] + 0.3 + (index - 2) * 0.35;
      tl.fromTo(
        statusElement,
        { opacity: 0 },
        { opacity: 1, duration: 0.4 },
        statusAt,
      );
      if (index < 3) {
        const indexes = [
          ...logIndexes(specialist.agent),
          ...(index === 2 ? logIndexes("signal-agent") : []),
        ];
        const reply = replyIndex(specialist.reply);
        if (reply >= 0) indexes.push(reply);
        focusLines(indexes, appear + 0.15);
        if (reply >= 0) scrollTo(lineElements[reply], appear + 0.1);
      }
    });
    // The two that could not run say why, in their own words.
    const statusLine = lineIndex(
      (line) => line.kind === "reply" && /^Agents:/.test(line.html),
    );
    const couldNot = replyIndex(/Could not run/);
    const unknownReason = (agent) =>
      agents.events
        .find((event) => event.agent === agent && /unknown/.test(event.message))
        ?.message.match(/\((.*)\)/)?.[1] ?? "";
    if (!status.asiOne || agents.labelAgent !== "ok") {
      for (const [selector, agent] of [
        ["#agentLabelResult", "label-agent"],
        ["#agentSignalResult", "signal-agent"],
      ]) {
        const reason = unknownReason(agent);
        if (!reason) continue;
        tl.to(
          selector,
          { opacity: 0, duration: 0.25 },
          cueAt["agents-7"] + 0.1,
        );
        tl.set(
          selector,
          { textContent: reason[0].toUpperCase() + reason.slice(1) },
          cueAt["agents-7"] + 0.36,
        );
        tl.to(selector, { opacity: 1, duration: 0.4 }, cueAt["agents-7"] + 0.4);
      }
    }
    focusLines(
      [couldNot, statusLine].filter((index) => index >= 0),
      cueAt["agents-7"] + 0.2,
    );
    scrollTo(lineElements[Math.max(couldNot, 0)], cueAt["agents-7"]);

    if (status.asiOne && facts.footage.asiOne) {
      // Footage of the same question in ASI:One, extracted by capture/prepare.sh at 30 fps.
      $("#asiOneFrame").hidden = false;
      $("#agentsPending").hidden = true;
      const start = cueAt["agents-7"] - 0.4;
      enter("#asiOneFrame", start, 30);
      tl.to(".agents-side", { opacity: 0, duration: 0.4 }, start);
      footagePlayer(
        $("#asiOneImage"),
        "footage/asi-one",
        start + 0.3,
        reportStart,
      );
    } else {
      html(
        "#agentsPendingBody",
        `Needs the five agents registered on Agentverse and this question asked in an ASI:One chat, recorded to <b>capture/raw/asi-one.mp4</b>.<br><br><b>Shown instead:</b> all five agents in one local process, against the live API (${agents.ranAt.slice(0, 10)}).`,
      );
      const pendingAt = endOf("agents-7") - 0.4;
      tl.to(".agents-side", { opacity: 0.12, duration: 0.5 }, pendingAt);
      enter("#agentsPending", pendingAt + 0.1, 30);
      SFX.pops.push(pendingAt + 0.2);
    }

    /* ---------- Report page: home search, the live chain, then the checked evidence ---------- */
    const benchStart = cueAt["bench-1"] - 0.5;
    scene("#report", reportStart, benchStart, 0.75, 0, "push");
    SFX.whooshes.push(reportStart + 0.35);
    const VIEW_WIDTH = 1620;
    const VIEW_HEIGHT = 864 - 44;
    const BASE = VIEW_WIDTH / 1440;
    const live = pages.eculizumab;
    const fixture = pages["eculizumab-fixture"];
    // The live page carries the evidence only once its meningococcal prediction is on the label with a quote.
    const meningococcalEntry = (page) =>
      (page.rects.entries ?? []).find((row) => /HP0005381/.test(row.id ?? ""));
    const entryHolds = (page, name) => {
      const entry = meningococcalEntry(page);
      return (page.rects[name] ?? []).some(
        (rect) => entry && rect.y >= entry.y && rect.y < entry.y + entry.h,
      );
    };
    const liveChecked =
      status.meningococcalOnLabel &&
      ["labelQuote", "twoByTwo", "statistic"].every((name) =>
        entryHolds(live, name),
      );
    const evidence = liveChecked ? live : fixture;
    $("#homeImage").src = "../capture/raw/home-00.jpg";
    $("#liveImage").src = `../capture/raw/${live.file}`;
    $("#fixtureImage").src = `../capture/raw/${fixture.file}`;
    await decodeAll([$("#homeImage"), $("#liveImage"), $("#fixtureImage")]);
    const top = (scroll) => ({ x: 0, y: -scroll * BASE, scale: BASE });
    const fit = (rect, page, { pad = 50, maxScale = 2.0 } = {}) => {
      const scale = Math.min(
        (VIEW_WIDTH - 2 * pad) / rect.w,
        (VIEW_HEIGHT - 2 * pad) / rect.h,
        maxScale,
      );
      let x = VIEW_WIDTH / 2 - (rect.x + rect.w / 2) * scale;
      let y = VIEW_HEIGHT / 2 - (rect.y + rect.h / 2) * scale;
      x = Math.min(0, Math.max(VIEW_WIDTH - 1440 * scale, x));
      y = Math.min(0, Math.max(VIEW_HEIGHT - page.height * scale, y));
      return { x, y, scale };
    };
    const union = (...rects) => {
      const left = Math.min(...rects.map((rect) => rect.x));
      const topEdge = Math.min(...rects.map((rect) => rect.y));
      const right = Math.max(...rects.map((rect) => rect.x + rect.w));
      const bottom = Math.max(...rects.map((rect) => rect.y + rect.h));
      return { x: left, y: topEdge, w: right - left, h: bottom - topEdge };
    };
    const move = (plate, view, time, duration = 1.1) =>
      tl.to(plate, { ...view, duration, ease: MOVE }, time);
    for (const plate of ["#homePlate", "#livePlate", "#fixturePlate"])
      gsap.set(plate, { transformOrigin: "0 0", ...top(0), opacity: 0 });
    // The home page's text sits in its left column; frame it from the kicker to the search scope note.
    const homeView = { x: 810 - 490 * 1.2, y: -160 * 1.2, scale: 1.2 };
    gsap.set("#homePlate", { ...homeView, opacity: 1 });
    tl.set("#reportPath", { textContent: "/" }, reportStart);

    const typingStart = cueAt["report-1"] + 0.15;
    const typingStep = 0.11;
    const typingFrames = 10;
    const typingImage = $("#typingImage");
    updaters.push((t) => {
      const frame = Math.max(
        1,
        Math.min(typingFrames, Math.floor((t - typingStart) / typingStep) + 1),
      );
      const source = `footage/typing/home-${String(frame).padStart(2, "0")}.jpg`;
      typingImage.style.opacity = t >= typingStart ? 1 : 0;
      if (typingImage.getAttribute("src") !== source) {
        typingImage.setAttribute("src", source);
        pending.push(typingImage.decode().catch(() => {}));
      }
    });
    for (let index = 0; index < typingFrames; index++)
      SFX.keys.push(typingStart + index * typingStep);
    const button = pages.home.button;
    const clickAt = typingStart + typingFrames * typingStep + 0.35;
    gsap.set("#reportTouch", {
      left: button.x + button.w / 2,
      top: button.y + button.h / 2,
      opacity: 0,
      scale: 0.7,
    });
    tl.to("#reportTouch", { opacity: 1, scale: 1, duration: 0.12 }, clickAt);
    tl.to(
      "#reportTouch",
      { opacity: 0, scale: 1.35, duration: 0.37 },
      clickAt + 0.18,
    );
    SFX.taps.push(clickAt);
    const reportShown = clickAt + 0.3;
    tl.set("#homePlate", { opacity: 0 }, reportShown);
    tl.set("#livePlate", { opacity: 1 }, reportShown);
    tl.set("#reportPath", { textContent: "/drug/eculizumab" }, reportShown);
    move(
      "#livePlate",
      fit(live.rects.chainSection[0], live, { pad: 40 }),
      reportShown + 0.9,
      1.3,
    );

    const uncheckedRect =
      live.rects.unchecked[0] ?? live.rects.effectsSection[0];
    move(
      "#livePlate",
      fit(union(live.rects.ledger[0] ?? uncheckedRect, uncheckedRect), live, {
        pad: 60,
      }),
      cueAt["report-2"] + 0.1,
      1.1,
    );

    const entry = meningococcalEntry(evidence) ?? evidence.rects.entries?.[0];
    const within = (rects) =>
      (rects ?? []).find(
        (rect) => rect.y >= entry.y && rect.y < entry.y + entry.h,
      );
    const quote = within(evidence.rects.labelQuote);
    const table = within(evidence.rects.twoByTwo);
    const statistic = within(evidence.rects.statistic);
    const evidencePlate = liveChecked ? "#livePlate" : "#fixturePlate";
    const evidenceIn = at("report-2", 0.36);
    if (!liveChecked) {
      // The fixture: same page, data filled in by hand from the live records, tagged on screen and in the narration.
      gsap.set("#fixturePlate", top(0));
      tl.to("#livePlate", { opacity: 0, duration: 0.5 }, evidenceIn);
      tl.to("#fixturePlate", { opacity: 1, duration: 0.5 }, evidenceIn);
      tl.set(
        "#reportPath",
        { textContent: "/drug/eculizumab?fixture=1" },
        evidenceIn,
      );
      tl.fromTo(
        "#fixtureOverlay",
        { opacity: 0, y: -10 },
        { opacity: 1, y: 0, duration: 0.5, ease: ENTER },
        evidenceIn + 0.4,
      );
      SFX.pops.push(evidenceIn + 0.45);
    }
    const entryHead = {
      x: entry.x,
      y: entry.y,
      w: entry.w,
      h: quote.y + quote.h - entry.y,
    };
    move(
      evidencePlate,
      fit(entryHead, evidence, { pad: 40, maxScale: 1.5 }),
      at("report-2", liveChecked ? 0.2 : 0.7),
      1.2,
    );
    move(
      evidencePlate,
      fit(quote, evidence, { pad: 50, maxScale: 2.05 }),
      cueAt["report-3"] + 0.1,
      1.0,
    );
    SFX.chimes.push(cueAt["report-3"] + 0.9);
    move(
      evidencePlate,
      fit(table, evidence, { pad: 40, maxScale: 1.9 }),
      at("report-3", 0.36),
      1.0,
    );
    move(
      evidencePlate,
      fit(statistic, evidence, { pad: 60, maxScale: 2.1 }),
      cueAt["report-4"] - 0.3,
      1.0,
    );

    /* ---------- Benchmark: frozen first, then the drug set, then what is measured ---------- */
    const signalStart = cueAt["signal-1"] - 0.5;
    scene("#bench", benchStart, signalStart, 0.6);
    const bench = facts.benchmark;
    const benchHead = $("#benchHead");
    const swapHead = (element, text, time) => {
      if (time > 0)
        tl.to(
          element,
          { opacity: 0, y: -10, duration: 0.25, ease: "power2.in" },
          time - 0.3,
        );
      tl.set(element, { textContent: text }, time);
      tl.fromTo(
        element,
        { opacity: 0, y: 24 },
        { opacity: 1, y: 0, duration: 0.6, ease: ENTER },
        time,
      );
    };
    swapHead(benchHead, "Fixed before any scoring.", cueAt["bench-1"] + 0.1);
    $("#protocolFile").textContent =
      `benchmark/PROTOCOL.md · version ${bench.protocolVersion}`;
    $("#protocolStamp").textContent =
      "Every rule written down before the first scoring run, 17 Oct 2026";
    const rules = [
      ["Drugs chosen by a script, never by hand", " · benchmark/drug_set.py"],
      [
        "Label precision first, then report precision",
        " · clinical before laboratory",
      ],
      [
        `Lift over ${bench.shuffles} shuffled diseases`,
        ` · seed ${bench.seed}`,
      ],
      ["Boxed-warning recall, and every miss classified", " · by script"],
    ];
    rules.forEach(([text, detail]) => {
      const item = document.createElement("li");
      item.innerHTML = `<div>${text}<span>${detail}</span></div>`;
      $("#protocolRules").appendChild(item);
    });
    enter("#benchProtocol", cueAt["bench-1"] + 0.5, 30);
    tl.fromTo(
      "#protocolRules li",
      { opacity: 0, y: 16 },
      { opacity: 1, y: 0, duration: 0.5, stagger: 0.28, ease: ENTER },
      cueAt["bench-1"] + 0.9,
    );
    SFX.pops.push(cueAt["bench-1"] + 0.55);
    leave("#benchProtocol", cueAt["bench-2"] - 0.35);

    swapHead(benchHead, "Picked by a script.", cueAt["bench-2"]);
    const funnelSteps = [
      [
        bench.funnel.step1_genes_kept,
        "catalog genes with a disease of known direction",
      ],
      [
        bench.funnel.step2_records_kept,
        "ChEMBL mechanisms on one human protein, approved drugs",
      ],
      [
        bench.funnel.step3_molecules_kept,
        "molecules that push the protein the disease’s way",
      ],
      [bench.funnel.step4_drugs_kept, "with an FDA label: the drug set"],
    ];
    const counters = [];
    funnelSteps.forEach(([count, label], index) => {
      const step = document.createElement("div");
      step.className = "funnel-step";
      step.innerHTML = `<div class="funnel-number">0</div><div class="funnel-label">${label}</div>`;
      $("#benchFunnel").appendChild(step);
      const start = cueAt["bench-2"] + 0.4 + index * spoken("bench-2") * 0.16;
      tl.fromTo(
        step,
        { opacity: 0, y: 24 },
        { opacity: 1, y: 0, duration: 0.6, ease: ENTER },
        start,
      );
      counters.push({
        element: step.querySelector(".funnel-number"),
        target: count,
        start,
      });
    });
    const funnelFoot = document.createElement("div");
    funnelFoot.className = "funnel-foot";
    funnelFoot.textContent = `${bench.funnel.drugs_with_boxed_warning} of the ${bench.drugCount} carry a boxed warning · benchmark/drug_set.json, protocol version ${bench.drugSetVersion}`;
    $("#bench").appendChild(funnelFoot);
    enter(funnelFoot, endOf("bench-2") - 0.6, 14);
    updaters.push((t) => {
      for (const counter of counters) {
        const share = clamp((t - counter.start) / 1.0);
        counter.element.textContent = Math.round(
          counter.target * (1 - (1 - share) ** 3),
        ).toLocaleString("en-US");
      }
    });
    leave(["#benchFunnel", funnelFoot], cueAt["bench-3"] - 0.35);

    swapHead(
      benchHead,
      status.benchmark ? "Measured." : "Not measured yet.",
      cueAt["bench-3"],
    );
    const measured = status.benchmark;
    const measureRows = [
      ["Label precision, clinical", measured ? bench.labelPrecision : null],
      [
        "Shuffled diseases, same measure",
        measured ? bench.shuffleLabelPrecision : null,
      ],
      ["Report precision, clinical", measured ? bench.reportPrecision : null],
      [
        "Boxed warnings predicted",
        measured && bench.boxedPredicted != null
          ? `${bench.boxedPredicted} of ${bench.boxedTotal}`
          : null,
      ],
      [
        "Candidate new signals",
        measured && bench.candidateCount != null
          ? String(bench.candidateCount)
          : null,
      ],
    ];
    measureRows.forEach(([label, value]) => {
      const row = document.createElement("div");
      row.className = "measures-row";
      row.innerHTML = `<span>${label}</span><span class="measure-value${value ? " measured" : ""}">${value ?? "not measured"}</span>`;
      $("#measuresRows").appendChild(row);
    });
    $("#measuresTag").textContent = measured ? "Scored" : "Pending";
    if (measured) $("#measuresTag").style.borderStyle = "solid";
    $("#measuresNote").textContent = measured
      ? `benchmark/results/results.json, protocol version ${bench.resultsVersion}`
      : "Blocked on step 5: no symptom is mapped to report terms until the Gemini key is set. No value here is estimated or filled in by hand.";
    enter("#benchMeasures", cueAt["bench-3"] + 0.3, 24);
    tl.fromTo(
      "#measuresRows .measures-row",
      { opacity: 0, y: 14 },
      { opacity: 1, y: 0, duration: 0.45, stagger: 0.18, ease: ENTER },
      cueAt["bench-3"] + 0.5,
    );
    enter("#measuresNote", at("bench-3", 0.62), 12);
    SFX.pops.push(cueAt["bench-3"] + 0.35);

    /* ---------- Signal: no prediction without evidence, and what a candidate new signal is ---------- */
    const watchStart = cueAt["watch-1"] - 0.5;
    scene("#signal", signalStart, watchStart, 0.6);
    const signalHead = $("#signalHead");
    const signalSub = $("#signalSub");
    const caveats = [
      ["Reports are voluntary and uneven.", " Counts are not incidence."],
      ["A boxed warning raises reporting", " of the effect it warns about."],
      ["The disease being treated", " may cause the effect too."],
    ];
    caveats.forEach(([lead, rest]) => {
      const item = document.createElement("li");
      item.innerHTML = `<b>${lead}</b>${rest}`;
      $("#candidateCaveats").appendChild(item);
    });
    if (status.candidate && facts.candidate) {
      const candidate = facts.candidate;
      swapHead(signalHead, "A candidate new signal.", cueAt["signal-1"]);
      $("#signalTerminal").hidden = true;
      const ready = $("#candidateReady");
      ready.hidden = false;
      ready.innerHTML = `<div><b>${candidate.drug}</b> blocks ${candidate.target}.</div><div>People born without it get <b>${candidate.disease}</b>, with ${candidate.phenotype}.</div><div>Reports: ${candidate.a} name ${candidate.term}, PRR ${candidate.prr}. Label: not mentioned.</div>`;
      tl.fromTo(
        ready.children,
        { opacity: 0, y: 20 },
        { opacity: 1, y: 0, duration: 0.6, stagger: 1.6, ease: ENTER },
        cueAt["signal-2"],
      );
      tl.to(ready, { opacity: 0, duration: 0.3 }, cueAt["signal-3"] + 3.5);
      tl.to(
        "#signalCandidate",
        { opacity: 1, duration: 0.5 },
        cueAt["signal-3"] + 3.8,
      );
      $("#signalPending").hidden = true;
    } else {
      swapHead(
        signalHead,
        "No prediction without its evidence.",
        cueAt["signal-1"],
      );
      signalSub.textContent = `Tiger Data store: TimescaleDB ${facts.timescaledb}, local container · faers_counts hypertable · faers_trend continuous aggregate`;
      enter(signalSub, cueAt["signal-1"] + 0.6, 14);
      $("#signalRunAt").textContent =
        "db/demo_trigger.sql · 17 Oct 2026, local";
      const signalBody = $("#signalBody");
      const triggerLines = [
        {
          kind: "prompt",
          text: "docker compose exec -T timescaledb psql -U knockout -d knockout -f db/demo_trigger.sql",
        },
        ...facts.trigger.map((line) => ({
          kind: /ERROR|HINT/.test(line) ? "error" : "log",
          text: line.replace(/^psql:\/tmp\/demo\.sql:\d+: /, ""),
        })),
      ];
      const triggerElements = triggerLines.map((line) => {
        const element = document.createElement("div");
        element.className = `line ${line.kind}`;
        element.textContent = line.text;
        signalBody.appendChild(element);
        return element;
      });
      const errorAt = triggerLines.findIndex((line) => /ERROR/.test(line.text));
      const secondPart = triggerLines.findIndex((line) =>
        /^2\./.test(line.text),
      );
      enter("#signalTerminal", cueAt["signal-1"] + 0.4, 24);
      tl.set(triggerElements[0], { opacity: 1 }, cueAt["signal-1"] + 0.6);
      wipe(triggerElements[0], cueAt["signal-1"] + 0.7, 1.6);
      triggerElements
        .slice(1, errorAt)
        .forEach((element, index) =>
          tl.to(
            element,
            { opacity: 1, duration: 0.1 },
            cueAt["signal-1"] + 2.5 + index * 0.18,
          ),
        );
      triggerElements
        .slice(errorAt, secondPart)
        .forEach((element, index) =>
          tl.to(
            element,
            { opacity: 1, duration: 0.15 },
            cueAt["signal-2"] + 0.5 + index * 0.25,
          ),
        );
      triggerElements
        .slice(1, errorAt)
        .forEach((element) =>
          tl.to(
            element,
            { opacity: 0.4, duration: 0.4 },
            cueAt["signal-2"] + 0.5,
          ),
        );
      if (triggerElements[errorAt])
        tl.set(
          triggerElements[errorAt],
          { attr: { class: "line error mark" } },
          cueAt["signal-2"] + 0.5,
        );
      triggerElements
        .slice(secondPart)
        .forEach((element, index) =>
          tl.to(
            element,
            { opacity: 0.55, duration: 0.1 },
            at("signal-2", 0.75) + index * 0.08,
          ),
        );
      SFX.pops.push(cueAt["signal-2"] + 0.55);

      leave("#signalTerminal", cueAt["signal-3"] - 0.1, 0.35);
      leave(signalSub, cueAt["signal-3"] - 0.1, 0.3);
      swapHead(signalHead, "Candidate new signals.", cueAt["signal-3"] + 0.25);
      tl.to(
        "#signalCandidate",
        { opacity: 1, duration: 0.01 },
        cueAt["signal-3"] + 0.3,
      );
      tl.fromTo(
        ".candidate-rule",
        { opacity: 0, y: 20 },
        { opacity: 1, y: 0, duration: 0.6, ease: ENTER },
        cueAt["signal-3"] + 0.4,
      );
      tl.fromTo(
        "#candidateCaveats li",
        { opacity: 0, y: 14 },
        { opacity: 1, y: 0, duration: 0.5, stagger: 0.3, ease: ENTER },
        at("signal-3", 0.55),
      );
      html(
        "#signalPendingBody",
        "None is shown yet: candidates come out of scoring, which waits on the mapping step. After scoring, a person picks one in <b>stage/status.json</b> and the video is re-rendered.",
      );
      enter("#signalPending", endOf("signal-3") - 0.2, 24);
      SFX.pops.push(endOf("signal-3"));
    }

    /* ---------- Watch: the watch agent's counts, and the trend the page draws from them ---------- */
    const closeStart = cueAt["new"] - 0.5;
    scene("#watch", watchStart, closeStart, 0.6);
    const watch = facts.watch;
    $("#watchRunAt").textContent =
      `${watch.runId.replace(/^manual-/, "manual · ")}`;
    const watchBody = $("#watchBody");
    const watchLines = [
      {
        kind: "prompt",
        text: `python creao/watch.py --dry-run --drug eculizumab --term "${watch.term}"`,
      },
      {
        kind: "log",
        text: `run ${watch.runId}: 1 drug(s), quarters ${watch.first} to ${watch.last}`,
      },
      { kind: "log", text: `term_source: ${watch.termSource}` },
      { kind: "blank", text: "" },
      { kind: "dim", text: "quarter   reports    PRR   signal" },
      ...watch.quarters.map((row) => ({
        kind: "reply",
        text: `${row.quarter}    ${String(row.reports).padStart(4)}    ${String(row.prr).padStart(5)}   ${row.signal ? "yes" : "no"}`,
      })),
      { kind: "blank", text: "" },
      {
        kind: "dim",
        text: `${watch.requests} openFDA requests, ${watch.seconds} s, ${watch.openfdaKey ? "with a key" : "no key"}`,
      },
      { kind: "dim", text: `openFDA data to ${watch.openfdaUpdated}` },
    ];
    const watchElements = watchLines.map((line) => {
      const element = document.createElement("div");
      element.className = `line ${line.kind}`;
      element.textContent = line.text;
      watchBody.appendChild(element);
      return element;
    });
    enter("#watchTerminal", watchStart + 0.25, 24);
    tl.set(watchElements[0], { opacity: 1 }, cueAt["watch-1"] + 0.1);
    wipe(watchElements[0], cueAt["watch-1"] + 0.2, 1.5);
    watchElements
      .slice(1)
      .forEach((element, index) =>
        tl.to(
          element,
          { opacity: 1, duration: 0.12 },
          cueAt["watch-1"] + 1.9 + index * 0.22,
        ),
      );
    $("#watchImage").src = `../capture/raw/${live.file}`;
    await decodeAll([$("#watchImage")]);
    const monitor = live.rects.monitoringSection[0];
    const monitorBody = {
      x: 400,
      y: monitor.y + 20,
      w: 880,
      h: monitor.h - 10,
    };
    const WATCH_WIDTH = 1020;
    const WATCH_HEIGHT = 560 - 44;
    const watchFit = (rect, maxScale) => {
      const scale = Math.min(
        WATCH_WIDTH / rect.w,
        WATCH_HEIGHT / rect.h,
        maxScale,
      );
      return {
        x: WATCH_WIDTH / 2 - (rect.x + rect.w / 2) * scale,
        y: WATCH_HEIGHT / 2 - (rect.y + rect.h / 2) * scale,
        scale,
      };
    };
    gsap.set("#watchPlate", {
      transformOrigin: "0 0",
      ...watchFit(monitorBody, 1.2),
    });
    enter("#watchBrowser", at("watch-1", 0.3), 24);
    SFX.pops.push(at("watch-1", 0.3) + 0.1);
    const trendRect = live.rects.trend[0];
    tl.to(
      "#watchPlate",
      {
        ...watchFit(
          {
            x: trendRect.x - 20,
            y: trendRect.y - 20,
            w: trendRect.w + 260,
            h: trendRect.h + 40,
          },
          1.9,
        ),
        duration: 1.1,
        ease: MOVE,
      },
      cueAt["watch-2"] + 0.1,
    );
    if (status.creao && watch.footage) {
      $("#watchPending").hidden = true;
      const frame = $("#creaoFrame");
      frame.hidden = false;
      enter(frame, at("watch-2", 0.4), 24);
      if (/\.(png|jpe?g)$/.test(watch.footage))
        $("#creaoImage").src = `../capture/raw/${watch.footage}`;
      else
        footagePlayer(
          $("#creaoImage"),
          "footage/creao-run",
          at("watch-2", 0.4),
          closeStart,
        );
    } else {
      html(
        "#watchPendingBody",
        "Needs the agent built on agent.creao.ai from <b>creao/AGENT.md</b>, posting to a public API. Shown: the same script on a laptop, live openFDA counts, the term chosen by hand.",
      );
      enter("#watchPending", at("watch-2", 0.45), 24);
      SFX.pops.push(at("watch-2", 0.45) + 0.1);
    }

    /* ---------- Close: what is new, the limits, the line ---------- */
    scene("#close", closeStart, END, 0.75, 0.9, "push");
    SFX.whooshes.push(closeStart + 0.35);
    const built = [
      "Drug → protein → disease pipeline and the direction rule",
      "Orphanet product 6 as a direction source",
      "Frequency filter and the Gemini symptom mapping",
      "Verbatim label check and the FAERS signal test",
      "Five Fetch.ai agents and the Creao watch agent",
      "API, Tiger Data store and its evidence trigger",
      "The report page and the frozen benchmark",
    ];
    const helix = [
      `IUIS catalog: ${facts.catalog.diseases} diseases, ${facts.catalog.genes} genes`,
      "<code>resolve_mechanism</code>: a disease’s direction",
      "<code>molecule_effect</code>: action type to lowers or raises",
    ];
    built.forEach((text) => {
      const item = document.createElement("li");
      item.textContent = text;
      $("#builtNew").appendChild(item);
    });
    helix.forEach((text) => {
      const item = document.createElement("li");
      item.innerHTML = text;
      $("#builtHelix").appendChild(item);
    });
    enter(
      "#closeBuilt .built-column:first-child .built-title",
      cueAt["new"],
      20,
    );
    tl.fromTo(
      "#builtNew li",
      { opacity: 0, y: 14 },
      { opacity: 1, y: 0, duration: 0.45, stagger: 0.32, ease: ENTER },
      cueAt["new"] + 0.5,
    );
    enter(".built-helix", cueAt["new"] + 0.4, 20);
    tl.fromTo(
      "#builtHelix li",
      { opacity: 0, y: 14 },
      { opacity: 1, y: 0, duration: 0.45, stagger: 0.25, ease: ENTER },
      cueAt["new"] + 0.9,
    );
    leave("#closeBuilt", cueAt["limits"] - 0.35, 0.3);
    const limits = [
      "FAERS reports are voluntary and uneven; counts are not incidence.",
      "A boxed warning raises reporting of the effect it warns about.",
      "Infections may come from the disease being treated, not the drug.",
    ];
    limits.forEach((text) => {
      const item = document.createElement("li");
      item.textContent = text;
      $("#limitsList").appendChild(item);
    });
    enter(".limits-head", cueAt["limits"], 24);
    tl.fromTo(
      "#limitsList li",
      { opacity: 0, y: 14 },
      { opacity: 1, y: 0, duration: 0.45, stagger: 0.3, ease: ENTER },
      cueAt["limits"] + 0.9,
    );
    leave("#closeLimits", cueAt["close"] - 0.4, 0.3);
    enter("#closeWord", cueAt["close"] - 0.05, 26, 0.8);
    enter("#closeTag", cueAt["close"] + 0.4, 18);
    tl.fromTo(
      "#closeCredits",
      { opacity: 0 },
      { opacity: 1, duration: 0.8 },
      cueAt["close"] + 1.4,
    );
    SFX.chimes.push(cueAt["close"] + 0.05);

    /* Clear each outgoing scene's type just before the next one dissolves in, so text never double-exposes. */
    for (const [selector, end] of [
      ["#hook .hook-grid", titleStart],
      ["#method", agentsStart],
      ["#report", benchStart],
      ["#bench", signalStart],
      ["#signal", watchStart],
    ]) {
      tl.to(
        `${selector} > *`,
        { opacity: 0, duration: 0.25, ease: "power1.in" },
        end - 0.15,
      );
    }

    /* Captions turn dark over the paper scenes. */
    const lightRanges = [[methodStart, closeStart + 0.4]];
    const captions = timedCaptions(cues, durations, captionTiming);
    buildCaptions(captions.cues, captions.durations, lightRanges);
    if (presenter) buildPresenter(presenter, [[0.4, END - 1.5]]);
  },
);

/* Plays a frame sequence (stage/footage/<folder>/00001.jpg at 30 fps) into an image between two stage times. */
function footagePlayer(image, folder, start, end, fps = 30) {
  updaters.push((t) => {
    if (t < start || t > end) return;
    const frame = Math.max(1, Math.round((t - start) * fps) + 1);
    const source = `${folder}/${String(frame).padStart(5, "0")}.jpg`;
    if (image.getAttribute("src") !== source) {
      image.setAttribute("src", source);
      pending.push(image.decode().catch(() => {}));
    }
  });
}
