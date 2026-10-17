"""openFDA: drug labels and FAERS adverse-event report totals."""

from dataclasses import dataclass
from urllib.parse import quote

from knockout.config import openfda_api_key
from knockout.http import get_json, retrieved_at

BASE = "https://api.fda.gov/drug"
LABEL_SECTIONS = ("boxed_warning", "warnings_and_cautions", "warnings", "precautions", "adverse_reactions")


def _url(endpoint: str, search: str | None, extra: str = "") -> tuple[str, str]:
    """The request URL and the cache key, which never contains the API key."""
    query = f"search={quote(search.replace(' ', '+'), safe='+:._()*')}" if search else ""
    public = f"{BASE}/{endpoint}.json?{query}{extra}"
    key = openfda_api_key()
    return (f"{public}&api_key={key}" if key else public), public


def drug_search(generic_name: str) -> str:
    return f'patient.drug.openfda.generic_name:"{generic_name.lower()}"'


def reaction_search(term: str) -> str:
    return f'patient.reaction.reactionmeddrapt.exact:"{term.upper()}"'


def total(search: str | None) -> int:
    """Reports matching a search. openFDA answers 404 when nothing matches, which is 0."""
    url, public = _url("event", search, "&limit=1")
    body = get_json(url, cache_key=public, not_found_ok=True)
    return int(body["meta"]["results"]["total"]) if body else 0


def total_retrieved_at(search: str | None) -> str | None:
    return retrieved_at(_url("event", search, "&limit=1")[1])


def query_url(search: str | None) -> str:
    return _url("event", search, "&limit=1")[1]


@dataclass(frozen=True)
class Label:
    set_id: str
    effective_time: str
    generic_names: tuple[str, ...]
    sections: dict[str, str]
    matched_by: str = "openfda.generic_name exact"
    retrieved_at: str | None = None

    @property
    def url(self) -> str:
        return f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={self.set_id}"


def _labels(field: str, generic_name: str) -> tuple[list[dict], str]:
    url, public = _url("label", f'{field}:"{generic_name.lower()}"', "&limit=100&sort=effective_time:desc")
    body = get_json(url, cache_key=public, not_found_ok=True)
    return (body or {}).get("results") or [], public


def label(generic_name: str) -> Label | None:
    """The most recent label for a generic name (protocol step 6, version 2).

    First a label whose harmonised openfda.generic_name is exactly the name, then one where it contains
    the name as a phrase, then, for labels openFDA has not harmonised, one whose product data elements
    name it as a phrase.
    """
    name = generic_name.strip().upper()
    harmonised, public = _labels("openfda.generic_name", generic_name)
    exact = [row for row in harmonised
             if [item.strip().upper() for item in (row.get("openfda") or {}).get("generic_name", [])] == [name]]
    candidates, matched_by = exact, "openfda.generic_name exact"
    if not candidates:
        candidates, matched_by = harmonised, "openfda.generic_name phrase"
    if not candidates:
        unharmonised, public = _labels("spl_product_data_elements", generic_name)
        candidates = [row for row in unharmonised if not (row.get("openfda") or {}).get("generic_name")]
        matched_by = "spl_product_data_elements phrase (label not harmonised by openFDA)"
    if not candidates:
        return None
    latest = max(candidates, key=lambda row: row.get("effective_time", ""))
    return Label(
        set_id=latest.get("set_id", ""),
        effective_time=latest.get("effective_time", ""),
        generic_names=tuple((latest.get("openfda") or {}).get("generic_name", [])),
        sections={section: " ".join(latest[section]) for section in LABEL_SECTIONS if latest.get(section)},
        matched_by=matched_by,
        retrieved_at=retrieved_at(public),
    )
