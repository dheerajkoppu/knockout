// Gathers every fact the video shows into stage/data/facts.json, read from what was captured and from the
// repository, so no number on screen is typed by hand. It also decides which beats are real yet.
// node capture/facts.mjs
import fs from "node:fs";
import path from "node:path";
import { root, readJson } from "../lib/project.mjs";

const repository = path.resolve(root, "..");
const raw = path.join(root, "capture", "raw");
const readRaw = (name, fallback = null) => {
  const file = path.join(raw, name);
  if (!fs.existsSync(file)) return fallback;
  return name.endsWith(".json") ? JSON.parse(fs.readFileSync(file, "utf8")) : fs.readFileSync(file, "utf8");
};
const readRepository = (relative, fallback = null) => {
  const file = path.join(repository, relative);
  return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : fallback;
};
const firstExisting = (...names) => names.find((name) => fs.existsSync(path.join(raw, name))) ?? null;
const NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];
const words = (count) => NUMBER_WORDS[count] ?? count.toLocaleString("en-US");
const grouped = (count) => (count ?? 0).toLocaleString("en-US");
const titleCase = (text) => text.replace(/\b\w/g, (letter) => letter.toUpperCase());

const pages = readRaw("pages.json", {});
const report = pages.api?.eculizumab ?? {};
const handcheck = readRaw("handcheck.json", {});
const target = report.targets?.find((row) => row.used) ?? {};
const disease = report.diseases?.find((row) => row.pairing === "use") ?? {};
const meningococcal = report.predictions?.find((row) => row.hpo_id === "HP:0005381") ?? {};
const catalogRecord = meningococcal.records?.find((record) => record.source === "iuis_2024");
const omimRecord = meningococcal.records?.find((record) => record.source === "hpo_annotations" && /OMIM/.test(record.description));
const effective = (stamp) => (stamp ? new Date(`${stamp.slice(0, 4)}-${stamp.slice(4, 6)}-${stamp.slice(6, 8)}T12:00:00Z`) : null);
const longDate = (date) => date?.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) ?? "";

/* The agents' one local chat: their log lines, then the reply. */
const askText = readRaw("agents-ask.txt", "");
const askLines = askText.split("\n");
const agentEvents = askLines
  .map((line) => line.match(/^INFO:\s+\[([\w-]+)\]: (.*)$/))
  .filter(Boolean)
  .map(([, agent, message]) => ({ agent, message }))
  .filter(({ message }) => /request from|slice for|: ok|: unknown/.test(message));
const replyStart = askLines.findIndex((line) => /^ChEMBL lists|^\*\*/.test(line));
const cardStart = askLines.findIndex((line) => line.startsWith("[Interactive Card"));
const reply = askLines.slice(replyStart, cardStart > 0 ? cardStart : undefined).filter((line) => !/^INFO:|^WARNING:/.test(line));
const listed = reply[0]?.match(/ChEMBL lists (\d+) approved drugs/);
const others = reply[0]?.match(/Others: (.*)\.\s*$/)?.[1]?.split(", ") ?? [];
const chosen = reply[0]?.match(/here is \*\*(.+?)\*\*/)?.[1] ?? "";
const agentStatus = reply.find((line) => line.startsWith("Agents:")) ?? "";
const statusOf = (agent) => agentStatus.match(new RegExp(`${agent} (\\w+)`))?.[1] ?? "unknown";
let card = null;
if (cardStart > 0) {
  const json = askLines.slice(cardStart + 1).join("\n");
  const end = json.lastIndexOf("}\n");
  try {
    card = JSON.parse(json.slice(0, json.indexOf("\nINFO:") > 0 ? json.indexOf("\nINFO:") : end + 1));
  } catch {
    card = null;
  }
}
const cardButtons = [];
JSON.stringify(card ?? {}, (key, value) => {
  if (value && value.type === "button") cardButtons.push(value.label);
  return value;
});

/* The watch agent's run, and the trend the API serves from its posts. */
const watchText = readRaw("watch-dry-run.txt", "");
const watchSummary = readRaw("watch-dry-run.json", {});
const watchStamps = watchText.match(/^\d{4}-\d\d-\d\dT[\d:]+Z$/gm) ?? [];
const watchRows = watchSummary.drugs?.[0]?.rows ?? [];
const latestRow = watchRows.at(-1) ?? {};
const trend = pages.api?.trend ?? {};
const trendTerm = trend.terms?.[0] ?? {};

/* The benchmark: the frozen protocol, the drug set and whatever the scorer has measured. */
const drugSet = readRepository("benchmark/drug_set.json", {});
const results = readRepository("benchmark/results/results.json", {});
const protocolText = fs.existsSync(path.join(repository, "benchmark/PROTOCOL.md")) ? fs.readFileSync(path.join(repository, "benchmark/PROTOCOL.md"), "utf8") : "";
const protocolVersion = Number(protocolText.match(/^# Benchmark protocol, version (\d+)/m)?.[1] ?? 0);
const resultsCurrent = results.protocol_version === drugSet.protocol_version;
const measures = results.measures ?? {};
const scored = Boolean(resultsCurrent && results.status?.complete);

/* Which beats are real yet. stage/status.json can force any of them either way. */
const overrides = readJson("stage/status.json", {});
const mapped = (report.predictions ?? []).some((row) => (row.reaction_terms ?? []).length > 0);
const asiOneFootage = firstExisting("asi-one.mp4", "asi-one.mov");
const creaoFootage = firstExisting("creao-run.mp4", "creao-run.mov", "creao-run.png", "creao-run.jpg");
const decide = (name, automatic) => (overrides[name] === "ready" ? true : overrides[name] === "pending" ? false : automatic);
// The meningococcal prediction is the example the report scene points at; it is real only on the live page.
const livePage = pages.eculizumab ?? {};
const meningococcalEntry = (livePage.rects?.entries ?? []).find((row) => /HP0005381/.test(row.id ?? ""));
const inside = (rect, outer) => outer && rect.y >= outer.y && rect.y < outer.y + outer.h;
const meningococcalQuote = (livePage.rects?.labelQuote ?? []).some((rect) => inside(rect, meningococcalEntry));
const meningococcalCount = (meningococcal.counts ?? []).find((count) => count.signal) ?? (meningococcal.counts ?? [])[0] ?? null;
const status = {
  mapping: decide("mapping", mapped),
  meningococcalOnLabel: decide("meningococcalOnLabel", mapped && meningococcal.verdict === "on_label" && meningococcalQuote),
  mappingWithoutMeningococcal: mapped && !(meningococcal.verdict === "on_label" && meningococcalQuote) && overrides.meningococcalOnLabel !== "ready",
  // A beat shown from footage can be forced pending, never ready without its footage.
  asiOne: Boolean(asiOneFootage) && decide("asiOne", true),
  benchmark: decide("benchmark", scored),
  candidate: decide("candidate", Boolean(overrides.candidateChoice && scored)),
  creao: Boolean(creaoFootage) && decide("creao", trendTerm.source !== "manual"),
  watchFromReport: (watchSummary.term_source ?? trendTerm.source) === "report",
};

const candidateChoice = overrides.candidateChoice ?? null;
// Scored reports are written per ChEMBL id by benchmark/score.py; the person's choice names the drug.
const scoredDirectory = path.join(repository, "benchmark", "results", "reports");
const candidateReport = candidateChoice && fs.existsSync(scoredDirectory)
  ? fs
      .readdirSync(scoredDirectory)
      .filter((name) => name.endsWith(".json"))
      .map((name) => JSON.parse(fs.readFileSync(path.join(scoredDirectory, name), "utf8")))
      .find((scoredReport) => [scoredReport.molecule?.name, scoredReport.molecule?.chembl_id, scoredReport.query].some((value) => value && value.toLowerCase() === candidateChoice.drug.toLowerCase())) ?? null
  : null;
const candidatePrediction = candidateReport?.predictions?.find((row) => row.hpo_id === candidateChoice.hpo_id) ?? null;
const candidateCount = candidatePrediction?.counts?.find((count) => count.signal) ?? null;

const percent = (value) => (value == null ? null : `${Math.round(value * 100)}%`);
const measure = (key) => measures[key] ?? null;

const facts = {
  generatedAt: new Date().toISOString(),
  capturedAt: pages.api?.capturedAt ?? null,
  status,
  hook: {
    gene: target.gene ?? "C5",
    protein: target.name ?? "Complement C5",
    accession: target.accession ?? "",
    action: target.action_types?.[0] ?? "",
    effect: target.effect ?? "",
    drug: report.molecule?.name ?? "Eculizumab",
    chemblId: report.molecule?.chembl_id ?? "",
    disease: disease.name ?? "C5 deficiency",
    directionSource: disease.direction_source ?? "",
    phenotype: meningococcal.phenotype ?? "",
    hpoId: meningococcal.hpo_id ?? "",
    frequency: meningococcal.frequency ?? "",
    catalogRecord: catalogRecord?.description ?? "",
    omim: omimRecord?.description?.replace("Catalog record ", "") ?? "",
  },
  label: {
    setId: handcheck.label?.set_id ?? report.label?.set_id ?? "",
    effective: longDate(effective(handcheck.label?.effective_time ?? report.label?.effective_time)),
    section: handcheck.label?.section ?? "",
    sentence: handcheck.label?.sentence ?? "",
    title: handcheck.label?.sentence?.match(/^WARNING: [A-Z ]+?(?= [A-Z][a-z]| SOLIRIS|$)/)?.[0] ?? "WARNING: SERIOUS MENINGOCOCCAL INFECTIONS",
  },
  handcheck: {
    checkedAt: handcheck.checked_at ?? null,
    term: handcheck.term ?? "",
    a: grouped(handcheck.counts?.a),
    drug: grouped(handcheck.counts?.drug),
    reaction: grouped(handcheck.counts?.reaction),
    all: grouped(handcheck.counts?.all),
    b: grouped((handcheck.counts?.drug ?? 0) - (handcheck.counts?.a ?? 0)),
    c: grouped((handcheck.counts?.reaction ?? 0) - (handcheck.counts?.a ?? 0)),
    d: grouped((handcheck.counts?.all ?? 0) - (handcheck.counts?.drug ?? 0) - ((handcheck.counts?.reaction ?? 0) - (handcheck.counts?.a ?? 0))),
    prr: Math.round(handcheck.counts?.prr ?? 0),
    prrExact: handcheck.counts?.prr ?? null,
    chiSquared: grouped(Math.round(handcheck.counts?.chi_squared ?? 0)),
    expected: handcheck.counts?.expected ?? null,
    signal: handcheck.counts?.signal ?? false,
    allMillions: Math.round((handcheck.counts?.all ?? 0) / 1e6),
    allMillionsText: ((handcheck.counts?.all ?? 0) / 1e6).toFixed(1),
  },
  report: {
    predictionCount: report.predictions?.length ?? 0,
    predictionCountWords: words(report.predictions?.length ?? 0),
    checkedCount: (report.predictions ?? []).filter((row) => row.verdict !== "unknown").length,
    drugReports: grouped(report.drug_reports),
    allReports: grouped(report.all_reports),
    problems: report.problems ?? [],
    store: pages.api?.health?.store ?? "",
    geminiKey: pages.api?.health?.gemini_key ?? false,
    sourceState: pages.eculizumab?.sourceState ?? "",
  },
  agents: {
    question: "What side effects should a C5 blocker cause?",
    drugCount: listed ? Number(listed[1]) : 0,
    drugCountWords: words(listed ? Number(listed[1]) : 0),
    chosen,
    chosenName: chosen.toLowerCase(),
    others,
    events: agentEvents,
    reply,
    statusLine: agentStatus,
    target: statusOf("target-agent"),
    genetics: statusOf("genetics-agent"),
    labelAgent: statusOf("label-agent"),
    signal: statusOf("signal-agent"),
    cardButtons,
    ranAt: readRaw("agents-ask.started", "").trim(),
  },
  watch: {
    runId: watchSummary.run_id ?? "",
    termSource: watchSummary.term_source ?? trendTerm.source ?? "",
    term: watchRows[0]?.term ?? trendTerm.term ?? "",
    quarters: watchRows.map((row) => ({ quarter: row.quarter, reports: row.reports, prr: Math.round(row.prr ?? 0), signal: row.signal })),
    quarterCount: watchRows.length,
    quarterCountWords: words(watchRows.length),
    first: watchSummary.quarters?.[0] ?? "",
    last: watchSummary.quarters?.at(-1) ?? "",
    latestPrr: Math.round(latestRow.prr ?? 0),
    latestSignal: latestRow.signal ?? false,
    requests: watchSummary.openfda_requests ?? 0,
    openfdaKey: watchSummary.openfda_key ?? false,
    seconds: watchStamps.length === 2 ? Math.round((Date.parse(watchStamps[1]) - Date.parse(watchStamps[0])) / 1000) : null,
    openfdaUpdated: watchSummary.openfda_last_updated ?? "",
    apiLastRun: trend.last_run_at ?? "",
    apiTermSource: trendTerm.source ?? "",
    footage: creaoFootage,
  },
  meningococcal: meningococcalCount
    ? {
        verdict: meningococcal.verdict,
        term: meningococcalCount.term,
        a: grouped(meningococcalCount.a),
        drug: grouped(meningococcalCount.drug),
        reaction: grouped(meningococcalCount.reaction),
        allMillionsText: ((meningococcalCount.all ?? 0) / 1e6).toFixed(1),
        prr: meningococcalCount.prr == null ? null : Math.round(meningococcalCount.prr),
        labelSection: meningococcal.label_section,
      }
    : null,
  trigger: readRaw("trigger.txt", "").trim().split("\n"),
  timescaledb: readRaw("timescaledb-version.txt", "").trim(),
  benchmark: {
    protocolVersion,
    drugSetVersion: drugSet.protocol_version ?? null,
    drugCount: drugSet.drugs?.length ?? 0,
    funnel: drugSet.counts ?? {},
    resultsVersion: results.protocol_version ?? null,
    resultsCurrent,
    scored,
    blocked: results.status?.blocked ?? (resultsCurrent ? null : "results.json was scored under an older protocol version"),
    labelPrecision: percent(measure("label_precision")?.clinical?.value),
    labelPrecisionCounts: measure("label_precision")?.clinical ?? null,
    reportPrecision: percent(measure("report_precision")?.clinical?.with_on_label?.value),
    shuffleLabelPrecision: percent(measure("label_precision_lift")?.clinical?.shuffle_mean),
    lift: (() => {
      const lift = measure("label_precision_lift")?.clinical;
      return lift?.real != null && lift?.shuffle_mean ? +(lift.real / lift.shuffle_mean).toFixed(1) : null;
    })(),
    shareAtOrAbove: measure("label_precision_lift")?.clinical?.share_at_or_above ?? null,
    boxedPredicted: measure("boxed_warning_recall")?.any_kind?.numerator ?? null,
    boxedTotal: measure("boxed_warning_recall")?.any_kind?.denominator ?? drugSet.counts?.drugs_with_boxed_warning ?? null,
    candidateCount: Array.isArray(measure("candidate_new_signals")) ? measure("candidate_new_signals").length : measure("candidate_new_signals")?.count ?? null,
    shuffles: results.inputs?.shuffles ?? 100,
    seed: results.inputs?.seed ?? 20261017,
  },
  candidate: candidatePrediction
    ? {
        drug: titleCase(candidateReport.molecule?.name ?? candidateChoice.drug),
        target: candidatePrediction.target,
        gene: candidatePrediction.gene,
        disease: candidatePrediction.disease,
        phenotype: candidatePrediction.phenotype,
        term: candidateCount?.term ?? "",
        a: grouped(candidateCount?.a),
        prr: candidateCount?.prr == null ? "" : Math.round(candidateCount.prr),
      }
    : null,
  catalog: handcheck.catalog ?? null,
  ibrutinib: {
    predictionCount: pages.api?.ibrutinib?.predictions?.length ?? 0,
    target: pages.api?.ibrutinib?.targets?.find((row) => row.used)?.name ?? "",
    disease: pages.api?.ibrutinib?.diseases?.find((row) => row.pairing === "use")?.name ?? "",
  },
  footage: {
    asiOne: asiOneFootage,
    creao: creaoFootage,
  },
};

fs.writeFileSync(path.join(root, "stage", "data", "facts.json"), JSON.stringify(facts, null, 1) + "\n");
console.log("wrote stage/data/facts.json");
const beats = ["mapping", "meningococcalOnLabel", "asiOne", "benchmark", "candidate", "creao"];
console.log("beats real yet:", beats.map((name) => `${name} ${status[name] ? "ready" : "pending"}`).join(", "));
