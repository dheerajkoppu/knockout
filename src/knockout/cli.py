"""`knockout setup` fetches the pinned data; `knockout predict <drug>` runs the engine."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from knockout import config
from knockout.http import download


def setup() -> int:
    for name in config.HELIX_SEED_FILES:
        destination = config.HELIX_SEED_DIR / name
        if not destination.exists():
            download(f"{config.HELIX_RAW_URL}/{name}", destination)
        print(f"helix {config.HELIX_COMMIT} {name}: {destination.stat().st_size:,} bytes")

    product6 = config.ORPHANET_DIR / "en_product6.xml"
    if not product6.exists():
        download(config.ORPHANET_PRODUCT6_URL, product6)
    sources = json.loads((config.HELIX_SEED_DIR / "SOURCES.json").read_text())
    pinned = next(
        (row for row in sources.get("sources", sources) if isinstance(row, dict) and row.get("id") == "orphadata_product6"),
        None,
    )
    digest = hashlib.sha256(product6.read_bytes()).hexdigest()
    if pinned and pinned.get("sha256") == digest:
        print(f"orphanet product 6: release {pinned['release']}, checksum matches Helix")
    else:
        print(f"orphanet product 6: checksum {digest[:12]} differs from the release the protocol names", file=sys.stderr)
    return 0


def _summary(report: dict) -> str:
    lines = []
    molecule = report.get("molecule") or {}
    lines.append(f"{molecule.get('name', report['query'])} ({molecule.get('chembl_id', '?')})")
    for target in report["targets"]:
        status = "used" if target["used"] else f"not used: {target['reason']}"
        lines.append(f"  target {target['name']} [{target['effect']}] {target['gene'] or ''} {status}")
    for disease in report["diseases"]:
        lines.append(
            f"  disease {disease['name']}: {disease['direction']} via {disease['direction_source']} -> {disease['pairing']}"
        )
    label = report.get("label") or {}
    lines.append(f"  label {label.get('set_id', 'none')} ({label.get('effective_time', '')})")
    lines.append(f"  reports: {report.get('drug_reports')} for the drug, {report.get('all_reports')} in FAERS")
    for prediction in report["predictions"]:
        best = max(prediction["counts"], key=lambda row: row["prr"] or 0, default=None)
        counts = f"a={best['a']} PRR={best['prr']:.1f}" if best and best["prr"] is not None else ""
        lines.append(f"  [{prediction['verdict']}] {prediction['phenotype']} -> {', '.join(prediction['reaction_terms'])} {counts}")
        if prediction["label_sentence"]:
            lines.append(f"      label ({prediction['label_section']}): {prediction['label_sentence'][:160]}")
        if prediction["reason"]:
            lines.append(f"      {prediction['reason']}")
    for problem in report["problems"]:
        lines.append(f"  problem: {problem}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(prog="knockout")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup", help="download the pinned Helix catalog and Orphanet product 6")
    predict = commands.add_parser("predict", help="predict a drug's side effects")
    predict.add_argument("drug")
    predict.add_argument("--json", type=Path, help="write the full report as JSON")
    predict.add_argument("--no-generate", action="store_true", help="use only committed mappings")
    arguments = parser.parse_args()

    if arguments.command == "setup":
        return setup()
    from knockout import observability
    from knockout.engine import predict as run

    observability.setup()

    report = run(arguments.drug, generate_mappings=not arguments.no_generate).to_dict()
    if arguments.json:
        arguments.json.parent.mkdir(parents=True, exist_ok=True)
        arguments.json.write_text(json.dumps(report, indent=1, default=str) + "\n")
    print(_summary(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
