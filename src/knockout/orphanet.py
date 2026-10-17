"""Orphanet product 6: whether a disease-gene association is a loss or a gain of function."""

import json
from functools import lru_cache
from xml.etree import ElementTree

from knockout.config import CACHE_DIR, ORPHANET_DIR

PRODUCT6_PATH = ORPHANET_DIR / "en_product6.xml"
PARSED_PATH = CACHE_DIR / "orphanet_associations.json"


def _parse() -> dict[str, str]:
    associations: dict[str, str] = {}
    for _, element in ElementTree.iterparse(PRODUCT6_PATH):
        if element.tag != "Disorder":
            continue
        code = element.findtext("OrphaCode")
        for association in element.iter("DisorderGeneAssociation"):
            symbol = association.findtext("Gene/Symbol")
            kind = association.findtext("DisorderGeneAssociationType/Name") or ""
            if code and symbol:
                associations[f"ORPHA:{code}|{symbol}"] = kind
        element.clear()
    return associations


@lru_cache(maxsize=1)
def associations() -> dict[str, str]:
    if PARSED_PATH.exists() and PARSED_PATH.stat().st_mtime >= PRODUCT6_PATH.stat().st_mtime:
        return json.loads(PARSED_PATH.read_text())
    parsed = _parse()
    PARSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    PARSED_PATH.write_text(json.dumps(parsed))
    return parsed


def association_type(orpha_code: str, gene_symbol: str) -> str | None:
    return associations().get(f"{orpha_code}|{gene_symbol}")
