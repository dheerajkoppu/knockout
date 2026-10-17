import type { Disease, Prediction, Target, TermCount, Verdict } from "./types";

const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export const formatCount = (value: number | null | undefined) =>
  value == null ? "–" : integer.format(value);

export function formatRatio(value: number | null | undefined): string {
  if (value == null) return "–";
  if (!Number.isFinite(value)) return "∞";
  if (value >= 100) return integer.format(value);
  if (value >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

/** A value next to a threshold, with enough decimals that it never rounds across the threshold. */
export function formatAgainst(
  value: number | null | undefined,
  threshold: number,
  format: (value: number) => string = formatRatio,
): string {
  if (value == null) return "–";
  if (!Number.isFinite(value)) return "∞";
  const consistent = (text: string) =>
    Number(text.replace(/,/g, "")) >= threshold === value >= threshold;
  let text = format(value);
  for (let digits = 2; digits <= 5 && !consistent(text); digits += 1)
    text = value.toFixed(digits);
  return text;
}

export function formatChiSquared(value: number): string {
  return value >= 1000 ? integer.format(value) : value.toFixed(1);
}

export function formatExpected(value: number): string {
  if (value >= 100) return integer.format(value);
  if (value >= 1) return value.toFixed(1);
  return value.toFixed(2);
}

export const VERDICTS: Record<
  Verdict,
  { label: string; short: string; meaning: string }
> = {
  on_label: {
    label: "On the label",
    short: "Label",
    meaning: "A sentence of the FDA label names one of its reaction terms.",
  },
  signal_in_reports: {
    label: "Signal in reports",
    short: "Reports",
    meaning: "Not on the label, but FAERS reports meet the Evans criteria.",
  },
  no_signal: {
    label: "No signal",
    short: "None",
    meaning:
      "Not on the label, and the reports do not meet the Evans criteria.",
  },
  unknown: {
    label: "Unknown",
    short: "Unknown",
    meaning:
      "Too few reports to tell, or a step could not run. Never read as safe.",
  },
};

export const SECTION_NAMES: Record<string, string> = {
  boxed_warning: "Boxed warning",
  warnings_and_cautions: "Warnings and precautions",
  warnings: "Warnings",
  precautions: "Precautions",
  adverse_reactions: "Adverse reactions",
};

export const DIRECTION_SOURCES: Record<string, string> = {
  iuis: "stated by IUIS",
  orphanet: "Orphanet gene association",
  disease_name: "read from the disease name",
};

export function effectVerb(effect: string): string {
  if (effect === "lowers") return "blocks";
  if (effect === "raises") return "activates";
  return "acts on";
}

export function directionPhrase(direction: string): string {
  if (direction === "decreased_activity") return "too little activity";
  if (direction === "increased_activity") return "too much activity";
  return "direction unknown";
}

export function actionTypes(target: Target): string {
  return (
    Array.from(new Set(target.action_types.filter(Boolean))).join(", ") ||
    "no action type"
  );
}

function frequencyParts(frequency: string) {
  const fraction = frequency.match(/^\s*(\d+)\s*\/\s*(\d+)\s*$/);
  if (fraction) return { cases: fraction[1], total: fraction[2] };
  const named = frequency.match(/^\s*([^(]+?)\s*(?:\((\d+)\s*-\s*(\d+)\s*%\))?\s*$/);
  if (!named) return { name: frequency };
  const [low, high] = [named[2], named[3]].map(Number).sort((left, right) => left - right);
  return { name: named[1].toLowerCase(), range: named[2] ? `${low}–${high}%` : undefined };
}

export function frequencyPhrase(frequency: string | null): string {
  if (!frequency) return "frequency not recorded";
  const parts = frequencyParts(frequency);
  if ("cases" in parts) return `${parts.cases}/${parts.total} cases`;
  return parts.range ? `${parts.name}, ${parts.range}` : parts.name;
}

export function frequencySentence(frequency: string | null): string {
  if (!frequency) return "the catalog records no frequency for this symptom";
  const parts = frequencyParts(frequency);
  if ("cases" in parts) return `this symptom is seen in ${parts.cases} of ${parts.total} reported cases`;
  if (parts.name === "obligate") return "this symptom is obligate, seen in every case";
  return parts.range
    ? `this symptom is ${parts.name}, seen in ${parts.range} of cases`
    : `this symptom is recorded as ${parts.name}`;
}

export function countRatio(count: TermCount): number | null {
  return count.prr_infinite ? Number.POSITIVE_INFINITY : count.prr;
}

export function strongestCount(counts: TermCount[]): TermCount | undefined {
  const ranked = [...counts].sort((left, right) => {
    if (left.signal !== right.signal) return left.signal ? -1 : 1;
    return (countRatio(right) ?? -1) - (countRatio(left) ?? -1);
  });
  return ranked[0];
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "–";
  const compact = value.match(/^(\d{4})(\d{2})(\d{2})$/);
  const date = compact
    ? new Date(`${compact[1]}-${compact[2]}-${compact[3]}T00:00:00Z`)
    : new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "–";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

export function relativeTime(
  value: string | null | undefined,
  now = Date.now(),
): string {
  if (!value) return "";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = Math.round((now - then) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

export function pluralize(
  count: number,
  singular: string,
  plural = `${singular}s`,
) {
  return `${formatCount(count)} ${count === 1 ? singular : plural}`;
}

export function titleCase(name: string): string {
  return name.replace(/\b\p{L}/gu, (letter) => letter.toUpperCase());
}

export function predictionAnchor(prediction: Prediction): string {
  return `effect-${prediction.disease_id}-${prediction.hpo_id.replace(":", "")}`;
}

export function verdictTally(
  predictions: Prediction[],
): Record<Verdict, number> {
  const tally: Record<Verdict, number> = {
    on_label: 0,
    signal_in_reports: 0,
    no_signal: 0,
    unknown: 0,
  };
  for (const prediction of predictions)
    tally[prediction.verdict] = (tally[prediction.verdict] ?? 0) + 1;
  return tally;
}

/** A check ran: the prediction has reaction terms and either the label or the FAERS counts were read. */
export function wasChecked(prediction: Prediction, labelFound: boolean): boolean {
  return (
    prediction.reaction_terms.length > 0 &&
    (labelFound || prediction.counts.length > 0 || Boolean(prediction.label_sentence))
  );
}

/** The engine's reason a target was not used, in words for a reader. */
export function targetReason(reason: string | null): string {
  if (!reason) return "none of its genetic diseases pairs with the drug's effect";
  const type = reason.match(/^target type is (.+), the protocol uses SINGLE PROTEIN only$/);
  if (type)
    return `ChEMBL records it as a ${type[1].toLowerCase()}, not a single protein, and the method needs one protein`;
  if (reason === "protein is not in the IUIS catalog")
    return "no inborn error of immunity in the IUIS catalog involves this protein";
  if (reason === "no disease of this protein pairs with the drug's effect")
    return "its genetic diseases push the protein the other way, or their direction is unknown";
  if (reason === "no single UniProt accession")
    return "ChEMBL gives it no single UniProt accession";
  return reason;
}

export function excludedDiseases(diseases: Disease[]): Disease[] {
  return diseases.filter((disease) => disease.pairing !== "use");
}
