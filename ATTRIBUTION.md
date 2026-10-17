# Attribution

The code in this repository is MIT (see `LICENSE`). Data that Knockout downloads, or that the
repository redistributes in derived form (`benchmark/drug_set.json`, `benchmark/results/`,
`web/fixtures/`, `data/mappings/hpo.json` once generated), keeps the licence of its source.

| Source                                                         | What Knockout uses                                                                         | Licence                                                                | Terms                                                                         |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| ChEMBL (EMBL-EBI)                                              | Molecules, mechanism records and targets                                                   | CC BY-SA 3.0                                                           | https://chembl.gitbook.io/chembl-interface-documentation/about#data-licensing |
| openFDA (US FDA)                                               | Drug labels (SPL) and FAERS adverse-event report totals                                    | Public domain (CC0 1.0)                                                | https://open.fda.gov/terms/                                                   |
| IUIS classification of inborn errors of immunity, 2024 update  | Genes, diseases and stated mechanisms, through the Helix catalog                           | CC BY-ND 4.0                                                           | https://creativecommons.org/licenses/by-nd/4.0/                               |
| Orphanet / Orphadata (products 1, 4 and 6, release 2026-06-23) | Disease cross-references, phenotypes and gene association types (gain or loss of function) | CC BY 4.0                                                              | https://creativecommons.org/licenses/by/4.0/legalcode                         |
| Human Phenotype Ontology (hp.obo and phenotype.hpoa)           | Phenotype terms and their frequencies per disease                                          | HPO licence: free to use with attribution; content must not be altered | https://human-phenotype-ontology.github.io/license.html                       |
| UniProtKB                                                      | Protein accessions                                                                         | CC BY 4.0                                                              | https://creativecommons.org/licenses/by/4.0/                                  |
| HGNC, Mondo, GenCC, ClinGen                                    | Gene symbols and disease mappings inside the Helix catalog                                 | CC0 1.0 (Mondo: CC BY 4.0)                                             | see `data/helix/SOURCES.json` after `knockout setup`                          |
| Helix (Dheeraj Koppu)                                          | The catalog loader, `resolve_mechanism` and `molecule_effect`, pinned at commit `97f3704`  | MIT                                                                    | https://github.com/dheerajkoppu/helix                                         |

Citations requested by the sources:

- Zdrazil B. et al. The ChEMBL Database in 2023. _Nucleic Acids Research_ 52, D1180–D1192 (2024).
- Gargano M. A. et al. The Human Phenotype Ontology in 2024. _Nucleic Acids Research_ 52, D1333–D1346 (2024).
- Orphanet: an online database on rare diseases and orphan drugs. INSERM, 1999–2026. https://www.orpha.net
- Poli M. C. et al. Human inborn errors of immunity: 2024 update on the classification from the
  International Union of Immunological Societies Expert Committee. _Journal of Human Immunology_ (2025).

Phenotype labels and HPO identifiers are shown unaltered. The reaction-term mapping in
`data/mappings/hpo.json` is a model output (Gemini) recorded with the model name and time; it is
Knockout's own work and is released under the MIT licence.

openFDA notes that its data is not for clinical use and that FAERS reports do not establish that a
drug caused an event. Nothing in Knockout is medical advice.
