"""Generate the drug set exactly as benchmark/PROTOCOL.md ("Drug set") states. Never edit the output by hand.

Run from the repository root: .venv/bin/python -m benchmark.drug_set
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from knockout import chembl, config, genetics, openfda, rules
from knockout.http import SourceError, get_json

OUTPUT_PATH = Path(__file__).resolve().parent / "drug_set.json"
PROTOCOL_VERSION = 2
SINGLE_PROTEIN = "SINGLE PROTEIN"
HUMAN = "Homo sapiens"
APPROVED_PHASE = 4.0
CHEMBL_WORKERS = 8
CHEMBL_HOST = "https://www.ebi.ac.uk"
MOLECULE_BATCH = 50
NETWORK_CALL_SECONDS = 0.05
# openFDA without a key allows about 40 requests a minute; stay under it.
OPENFDA_INTERVAL_WITHOUT_KEY = 1.6
OPENFDA_INTERVAL_WITH_KEY = 0.3


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _all_pages(url: str, key: str) -> list[dict]:
    rows: list[dict] = []
    next_url: str | None = url
    while next_url:
        body = get_json(next_url)
        rows.extend(body[key])
        following = body["page_meta"].get("next")
        next_url = f"{CHEMBL_HOST}{following}" if following else None
    return rows


def _parallel(function, items: list) -> dict:
    """function(item) for distinct items, so no two threads ever write the same cache file."""
    distinct = list(dict.fromkeys(items))
    with ThreadPoolExecutor(max_workers=CHEMBL_WORKERS) as pool:
        return dict(zip(distinct, pool.map(function, distinct)))


class OpenFdaPacer:
    """Spaces uncached openFDA calls to stay inside the keyless rate limit, and counts them."""

    def __init__(self) -> None:
        self.interval = OPENFDA_INTERVAL_WITH_KEY if config.openfda_api_key() else OPENFDA_INTERVAL_WITHOUT_KEY
        self.network_calls = 0

    def call(self, function, *arguments):
        started = time.monotonic()
        result = function(*arguments)
        elapsed = time.monotonic() - started
        if elapsed > NETWORK_CALL_SECONDS:
            self.network_calls += 1
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)
        return result


def step1_genes() -> tuple[list[dict], list[dict]]:
    """Every catalog gene with a UniProt accession and at least one disease with a known direction."""
    kept, dropped = [], []
    for gene in sorted(genetics.catalog().genes, key=lambda row: row.symbol):
        if not gene.uniprot_accession:
            dropped.append({"step": 1, "gene": gene.symbol, "reason": "no UniProt accession in the catalog"})
            continue
        known, unknown = [], []
        for disease in genetics.diseases(gene):
            direction = genetics.disease_direction(disease, gene.symbol)
            row = {
                "disease_id": disease.id,
                "name": disease.name,
                "direction": direction.direction,
                "direction_source": direction.source,
                "direction_basis": direction.basis,
            }
            (unknown if direction.direction == "unknown" else known).append(row)
        if not known:
            dropped.append({
                "step": 1,
                "gene": gene.symbol,
                "accession": gene.uniprot_accession,
                "reason": "no disease with a known direction",
                "diseases": [row["name"] for row in unknown],
            })
            continue
        kept.append({"gene": gene.symbol, "accession": gene.uniprot_accession, "diseases": known})
    return kept, dropped


def _targets_for_accession(accession: str) -> list[dict]:
    return _all_pages(f"{chembl.BASE}/target.json?target_components__accession={accession}&limit=100", "targets")


def _mechanisms_for_target(target_id: str) -> list[dict]:
    return _all_pages(f"{chembl.BASE}/mechanism.json?target_chembl_id={target_id}&limit=1000", "mechanisms")


def _molecule_batch(chembl_ids: tuple[str, ...]) -> list[dict]:
    joined = ",".join(chembl_ids)
    return _all_pages(
        f"{chembl.BASE}/molecule.json?molecule_chembl_id__in={joined}&limit={MOLECULE_BATCH}", "molecules"
    )


def _parent_id(record: dict) -> str:
    return record.get("parent_molecule_chembl_id") or record["molecule_chembl_id"]


def step2_records(genes: list[dict]) -> tuple[list[dict], list[dict], dict[str, dict]]:
    """Mechanism records on a SINGLE PROTEIN, Homo sapiens target with the gene's accession, at max phase 4."""
    accessions = [gene["accession"] for gene in genes]
    _log(f"step 2: ChEMBL targets for {len(accessions)} accessions")
    targets_by_accession = _parallel(_targets_for_accession, accessions)

    dropped: list[dict] = []
    target_rows: list[tuple[dict, dict]] = []
    for gene in genes:
        for target in targets_by_accession[gene["accession"]]:
            target_rows.append((gene, target))

    target_ids = [target["target_chembl_id"] for _, target in target_rows]
    _log(f"step 2: mechanism records for {len(set(target_ids))} targets")
    records_by_target = _parallel(_mechanisms_for_target, target_ids)

    candidate_records: list[tuple[dict, dict, dict]] = []
    for gene, target in target_rows:
        records = records_by_target[target["target_chembl_id"]]
        accessions_on_target = [
            component.get("accession") for component in target.get("target_components", []) if component.get("accession")
        ]
        if target.get("target_type") != SINGLE_PROTEIN or target.get("organism") != HUMAN:
            if records:
                dropped.append({
                    "step": 2,
                    "gene": gene["gene"],
                    "target_chembl_id": target["target_chembl_id"],
                    "target_name": target.get("pref_name"),
                    "reason": f"target is {target.get('target_type')} in {target.get('organism')}, "
                    "the protocol uses SINGLE PROTEIN in Homo sapiens only",
                    "molecules": sorted({_parent_id(record) for record in records}),
                })
            continue
        if accessions_on_target != [gene["accession"]]:
            if records:
                dropped.append({
                    "step": 2,
                    "gene": gene["gene"],
                    "target_chembl_id": target["target_chembl_id"],
                    "reason": f"target accessions {accessions_on_target} are not exactly {gene['accession']}",
                    "molecules": sorted({_parent_id(record) for record in records}),
                })
            continue
        candidate_records.extend((gene, target, record) for record in records)

    parent_ids = sorted({_parent_id(record) for *_, record in candidate_records})
    _log(f"step 2: max phase for {len(parent_ids)} parent molecules")
    batches = [tuple(parent_ids[start : start + MOLECULE_BATCH]) for start in range(0, len(parent_ids), MOLECULE_BATCH)]
    molecules: dict[str, dict] = {}
    for rows in _parallel(_molecule_batch, batches).values():
        for row in rows:
            molecules[row["molecule_chembl_id"]] = row

    kept: list[dict] = []
    below_phase: dict[tuple[str, str], dict] = {}
    for gene, target, record in candidate_records:
        parent = _parent_id(record)
        row = molecules.get(parent) or {}
        phase = float(row["max_phase"]) if row.get("max_phase") is not None else None
        if phase != APPROVED_PHASE:
            below_phase.setdefault((parent, target["target_chembl_id"]), {
                "step": 2,
                "molecule_chembl_id": parent,
                "name": row.get("pref_name"),
                "gene": gene["gene"],
                "target_chembl_id": target["target_chembl_id"],
                "reason": f"max phase is {phase}, the protocol uses max phase 4 only",
            })
            continue
        kept.append({"gene": gene, "target": target, "record": record, "molecule": row})
    dropped.extend(sorted(below_phase.values(), key=lambda row: (row["gene"], row["molecule_chembl_id"])))
    return kept, dropped, molecules


def step3_pairs(records: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    """Kept when the effect lowers a gene with a decreased-activity disease, or raises one with an increased one."""
    grouped: dict[tuple[str, str], list[dict]] = {}
    for item in records:
        grouped.setdefault((_parent_id(item["record"]), item["target"]["target_chembl_id"]), []).append(item)

    kept: dict[str, list[dict]] = {}
    failed: list[dict] = []
    for (parent, target_id), items in sorted(grouped.items()):
        gene = items[0]["gene"]
        target = items[0]["target"]
        action_types = [item["record"].get("action_type") for item in items]
        effect = rules.target_effect(action_types)
        pairings = [(disease, rules.pairing(effect, disease["direction"])) for disease in gene["diseases"]]
        used = [disease for disease, pairing in pairings if pairing == "use"]
        row = {
            "molecule_chembl_id": parent,
            "name": items[0]["molecule"].get("pref_name"),
            "gene": gene["gene"],
            "accession": gene["accession"],
            "target_chembl_id": target_id,
            "target_name": target.get("pref_name"),
            "effect": effect,
            "action_types": action_types,
            "mechanism_record_ids": sorted(item["record"]["mec_id"] for item in items),
            "records_on_salt_forms": sorted({
                item["record"]["molecule_chembl_id"] for item in items if item["record"]["molecule_chembl_id"] != parent
            }),
        }
        if used:
            kept.setdefault(parent, []).append(row | {"diseases_used": used})
            continue
        if effect == "unknown":
            reason = f"effect is unknown for action types {sorted(set(map(str, action_types)))}"
        else:
            reason = f"effect {effect} points the other way from every disease of {gene['gene']}"
        failed.append(row | {
            "step": 3,
            "reason": reason,
            "gene_directions": sorted({disease["direction"] for disease in gene["diseases"]}),
        })
    for row in failed:
        row["molecule_kept_through_another_target"] = row["molecule_chembl_id"] in kept
    return kept, failed


def step4_labels(pairs: dict[str, list[dict]]) -> tuple[list[dict], list[dict], int]:
    """Kept when openFDA holds a label for the molecule's generic name."""
    _log(f"step 4: ChEMBL parent records for {len(pairs)} molecules")
    parents = _parallel(chembl.molecule, sorted(pairs))
    pacer = OpenFdaPacer()
    drugs, dropped = [], []
    for position, parent_id in enumerate(sorted(pairs, key=lambda chembl_id: parents[chembl_id].name.lower())):
        molecule = parents[parent_id]
        base = {
            "chembl_id": molecule.chembl_id,
            "name": molecule.name,
            "max_phase": molecule.max_phase,
            "molecule_type": molecule.molecule_type,
        }
        if molecule.name == molecule.chembl_id.title():
            dropped.append(base | {"step": 4, "reason": "ChEMBL has no preferred name, so there is no generic name to search"})
            continue
        generic_name = molecule.name.lower()
        try:
            label = pacer.call(openfda.label, generic_name)
        except SourceError as error:
            dropped.append(base | {"step": 4, "generic_name": generic_name, "reason": f"openFDA label search failed: {error}",
                                   "source_failed": True})
            continue
        if position % 20 == 0:
            _log(f"step 4: labels {position}/{len(pairs)} ({pacer.network_calls} openFDA network calls)")
        if label is None:
            dropped.append(base | {"step": 4, "generic_name": generic_name,
                                   "reason": f"openFDA holds no label for {generic_name!r} by any of the step 6 rules"})
            continue
        drugs.append(base | {
            "generic_name": generic_name,
            "reason": {
                "summary": "; ".join(
                    f"{pair['effect']} {pair['gene']} ({', '.join(sorted(set(map(str, pair['action_types']))))}), "
                    f"which has {len(pair['diseases_used'])} disease(s) with "
                    f"{pair['diseases_used'][0]['direction'].replace('_', ' ')}"
                    for pair in pairs[parent_id]
                ),
                "targets": pairs[parent_id],
            },
            "label": {
                "set_id": label.set_id,
                "effective_time": label.effective_time,
                "generic_names": list(label.generic_names),
                "sections": list(label.sections),
                "has_boxed_warning": "boxed_warning" in label.sections,
                "matched_by": label.matched_by,
                "url": label.url,
            },
        })
    return drugs, dropped, pacer.network_calls


def _sources() -> dict:
    status = get_json(f"{chembl.BASE}/status.json")
    manifest = genetics.catalog().manifest
    return {
        "helix_commit": config.HELIX_COMMIT,
        "catalog_generated_at": manifest.generated_at if manifest else None,
        "chembl_release": status.get("chembl_db_version"),
        "chembl_release_date": status.get("chembl_release_date"),
        "orphanet_product6": str(config.ORPHANET_DIR.relative_to(config.ROOT_DIR) / "en_product6.xml"),
        "openfda": "https://api.fda.gov/drug/label.json (protocol step 6: exact generic name, then phrase, then "
                   "unharmonised product data elements; most recent by effective_time)",
    }


def generate() -> dict:
    genes, dropped_genes = step1_genes()
    _log(f"step 1: {len(genes)} genes kept, {len(dropped_genes)} dropped")
    records, dropped_records, _ = step2_records(genes)
    _log(f"step 2: {len(records)} mechanism records kept, {len(dropped_records)} candidates dropped")
    pairs, dropped_pairs = step3_pairs(records)
    _log(f"step 3: {len(pairs)} molecules kept, {len(dropped_pairs)} molecule-target pairs dropped")
    drugs, dropped_labels, network_calls = step4_labels(pairs)
    _log(f"step 4: {len(drugs)} drugs kept, {len(dropped_labels)} dropped, {network_calls} openFDA network calls")
    return {
        "protocol_version": PROTOCOL_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "generated_by": "benchmark/drug_set.py",
        "sources": _sources(),
        "counts": {
            "step1_genes_kept": len(genes),
            "step1_genes_dropped": len(dropped_genes),
            "step2_records_kept": len(records),
            "step2_candidates_dropped": len(dropped_records),
            "step3_molecules_kept": len(pairs),
            "step3_pairs_dropped": len(dropped_pairs),
            "step4_drugs_kept": len(drugs),
            "step4_molecules_dropped": len(dropped_labels),
            "drugs_with_boxed_warning": sum(drug["label"]["has_boxed_warning"] for drug in drugs),
        },
        "drugs": drugs,
        "dropped": {
            "step1": dropped_genes,
            "step2": dropped_records,
            "step3": dropped_pairs,
            "step4": dropped_labels,
        },
    }


def main() -> int:
    drug_set = generate()
    OUTPUT_PATH.write_text(json.dumps(drug_set, indent=1, default=str) + "\n")
    _log(f"wrote {OUTPUT_PATH} with {len(drug_set['drugs'])} drugs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
