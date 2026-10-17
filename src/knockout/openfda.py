"""openFDA: drug labels and FAERS adverse-event report totals."""

from dataclasses import dataclass
from urllib.parse import quote

from knockout.config import openfda_api_key
from knockout.http import get_json

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


def query_url(search: str | None) -> str:
    return _url("event", search, "&limit=1")[1]


@dataclass(frozen=True)
class Label:
    set_id: str
    effective_time: str
    generic_names: tuple[str, ...]
    sections: dict[str, str]

    @property
    def url(self) -> str:
        return f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={self.set_id}"


def label(generic_name: str) -> Label | None:
    """The most recent label whose openFDA generic name matches."""
    url, public = _url("label", f'openfda.generic_name:"{generic_name.lower()}"', "&limit=100")
    body = get_json(url, cache_key=public, not_found_ok=True)
    if not body or not body.get("results"):
        return None
    latest = max(body["results"], key=lambda row: row.get("effective_time", ""))
    return Label(
        set_id=latest.get("set_id", ""),
        effective_time=latest.get("effective_time", ""),
        generic_names=tuple((latest.get("openfda") or {}).get("generic_name", [])),
        sections={name: " ".join(latest[name]) for name in LABEL_SECTIONS if latest.get(name)},
    )
