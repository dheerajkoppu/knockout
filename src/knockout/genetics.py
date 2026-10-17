"""A protein to its IUIS diseases, each disease's direction, and the phenotypes used (protocol steps 2 and 4)."""

import re
from dataclasses import dataclass
from functools import lru_cache

from helix.discovery.subject import resolve_mechanism
from helix.knowledge.catalog import Catalog, SeedDisease, SeedGene, SeedPhenotype, load_catalog

from knockout import (
    config,
    orphanet,
)

MIN_CASE_FRACTION = 0.30
INCLUDED_FREQUENCIES = {"obligate", "very frequent", "frequent"}


@dataclass(frozen=True)
class DiseaseDirection:
    direction: str
    source: str | None
    basis: str


@lru_cache(maxsize=1)
def catalog() -> Catalog:
    loaded = load_catalog()
    if not loaded.ready:
        raise RuntimeError(f"Helix catalog not loaded from {config.HELIX_SEED_DIR}. Run `knockout setup`.")
    return loaded


def gene_for_accession(accession: str) -> SeedGene | None:
    return catalog().gene_by_uniprot(accession)


def diseases(gene: SeedGene) -> list[SeedDisease]:
    return catalog().diseases_for_gene(gene.symbol)


def disease_direction(disease: SeedDisease, gene_symbol: str) -> DiseaseDirection:
    """IUIS stated mechanism, then Orphanet product 6, then the disease name, as the protocol orders them."""
    resolved = resolve_mechanism(catalog(), [disease], gene_symbol)
    if resolved.confidence == "stated_in_the_catalog" and resolved.mechanism_class == "neomorph":
        # Protocol step 3 counts only gain of function as increased activity; a new function is not more of the old one.
        return DiseaseDirection("unknown", "iuis", f"{resolved.basis} A neomorph is not a direction the protocol uses.")
    if resolved.confidence == "stated_in_the_catalog":
        return DiseaseDirection(resolved.direction, "iuis", resolved.basis)
    for code in disease.xrefs.orphanet:
        kind = orphanet.association_type(code, gene_symbol) or ""
        if "loss of function" in kind:
            return DiseaseDirection("decreased_activity", "orphanet", f"Orphanet {code}: {kind}")
        if "gain of function" in kind:
            return DiseaseDirection("increased_activity", "orphanet", f"Orphanet {code}: {kind}")
    if resolved.confidence == "named_in_the_disease_label":
        return DiseaseDirection(resolved.direction, "disease_name", resolved.basis)
    return DiseaseDirection("unknown", None, resolved.basis)


def frequency_qualifies(frequency: str | None) -> bool:
    if not frequency:
        return False
    fraction = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", frequency)
    if fraction:
        cases, total = int(fraction.group(1)), int(fraction.group(2))
        return total > 0 and cases / total >= MIN_CASE_FRACTION
    name = re.sub(r"\s*\(.*\)\s*$", "", frequency).strip().lower()
    return name in INCLUDED_FREQUENCIES


def qualifying_phenotypes(disease: SeedDisease) -> list[SeedPhenotype]:
    return [phenotype for phenotype in disease.phenotypes if frequency_qualifies(phenotype.frequency)]


def excluded_phenotypes(disease: SeedDisease) -> list[SeedPhenotype]:
    return [phenotype for phenotype in disease.phenotypes if not frequency_qualifies(phenotype.frequency)]
