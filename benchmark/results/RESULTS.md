# Knockout benchmark results, protocol version 1

Generated 2026-10-17T21:50:14+00:00 by `benchmark/score.py` at commit `20ebd86`. Every rule is in [PROTOCOL.md](../PROTOCOL.md); this file is written by the script and never edited by hand.

- Drug set: `benchmark/drug_set.json`, sha256 `412c92592c6ead6e`, generated 2026-10-17T21:07:38+00:00 from ChEMBL_37 and Helix `97f3704`.
- Mappings: `data/mappings/hpo.json`, missing (step 5 has not run).
- Shuffles: 100, seed 20261017.
- Keys: GEMINI_API_KEY not set, OPENFDA_API_KEY not set. Uncached openFDA requests this run: 0.

## Status

> **Scoring is blocked on step 5: GEMINI_API_KEY is not set in .env, so none of the 525 predictions has a kind or reaction terms, and no label or report check could run.**
> No precision, lift, recall or signal number below was computed; each measure says why.

## Drug set

| Step | Kept | Dropped | Caveat beside these numbers |
| --- | --- | --- | --- |
| 1. Catalog genes with a UniProt accession and a disease of known direction | 407 genes | 104 genes | direction from IUIS, then Orphanet product 6, then the words of the disease name |
| 2. ChEMBL mechanism records on a SINGLE PROTEIN, Homo sapiens target, max phase 4 | 118 records | 329 candidates | ChEMBL_37 (2026-05-01); a drug recorded against a protein family or complex is dropped here |
| 3. Effect matches a disease direction | 57 molecules | 40 molecule-target pairs | effect from Helix molecule_effect(); records that disagree give unknown |
| 4. openFDA holds a label for the generic name | 39 drugs | 18 molecules | the drug match on generic name relies on openFDA's harmonised fields, which not every report or label has |
| Drugs in the set with a boxed warning | 17 drugs |  | most recent label by effective_time |

Dropped at step 4: .Alpha.1-Proteinase Inhibitor Human, Anifrolumab, Atezolizumab, Avacincaptad Pegol Sodium, Copanlisib, Cosibelimab, Cravacitinib, Filgotinib, Forodesine, Human C1-Esterase Inhibitor, Idelalisib, Leniolisib, Mepazine, Retifanlimab, Tirabrutinib, Tislelizumab, Umbralisib, Zanubrutinib. Every drop at every step, with its reason, is in `benchmark/drug_set.json`.

## Drugs scored

| Drug | Genes used | Diseases used | Predictions | Unmapped | FAERS reports | Boxed warning |
| --- | --- | --- | --- | --- | --- | --- |
| Abrocitinib | JAK1 | JAK1 deficiency | 0 | 0 | 3,840 | yes |
| Acalabrutinib | BTK | BTK deficiency, X-linked agammaglobulinemia | 37 | 37 | 12,049 | no |
| Baricitinib | JAK1 | JAK1 deficiency | 0 | 0 | 2,933 | no |
| Bimekizumab | IL17F | IL-17F deficiency | 0 | 0 | 21,176 | no |
| Blinatumomab | CD19 | CD19 deficiency | 7 | 7 | 10,373 | yes |
| Brodalumab | IL17RA | IL-17RA deficiency | 11 | 11 | 2,000 | yes |
| Cemiplimab | PDCD1 | PD-1 deficiency | 18 | 18 | 2,008 | no |
| Crofelemer | CFTR | Cystic fibrosis | 14 | 14 | 233 | no |
| Crovalimab | C5 | C5 deficiency | 3 | 3 | 93 | yes |
| Danicopan | CFD | Factor D deficiency | 2 | 2 | 273 | yes |
| Dostarlimab | PDCD1 | PD-1 deficiency | 18 | 18 | 2,264 | no |
| Durvalumab | CD274 | PD-L1 deficiency | 0 | 0 | 20,225 | no |
| Duvelisib | PIK3CD, PIK3CG | p110δ deficiency; PIK3CG deficiency | 53 | 53 | 765 | yes |
| Eculizumab | C5 | C5 deficiency | 3 | 3 | 54,046 | yes |
| Emapalumab | IFNG | IFN-γ deficiency | 6 | 6 | 208 | no |
| Hydroxychloroquine | TLR7 | TLR7 deficiency | 2 | 2 | 151,391 | no |
| Ibrutinib | BTK | BTK deficiency, X-linked agammaglobulinemia | 37 | 37 | 80,310 | no |
| Imiquimod | TLR7 | TLR7 monogenic lupus | 23 | 23 | 2,292 | no |
| Ipilimumab | CTLA4 | CTLA4 haploinsufficiency (ALPS-V) | 16 | 16 | 42,912 | no |
| Iptacopan | CFB | Factor B deficiency | 0 | 0 | 730 | yes |
| Momelotinib | JAK1 | JAK1 deficiency | 0 | 0 | 1,339 | no |
| Nivolumab | PDCD1 | PD-1 deficiency | 18 | 18 | 96,645 | no |
| Pacritinib | IRAK1 | IRAK1 deficiency | 0 | 0 | 2,964 | no |
| Pazopanib | ITK, LCK | LCK deficiency; ITK deficiency | 43 | 43 | 26,904 | yes |
| Pegcetacoplan | C3 | C3 deficiency (LOF) | 6 | 6 | 1,779 | yes |
| Pembrolizumab | PDCD1 | PD-1 deficiency | 18 | 18 | 104,614 | no |
| Pentostatin | ADA | ADA deficiency | 31 | 31 | 1,048 | yes |
| Pirtobrutinib | BTK | BTK deficiency, X-linked agammaglobulinemia | 37 | 37 | 823 | no |
| Plerixafor | CXCR4 | WHIM (warts, hypogammaglobulinemia, infections, myelokathexis) syndrome | 13 | 13 | 1,464 | no |
| Pozelimab | C5 | C5 deficiency | 3 | 3 | 4 | yes |
| Ravulizumab | C5 | C5 deficiency | 3 | 3 | 13,435 | yes |
| Ritlecitinib | JAK3 | JAK3 deficiency | 19 | 19 | 1,862 | yes |
| Ruxolitinib | JAK1, JAK3, TYK2 | JAK1 deficiency; JAK3 deficiency; TYK2 deficiency | 19 | 19 | 71,241 | no |
| Sarilumab | IL6R | IL-6 receptor deficiency | 6 | 6 | 26,260 | yes |
| Sutimlimab | C1S | C1s deficiency | 0 | 0 | 311 | no |
| Tocilizumab | IL6R | IL-6 receptor deficiency | 6 | 6 | 113,810 | yes |
| Toripalimab | PDCD1 | PD-1 deficiency | 18 | 18 | 15 | no |
| Tremelimumab | CTLA4 | CTLA4 haploinsufficiency (ALPS-V) | 16 | 16 | 4,216 | no |
| Upadacitinib | JAK1, JAK3, TYK2 | TYK2 deficiency; JAK3 deficiency; JAK1 deficiency | 19 | 19 | 81,041 | yes |

Caveats beside these numbers: FAERS reports: FAERS reports are voluntary and uneven; counts are not incidence; the drug match on generic name relies on openFDA's harmonised fields, which not every report or label has. Predictions: a lifelong genetic loss is stronger than partial inhibition, so an effect may be milder or absent.

## Measures

Clinical first, as the protocol orders them.

### 1. Label precision

Not computed: scoring is blocked on step 5: GEMINI_API_KEY is not set in .env, so none of the 525 predictions has a kind or reaction terms, and no label or report check could run.

### 2. Report precision

Not computed: scoring is blocked on step 5: GEMINI_API_KEY is not set in .env, so none of the 525 predictions has a kind or reaction terms, and no label or report check could run.

### 3. Lift over shuffled diseases, label precision

Not computed: scoring is blocked on step 5: GEMINI_API_KEY is not set in .env, so none of the 525 predictions has a kind or reaction terms, and no label or report check could run.

### 4. Lift over shuffled diseases, report precision

Not computed: scoring is blocked on step 5: GEMINI_API_KEY is not set in .env, so none of the 525 predictions has a kind or reaction terms, and no label or report check could run.

### 5. Boxed-warning recall

Not computed: scoring is blocked on step 5: GEMINI_API_KEY is not set in .env, so none of the 525 predictions has a kind or reaction terms, and no label or report check could run.

### 6. Candidate new signals

Not computed: scoring is blocked on step 5: GEMINI_API_KEY is not set in .env, so none of the 525 predictions has a kind or reaction terms, and no label or report check could run.

## Misses

Not computed: scoring is blocked on step 5: GEMINI_API_KEY is not set in .env, so none of the 525 predictions has a kind or reaction terms, and no label or report check could run.

## Checks

Every drug's engine run used the genes that brought it into the set.

## Caveats in full

- FAERS reports are voluntary and uneven, and counts are not incidence.
- A boxed warning increases reporting of the reaction it warns about, so a report signal for a labelled effect is partly circular. Report precision is shown with and without on-label predictions.
- Patients taking immune drugs have immune diseases, so an infection report may come from the disease rather than the drug.
- A lifelong genetic loss is stronger than partial inhibition by a drug, so a predicted effect may be milder or absent.
- The drug match on generic name relies on openFDA's harmonised fields, which not every report has.
- The mapping in step 5 is a model output. A sample of 50 mappings, drawn with seed 20261017, is checked by a team member: the 50-mapping review sample has not been checked yet.
