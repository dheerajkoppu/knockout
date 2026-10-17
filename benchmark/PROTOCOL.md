# Benchmark protocol, version 1

Committed on 17 Oct 2026 before any scoring run. Every rule below is fixed. A change after the
first scoring run is a new version of this file, committed with the reason, and both versions'
results are reported.

## Question

When Knockout predicts a drug's side effects from the genetic diseases of the proteins it acts on,
how often does the FDA label or the FDA adverse-event record agree, and is that agreement higher
than for predictions taken from unrelated genetic diseases?

## The pipeline being measured

**1. Drug to targets.** ChEMBL mechanism records for the drug's parent molecule. Only targets of
type `SINGLE PROTEIN` with organism `Homo sapiens` are used, each resolved to its UniProt
accession. Each record's `action_type` is read with Helix's `molecule_effect()` (Helix commit
`97f3704`): `lowers`, `raises` or `unknown`. If two records for the same target disagree, the
effect is `unknown`.

**2. Targets to diseases.** The target's accession is looked up in the Helix IUIS catalog. Each of
the gene's diseases is taken separately, and its direction comes from the first of these that gives
one:

1. the IUIS mechanism stated in the catalog (Helix `resolve_mechanism()`, confidence
   `stated_in_the_catalog`);
2. Orphanet product 6 (release 2026-06-23): the association type for the disease's ORPHA code and
   this gene, when it names "loss of function" or "gain of function";
3. the words of the disease name (Helix `resolve_mechanism()`, confidence
   `named_in_the_disease_label`).

Otherwise the direction is unknown and the disease is not used.

**3. The direction rule.** A drug that `lowers` a protein uses only that protein's diseases with
decreased activity (loss of function, haploinsufficiency, dominant negative). A drug that `raises` a
protein uses only diseases with increased activity (gain of function). Every other pairing is not
used and is recorded as `points_the_other_way` or `unknown`.

**4. Diseases to phenotypes.** A phenotype is used when its catalog frequency is Obligate, Very
frequent or Frequent (with or without the percentage range), or a case fraction k/n with
k/n ≥ 0.30. A phenotype with no frequency, Occasional or Very rare is not used.

**5. Phenotypes to reaction terms.** Each HPO term is classified and mapped once by Gemini at
temperature 0. The prompt contains the HPO id and label only and never names a drug. The output, per
term, is:

- `kind`: `clinical`, `laboratory` or `developmental`;
- up to five MedDRA preferred terms for the same condition, as FAERS records reactions.

A proposed reaction term is kept only if FAERS holds at least one report with that exact reaction
term, counted across all drugs. The mappings are written to `data/mappings/hpo.json`, with the
model name and the time, and committed. Scored runs read only that file. Developmental phenotypes
are not used, because a drug given after birth cannot cause them.

**6. Label check.** The most recent openFDA label for the drug's generic name. The sections
`boxed_warning`, `warnings_and_cautions`, `warnings`, `precautions` and `adverse_reactions` are
searched. A prediction is on the label when a sentence contains one of its reaction terms as a whole
phrase, ignoring case, with the last word allowed to end in "s" or "es". The sentence and section
are recorded verbatim. No model takes part in this step.

**7. Report check.** openFDA `drug/event` totals, with the drug matched by the phrase query
`patient.drug.openfda.generic_name:"<name>"`, any role. For each reaction term:

- `a`: reports with the drug and the term; `drug`: reports with the drug;
  `term`: reports with the term; `all`: all reports.
- PRR = (a / drug) / ((term − a) / (all − drug)).
- Pearson chi-squared with Yates correction on the 2×2 table.
- A term is a signal when a ≥ 3, PRR ≥ 2 and chi-squared ≥ 4 (Evans criteria).

A prediction has a report signal when at least one of its terms is a signal.

**8. Verdict per prediction:**

| Verdict             | Rule                                                                                                                                                                       |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `on_label`          | Step 6 found a sentence                                                                                                                                                    |
| `signal_in_reports` | Not on the label, and step 7 found a signal                                                                                                                                |
| `unknown`           | Not on the label, no signal, and 2 × expected < 3 for every term, where expected = drug × term / all, so even a doubled rate could not reach 3 reports; or a source failed |
| `no_signal`         | Everything else                                                                                                                                                            |

A `signal_in_reports` prediction of kind `clinical` is a **candidate new signal**.

## Drug set

Generated by `benchmark/drug_set.py` and never edited by hand:

1. every catalog gene with a UniProt accession and at least one disease with a known direction;
2. every ChEMBL mechanism record on a `SINGLE PROTEIN`, `Homo sapiens` target with that accession,
   for a molecule at max phase 4;
3. kept when the effect is `lowers` and the gene has a decreased-activity disease, or `raises` and
   it has an increased-activity disease;
4. kept when openFDA holds a label for the molecule's generic name.

The resulting list, with the reason each drug is in it, is committed before scoring as
`benchmark/drug_set.json`.

## Measures

Reported in this order, for `clinical` and `laboratory` phenotypes separately, `clinical` first.

1. **Label precision:** predictions `on_label` ÷ all predictions.
2. **Report precision:** predictions with a report signal ÷ predictions not `unknown`.
3. **Lift over shuffled diseases**, for label precision: each drug's diseases are replaced by the same
   number of catalog diseases drawn at random from those with the same direction, excluding the drug's
   own target genes. 100 shuffles, seed 20261017. Reported as the real value, the shuffle mean and
   the share of shuffles at or above the real value.
4. **Lift over shuffled diseases, for report precision**, computed the same way with 100 shuffles, but
   both the real and the shuffled arm read `a` from the drug's 1,000 most-reported reaction terms
   (openFDA `count`), and a term outside them counts as no signal. This keeps the comparison fair and
   within the API's limits; the exact counts from step 7 are reported separately for the real arm.
5. **Boxed-warning recall:** among drugs in the set with a boxed warning, the share of boxed warnings
   that contain a sentence matched by at least one prediction.
6. **Candidate new signals:** the full list, each with its chain and counts.

## Classifying misses

Every prediction that is neither `on_label` nor a report signal is classified by a script, in this
order, into exactly one bucket: no reaction term survived step 5; the drug has fewer than 100 reports;
the verdict is `unknown`; none of the above. Every drug-set candidate dropped in steps 1 to 4 is listed
with the step that dropped it.

## Caveats reported beside every number

- FAERS reports are voluntary and uneven, and counts are not incidence.
- A boxed warning increases reporting of the reaction it warns about, so a report signal for a
  labelled effect is partly circular. Report precision is shown with and without on-label predictions.
- Patients taking immune drugs have immune diseases, so an infection report may come from the disease
  rather than the drug.
- A lifelong genetic loss is stronger than partial inhibition by a drug, so a predicted effect may be
  milder or absent.
- The drug match on generic name relies on openFDA's harmonised fields, which not every report has.
- The mapping in step 5 is a model output. A sample of 50 mappings, drawn with seed 20261017, is
  checked by a team member and the agreement is reported.
