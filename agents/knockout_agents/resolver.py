"""Turns the words of a request into a drug: a drug name directly, or a protein to the approved drugs acting on it."""

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import httpx

from knockout_agents import settings

# The same ChEMBL action types as Helix rules.LOWERING_ACTIONS and RAISING_ACTIONS (Helix commit 97f3704).
LOWERING_ACTIONS = frozenset({
    "INHIBITOR", "ANTAGONIST", "NEGATIVE ALLOSTERIC MODULATOR", "NEGATIVE MODULATOR", "INVERSE AGONIST", "BLOCKER",
    "DOWN REGULATOR", "DEGRADER", "DISRUPTING AGENT", "ANTISENSE INHIBITOR", "RNAI INHIBITOR", "SEQUESTERING AGENT",
    "PROTEOLYTIC ENZYME", "CROSS-LINKING AGENT",
})
RAISING_ACTIONS = frozenset({
    "AGONIST", "PARTIAL AGONIST", "ACTIVATOR", "POSITIVE ALLOSTERIC MODULATOR", "POSITIVE MODULATOR", "UP REGULATOR",
    "OPENER", "STABILISER", "CHAPERONE",
})


def drug_effect(action_types: tuple[str, ...]) -> str:
    """lowers or raises when every action type agrees, otherwise unknown, as Knockout's target_effect rule."""
    values = {(action or "").strip().upper() for action in action_types}
    if values and values <= LOWERING_ACTIONS:
        return "lowers"
    if values and values <= RAISING_ACTIONS:
        return "raises"
    return "unknown"


class ResolverError(RuntimeError):
    """ChEMBL or UniProt could not be reached."""


@dataclass(frozen=True)
class Drug:
    chembl_id: str
    name: str
    max_phase: float | None
    first_approval: int | None = None
    action_types: tuple[str, ...] = ()

    @property
    def effect(self) -> str:
        return drug_effect(self.action_types)


@dataclass
class TargetDrugs:
    query: str
    target_chembl_id: str
    target_name: str
    gene: str | None
    accession: str | None
    drugs: list[Drug] = field(default_factory=list)
    effect: str | None = None

    @property
    def same_effect(self) -> bool:
        """Every listed drug pushes the protein the same way, so they share one genetic prediction."""
        return len({drug.effect for drug in self.drugs}) == 1 and self.drugs[0].effect != "unknown"


CACHE_DIR = Path(os.environ.get("AGENT_CACHE_DIR") or Path(__file__).resolve().parents[1] / ".cache" / "lookups")
ATTEMPTS = 3
ATTEMPT_TIMEOUT = 10.0
RETRY_STATUSES = {429, 500, 502, 503, 504}


def _cache_path(url: str) -> Path:
    return CACHE_DIR / f"{hashlib.sha256(url.encode()).hexdigest()}.json"


async def _get_json(client: httpx.AsyncClient, url: str) -> dict:
    """ChEMBL and UniProt answer slowly or with a 500 often enough to matter on stage: retry, then cache on disk."""
    public = url.split("?")[0]
    # Only the real public services are cached; the test fakes run on plain http.
    cacheable = url.startswith("https://")
    if cacheable and _cache_path(url).exists():
        return json.loads(_cache_path(url).read_text())
    problem = ""
    for attempt in range(ATTEMPTS):
        if attempt:
            await asyncio.sleep(2 ** (attempt - 1))
        try:
            response = await client.get(url, timeout=ATTEMPT_TIMEOUT)
        except httpx.HTTPError as error:
            problem = f"{public} is unreachable ({error.__class__.__name__})"
            continue
        if response.status_code in RETRY_STATUSES:
            problem = f"{public} returned HTTP {response.status_code}"
            continue
        if response.status_code >= 400:
            raise ResolverError(f"{public} returned HTTP {response.status_code}")
        body = response.json()
        if cacheable:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _cache_path(url).write_text(json.dumps(body))
        return body
    raise ResolverError(f"{problem} after {ATTEMPTS} tries")


def _drug(row: dict, action_types: tuple[str, ...] = ()) -> Drug:
    phase = row.get("max_phase")
    return Drug(
        chembl_id=row["molecule_chembl_id"],
        name=(row.get("pref_name") or row["molecule_chembl_id"]).lower(),
        max_phase=float(phase) if phase is not None else None,
        first_approval=row.get("first_approval"),
        action_types=action_types,
    )


async def find_drug(word: str) -> Drug | None:
    """An exact ChEMBL preferred name or synonym, never a fuzzy match."""
    base = settings.chembl_url()
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for field_name in ("pref_name__iexact", "molecule_synonyms__molecule_synonym__iexact"):
            body = await _get_json(client, f"{base}/molecule.json?{field_name}={quote(word)}&limit=5")
            rows = body.get("molecules") or []
            if rows:
                rows.sort(key=lambda row: -float(row.get("max_phase") or 0))
                return _drug(rows[0])
    return None


async def _uniprot_accession(client: httpx.AsyncClient, gene: str) -> str | None:
    query = quote(f"gene_exact:{gene} AND organism_id:9606 AND reviewed:true")
    body = await _get_json(
        client, f"{settings.uniprot_url()}/uniprotkb/search?query={query}&fields=accession&format=json&size=1"
    )
    results = body.get("results") or []
    return results[0].get("primaryAccession") if results else None


async def _human_target(client: httpx.AsyncClient, words: str) -> tuple[dict | None, str | None]:
    base = settings.chembl_url()
    gene = words.split()[-1].upper()
    accession = await _uniprot_accession(client, gene)
    if accession:
        body = await _get_json(client, f"{base}/target.json?target_components__accession={accession}&limit=20")
        for row in body.get("targets") or []:
            if row.get("target_type") == "SINGLE PROTEIN" and row.get("organism") == "Homo sapiens":
                return row, accession
    body = await _get_json(client, f"{base}/target/search.json?q={quote(words)}&limit=20")
    for row in body.get("targets") or []:
        if row.get("target_type") == "SINGLE PROTEIN" and row.get("organism") == "Homo sapiens":
            components = row.get("target_components") or []
            return row, components[0].get("accession") if len(components) == 1 else None
    return None, None


async def drugs_for_target(words: str, effect: str | None = None) -> TargetDrugs | None:
    """Approved drugs (ChEMBL max phase 4) with a mechanism on the human protein the words name.

    With `effect` ("lowers" for a blocker or an inhibitor, "raises" for an activator), only drugs with that effect.
    """
    base = settings.chembl_url()
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        target, accession = await _human_target(client, words)
        if target is None:
            return None
        target_id = target["target_chembl_id"]
        body = await _get_json(client, f"{base}/mechanism.json?target_chembl_id={target_id}&limit=200")
        action_types: dict[str, set[str]] = {}
        for row in body.get("mechanisms") or []:
            molecule_id = row.get("parent_molecule_chembl_id") or row.get("molecule_chembl_id")
            if molecule_id:
                action_types.setdefault(molecule_id, set()).add(row.get("action_type") or "UNKNOWN")
        drugs: list[Drug] = []
        identifiers = sorted(action_types)
        for start in range(0, len(identifiers), 40):
            chunk = ",".join(identifiers[start:start + 40])
            molecules = await _get_json(
                client,
                f"{base}/molecule.json?molecule_chembl_id__in={chunk}&max_phase=4&limit=100"
                "&only=molecule_chembl_id,pref_name,max_phase,first_approval",
            )
            drugs.extend(
                _drug(row, tuple(sorted(action_types[row["molecule_chembl_id"]])))
                for row in molecules.get("molecules") or []
            )
    if effect:
        drugs = [drug for drug in drugs if drug.effect == effect]
    # the longest-marketed drug has had the most time to collect adverse-event reports
    drugs.sort(key=lambda drug: (drug.first_approval or 9999, drug.name))
    gene = None
    for component in target.get("target_components") or []:
        for synonym in component.get("target_component_synonyms") or []:
            if synonym.get("syn_type") == "GENE_SYMBOL":
                gene = synonym.get("component_synonym")
                break
    return TargetDrugs(
        query=words,
        target_chembl_id=target_id,
        target_name=target.get("pref_name") or target_id,
        gene=gene,
        accession=accession,
        drugs=drugs,
        effect=effect,
    )


async def _warm(words: list[str]) -> None:
    for word in words:
        found = await drugs_for_target(word, "lowers")
        names = ", ".join(drug.name for drug in found.drugs) if found else "no human protein"
        print(f"{word}: {names}")


if __name__ == "__main__":
    import sys

    # Fills the lookup cache before judging: python -m knockout_agents.resolver c5 btk jak3
    asyncio.run(_warm(sys.argv[1:] or ["c5", "btk", "jak3"]))
