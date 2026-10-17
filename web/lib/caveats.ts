import type { Prediction } from "./types";

export const CAVEATS = [
  {
    key: "voluntary",
    short: "Counts are not incidence.",
    text: "FAERS reports are voluntary and uneven, and counts are not incidence.",
  },
  {
    key: "circular",
    short: "The warning itself raises reporting.",
    text: "A boxed warning increases reporting of the reaction it warns about, so a report signal for a labelled effect is partly circular.",
  },
  {
    key: "indication",
    short: "Infections may come from the disease being treated.",
    text: "Patients taking immune drugs have immune diseases, so an infection report may come from the disease rather than the drug.",
  },
  {
    key: "milder",
    short: "A drug is a partial knockout.",
    text: "A lifelong genetic loss is stronger than partial inhibition by a drug, so a predicted effect may be milder or absent.",
  },
  {
    key: "matching",
    short: "Not every report names the drug the same way.",
    text: "The drug match on generic name relies on openFDA's harmonised fields, which not every report has.",
  },
  {
    key: "mapping",
    short: "The reaction terms are a model's mapping.",
    text: "The mapping from phenotype to reaction terms (step 5) is a model output; the protocol has a team member check a sample of 50.",
  },
] as const;

export type CaveatKey = (typeof CAVEATS)[number]["key"];

const INFECTION = /infect|sepsis|septic|mening|pneumon|abscess|candid|herpes|zoster|tubercul|bacter|viral|fung/i;

export function caveatsFor(prediction: Prediction) {
  const keys = new Set<CaveatKey>(["milder"]);
  if (prediction.reaction_terms.length) keys.add("mapping");
  if (prediction.counts.length) {
    keys.add("voluntary");
    keys.add("matching");
  }
  if (prediction.label_section && prediction.counts.some((count) => count.signal)) keys.add("circular");
  if (INFECTION.test(prediction.phenotype) || prediction.reaction_terms.some((term) => INFECTION.test(term))) {
    keys.add("indication");
  }
  return CAVEATS.filter((caveat) => keys.has(caveat.key));
}
