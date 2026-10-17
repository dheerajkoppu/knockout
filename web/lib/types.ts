export type Effect = "lowers" | "raises" | "unknown";
export type Verdict =
  "on_label" | "signal_in_reports" | "no_signal" | "unknown";
export type Pairing = "use" | "points_the_other_way" | "unknown";

export interface Molecule {
  chembl_id: string;
  name: string;
  max_phase: number | null;
  molecule_type: string | null;
  url: string;
}

export interface Target {
  chembl_id: string;
  name: string;
  accession: string | null;
  effect: Effect | string;
  action_types: (string | null)[];
  gene: string | null;
  used: boolean;
  reason: string | null;
}

export interface Disease {
  disease_id: string;
  name: string;
  gene: string;
  direction: "decreased_activity" | "increased_activity" | "unknown" | string;
  direction_source: "iuis" | "orphanet" | "disease_name" | string | null;
  direction_basis: string;
  pairing: Pairing | string;
  phenotypes_used: number;
}

export interface TermCount {
  term: string;
  a: number;
  drug: number;
  reaction: number;
  all: number;
  prr: number | null;
  prr_infinite?: boolean;
  chi_squared: number;
  signal: boolean;
  expected: number;
  query: string;
}

export interface EvidenceRecord {
  source: string;
  description: string;
  url: string | null;
}

export interface Prediction {
  hpo_id: string;
  phenotype: string;
  frequency: string | null;
  kind: "clinical" | "laboratory" | "developmental" | string | null;
  gene: string;
  target: string;
  disease_id: string;
  disease: string;
  reaction_terms: string[];
  label_section: string | null;
  label_term: string | null;
  label_sentence: string | null;
  counts: TermCount[];
  verdict: Verdict;
  reason: string | null;
  candidate_new_signal: boolean;
  records: EvidenceRecord[];
}

export interface Label {
  set_id: string;
  effective_time: string;
  generic_names: string[];
  sections: string[];
  matched_by?: string;
  url: string;
}

export interface Report {
  query: string;
  generated_at: string;
  cached_at?: string | null;
  molecule: Molecule | null;
  targets: Target[];
  diseases: Disease[];
  predictions: Prediction[];
  excluded_developmental: { hpo_id: string; phenotype: string }[];
  /** Catalog symptoms of a used disease below the frequency threshold (protocol step 4). */
  excluded_by_frequency?: {
    hpo_id: string;
    phenotype: string;
    frequency: string | null;
    disease_id: string;
  }[];
  label: Label | null;
  drug_reports: number | null;
  all_reports: number | null;
  /** The oldest retrieval time among the label and the FAERS totals this report used. */
  openfda_retrieved_at?: string | null;
  problems: string[];
  _fixture?: { note: string; sources: string[] };
}

export interface TrendQuarter {
  quarter: string;
  /** FAERS reports with the drug and the term received during that quarter. */
  reports: number;
  /** PRR over every report received up to the end of the quarter. */
  prr?: number | null;
  prr_infinite?: boolean;
  signal?: boolean;
}

export interface Trend {
  drug: string;
  terms: {
    term: string;
    /** "manual" when a person chose the term for the watch agent (watch.py --term). */
    source?: "report" | "manual" | string;
    quarters: TrendQuarter[];
  }[];
  last_run_at: string | null;
}

export interface Alert {
  term: string;
  quarter: string;
  prr: number | null;
  prr_infinite?: boolean;
  crossed_at: string;
}

export interface Alerts {
  drug: string;
  alerts: Alert[];
}

export interface Health {
  status: string;
  gemini_key: boolean;
  openfda_key: boolean;
  store: "postgres" | "files" | string;
}
