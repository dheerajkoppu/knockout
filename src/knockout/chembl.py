"""ChEMBL: a drug name to its parent molecule, mechanisms and protein targets."""

from dataclasses import dataclass
from urllib.parse import quote

from knockout.http import get_json

BASE = "https://www.ebi.ac.uk/chembl/api/data"


@dataclass(frozen=True)
class Molecule:
    chembl_id: str
    name: str
    max_phase: float | None
    molecule_type: str | None

    @property
    def url(self) -> str:
        return f"https://www.ebi.ac.uk/chembl/explore/compound/{self.chembl_id}"


@dataclass(frozen=True)
class Target:
    chembl_id: str
    name: str
    target_type: str
    organism: str | None
    accessions: tuple[str, ...]


@dataclass(frozen=True)
class Mechanism:
    record_id: int
    action_type: str | None
    description: str | None
    target: Target | None


def _molecule(row: dict) -> Molecule:
    phase = row.get("max_phase")
    return Molecule(
        chembl_id=row["molecule_chembl_id"],
        name=(row.get("pref_name") or row["molecule_chembl_id"]).title(),
        max_phase=float(phase) if phase is not None else None,
        molecule_type=row.get("molecule_type"),
    )


def _parent(row: dict) -> Molecule:
    parent_id = (row.get("molecule_hierarchy") or {}).get("parent_chembl_id")
    if parent_id and parent_id != row["molecule_chembl_id"]:
        return molecule(parent_id)
    return _molecule(row)


def molecule(chembl_id: str) -> Molecule:
    return _molecule(get_json(f"{BASE}/molecule/{chembl_id}.json"))


def resolve(name_or_id: str) -> Molecule | None:
    """Exact preferred name first, then a synonym, then ChEMBL's ranked search. Always the parent."""
    text = name_or_id.strip()
    if text.upper().startswith("CHEMBL"):
        return _parent(get_json(f"{BASE}/molecule/{text.upper()}.json"))
    exact = get_json(f"{BASE}/molecule.json?pref_name__iexact={quote(text)}&limit=5")["molecules"]
    if exact:
        return _parent(exact[0])
    synonym = get_json(
        f"{BASE}/molecule.json?molecule_synonyms__molecule_synonym__iexact={quote(text)}&limit=5"
    )["molecules"]
    if synonym:
        return _parent(synonym[0])
    ranked = get_json(f"{BASE}/molecule/search.json?q={quote(text)}&limit=5")["molecules"]
    return _parent(ranked[0]) if ranked else None


def target(chembl_id: str) -> Target:
    row = get_json(f"{BASE}/target/{chembl_id}.json")
    return Target(
        chembl_id=chembl_id,
        name=row.get("pref_name") or chembl_id,
        target_type=row.get("target_type") or "UNKNOWN",
        organism=row.get("organism"),
        accessions=tuple(
            component["accession"] for component in row.get("target_components", []) if component.get("accession")
        ),
    )


def mechanisms(chembl_id: str) -> list[Mechanism]:
    rows = get_json(f"{BASE}/mechanism.json?molecule_chembl_id={chembl_id}&limit=100")["mechanisms"]
    return [
        Mechanism(
            record_id=row["mec_id"],
            action_type=row.get("action_type"),
            description=row.get("mechanism_of_action"),
            target=target(row["target_chembl_id"]) if row.get("target_chembl_id") else None,
        )
        for row in rows
    ]
