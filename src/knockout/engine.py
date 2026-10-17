"""Protocol steps 1 to 8 for one drug. Every prediction carries the records it rests on."""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from knockout import chembl, genetics, label_match, mapping, openfda, rules
from knockout.gemini import GeminiUnavailable
from knockout.http import SourceError
from knockout.signals import TermCounts

SINGLE_PROTEIN = "SINGLE PROTEIN"
HUMAN = "Homo sapiens"


@dataclass
class Record:
    source: str
    description: str
    url: str | None = None


@dataclass
class TargetRow:
    chembl_id: str
    name: str
    accession: str | None
    effect: str
    action_types: list[str | None]
    gene: str | None = None
    used: bool = False
    reason: str | None = None


@dataclass
class DiseaseRow:
    disease_id: str
    name: str
    gene: str
    direction: str
    direction_source: str | None
    direction_basis: str
    pairing: str
    phenotypes_used: int = 0


@dataclass
class Prediction:
    hpo_id: str
    phenotype: str
    frequency: str | None
    kind: str | None
    gene: str
    target: str
    disease_id: str
    disease: str
    reaction_terms: list[str]
    label_section: str | None = None
    label_term: str | None = None
    label_sentence: str | None = None
    counts: list[dict] = field(default_factory=list)
    verdict: str = "unknown"
    reason: str | None = None
    candidate_new_signal: bool = False
    records: list[Record] = field(default_factory=list)


@dataclass
class Report:
    query: str
    generated_at: str
    molecule: dict | None = None
    targets: list[TargetRow] = field(default_factory=list)
    diseases: list[DiseaseRow] = field(default_factory=list)
    predictions: list[Prediction] = field(default_factory=list)
    excluded_developmental: list[dict] = field(default_factory=list)
    excluded_by_frequency: list[dict] = field(default_factory=list)
    label: dict | None = None
    drug_reports: int | None = None
    all_reports: int | None = None
    openfda_retrieved_at: str | None = None
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _targets(report: Report, molecule: chembl.Molecule) -> list[TargetRow]:
    grouped: dict[str, list[chembl.Mechanism]] = {}
    for mechanism in chembl.mechanisms(molecule.chembl_id):
        if mechanism.target is None:
            continue
        grouped.setdefault(mechanism.target.chembl_id, []).append(mechanism)
    rows = []
    for target_id, mechanisms in grouped.items():
        target = mechanisms[0].target
        action_types = [mechanism.action_type for mechanism in mechanisms]
        row = TargetRow(
            chembl_id=target_id,
            name=target.name,
            accession=target.accessions[0] if len(target.accessions) == 1 else None,
            effect=rules.target_effect(action_types),
            action_types=action_types,
        )
        if target.target_type != SINGLE_PROTEIN:
            row.reason = f"target type is {target.target_type}, the protocol uses SINGLE PROTEIN only"
        elif target.organism != HUMAN:
            row.reason = f"organism is {target.organism}"
        elif row.accession is None:
            row.reason = "no single UniProt accession"
        rows.append(row)
    report.targets = rows
    return rows


def _diseases(report: Report, target: TargetRow) -> list[tuple[DiseaseRow, list]]:
    gene = genetics.gene_for_accession(target.accession)
    if gene is None:
        target.reason = "protein is not in the IUIS catalog"
        return []
    target.gene = gene.symbol
    used = []
    for disease in genetics.diseases(gene):
        direction = genetics.disease_direction(disease, gene.symbol)
        row = DiseaseRow(
            disease_id=disease.id,
            name=disease.name,
            gene=gene.symbol,
            direction=direction.direction,
            direction_source=direction.source,
            direction_basis=direction.basis,
            pairing=rules.pairing(target.effect, direction.direction),
        )
        report.diseases.append(row)
        if row.pairing == "use":
            phenotypes = genetics.qualifying_phenotypes(disease)
            row.phenotypes_used = len(phenotypes)
            report.excluded_by_frequency.extend(
                {"hpo_id": phenotype.hpo_id, "phenotype": phenotype.label or phenotype.hpo_id,
                 "frequency": phenotype.frequency, "disease_id": disease.id}
                for phenotype in genetics.excluded_phenotypes(disease)
            )
            used.append((row, disease, phenotypes))
    if not used:
        target.reason = target.reason or "no disease of this protein pairs with the drug's effect"
    target.used = bool(used)
    return used


def _disease_records(disease) -> list[Record]:
    return [
        Record(source=item.source_id, description=f"Catalog record {item.record_id or disease.id}", url=item.url)
        for item in disease.provenance
    ]


def _count(drug: str, term: str, drug_total: int, all_total: int) -> TermCounts:
    reaction = openfda.reaction_search(term)
    return TermCounts(
        term=term,
        a=openfda.total(f"{openfda.drug_search(drug)} AND {reaction}"),
        drug=drug_total,
        reaction=openfda.total(reaction),
        all=all_total,
    )


def predict(query: str, *, generate_mappings: bool = True) -> Report:
    report = Report(query=query, generated_at=_now())
    molecule = chembl.resolve(query)
    if molecule is None:
        report.problems.append(f"ChEMBL has no molecule named {query!r}")
        return report
    report.molecule = asdict(molecule) | {"url": molecule.url}
    generic_name = molecule.name.lower()

    rows = []
    for target in _targets(report, molecule):
        if target.reason is None:
            for disease_row, disease, phenotypes in _diseases(report, target):
                rows.extend((target, disease_row, disease, phenotype) for phenotype in phenotypes)

    terms = {phenotype.hpo_id: phenotype.label or phenotype.hpo_id for *_, phenotype in rows}
    try:
        mappings = mapping.ensure(terms) if generate_mappings else mapping.stored(terms)
    except GeminiUnavailable as error:
        report.problems.append(f"Step 5 could not map new phenotypes: {error}")
        mappings = mapping.stored(terms)

    label = openfda.label(generic_name)
    if label is None:
        report.problems.append(f"openFDA has no label for {generic_name!r}")
    else:
        report.label = {
            "set_id": label.set_id,
            "effective_time": label.effective_time,
            "generic_names": list(label.generic_names),
            "sections": list(label.sections),
            "matched_by": label.matched_by,
            "url": label.url,
        }
    reports_problem = None
    try:
        report.drug_reports = openfda.total(openfda.drug_search(generic_name))
        report.all_reports = openfda.total(None)
    except SourceError as error:
        reports_problem = f"openFDA reports unavailable: {error}"
        report.problems.append(reports_problem)
    retrieval_times = [time for time in (
        label.retrieved_at if label else None,
        openfda.total_retrieved_at(openfda.drug_search(generic_name)),
        openfda.total_retrieved_at(None),
    ) if time]
    report.openfda_retrieved_at = min(retrieval_times) if retrieval_times else None

    for target, disease_row, disease, phenotype in rows:
        mapped = mappings.get(phenotype.hpo_id)
        if mapped is not None and mapped.kind == "developmental":
            report.excluded_developmental.append({"hpo_id": phenotype.hpo_id, "phenotype": mapped.label})
            continue
        prediction = Prediction(
            hpo_id=phenotype.hpo_id,
            phenotype=phenotype.label or phenotype.hpo_id,
            frequency=phenotype.frequency,
            kind=mapped.kind if mapped else None,
            gene=disease_row.gene,
            target=target.name,
            disease_id=disease.id,
            disease=disease.name,
            reaction_terms=list(mapped.reaction_terms) if mapped else [],
            records=[
                Record("chembl", f"{molecule.name}: {', '.join(filter(None, target.action_types))} of {target.name}",
                       f"https://www.ebi.ac.uk/chembl/explore/target/{target.chembl_id}"),
                *_disease_records(disease),
                Record(disease_row.direction_source or "unknown", disease_row.direction_basis),
                Record(phenotype.source_id or "catalog", f"{phenotype.label} ({phenotype.frequency})",
                       f"https://hpo.jax.org/browse/term/{phenotype.hpo_id}"),
            ],
        )
        report.predictions.append(prediction)
        if mapped is None:
            prediction.reason = "phenotype not mapped yet (step 5)"
            continue
        if not prediction.reaction_terms:
            prediction.reason = "no reaction term survived step 5"
            continue

        if label is not None:
            match = label_match.find(label, prediction.reaction_terms)
            if match is not None:
                prediction.label_section, prediction.label_term, prediction.label_sentence = (
                    match.section, match.term, match.sentence
                )
                prediction.records.append(Record("openfda_label", f"{match.section}: {match.sentence}", label.url))

        counts: list[TermCounts] = []
        if report.drug_reports is None or not report.all_reports:
            prediction.reason = reports_problem or "openFDA reports unavailable: no report totals"
        else:
            try:
                counts = [_count(generic_name, term, report.drug_reports, report.all_reports)
                          for term in prediction.reaction_terms]
            except SourceError as error:
                prediction.reason = f"openFDA reports unavailable: {error}"
        prediction.counts = [
            asdict(item) | {"prr": item.prr, "chi_squared": item.chi_squared, "signal": item.is_signal,
                            "expected": item.expected, "query": openfda.query_url(
                                f"{openfda.drug_search(generic_name)} AND {openfda.reaction_search(item.term)}")}
            for item in counts
        ]
        signal = any(item.is_signal for item in counts)

        if prediction.label_sentence:
            prediction.verdict = "on_label"
        elif signal:
            prediction.verdict = "signal_in_reports"
            prediction.candidate_new_signal = prediction.kind == "clinical"
        elif not counts or all(item.underpowered for item in counts):
            prediction.verdict = "unknown"
            prediction.reason = prediction.reason or "too few reports for even a doubled rate to show"
        else:
            prediction.verdict = "no_signal"
    return report
