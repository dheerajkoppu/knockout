"""Source failures: the reason must say a source failed, and no API key may reach a report."""

from types import SimpleNamespace

import httpx
import pytest

from knockout import chembl, engine, http, mapping, openfda
from knockout.mapping import TermMapping


class RateLimited:
    def get(self, url):
        return httpx.Response(429, text="limit", request=httpx.Request("GET", url))


@pytest.fixture
def rate_limited_openfda(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENFDA_API_KEY", "FAKEKEY123")
    monkeypatch.setattr(http, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(http, "_client", RateLimited())
    monkeypatch.setattr(http.time, "sleep", lambda seconds: None)


def test_a_rate_limited_openfda_call_never_puts_the_key_in_the_error(rate_limited_openfda):
    with pytest.raises(http.SourceError) as caught:
        openfda.total(openfda.drug_search("eculizumab"))
    assert "FAKEKEY123" not in str(caught.value)
    assert "api_key=" not in str(caught.value)
    assert "HTTP 429" in str(caught.value)


def test_source_error_scrubs_any_key_it_is_given():
    error = http.SourceError("https://example.invalid/models?pageSize=1000&key=SECRETVALUE: HTTP 500")
    assert "SECRETVALUE" not in str(error)


def _stub_chain(monkeypatch):
    molecule = chembl.Molecule("CHEMBL_TEST", "Testmab", 4.0, "Antibody")
    monkeypatch.setattr(chembl, "resolve", lambda query: molecule)

    def targets(report, molecule):
        row = engine.TargetRow("CHEMBL_T", "Test protein", "P00000", "lowers", ["INHIBITOR"])
        report.targets = [row]
        return [row]

    disease = SimpleNamespace(id="test-deficiency", name="Test deficiency", provenance=[])
    phenotype = SimpleNamespace(hpo_id="HP:0000001", label="Test infection", frequency="2/2", source_id="hpo")
    disease_row = engine.DiseaseRow("test-deficiency", "Test deficiency", "TEST", "decreased_activity",
                                    "iuis", "stated", "use", 1)
    monkeypatch.setattr(engine, "_targets", targets)
    monkeypatch.setattr(engine, "_diseases", lambda report, target: [(disease_row, disease, [phenotype])])
    mapped = TermMapping("HP:0000001", "Test infection", "clinical", ("TEST REACTION",), ())
    monkeypatch.setattr(mapping, "ensure", lambda terms: {"HP:0000001": mapped})
    monkeypatch.setattr(openfda, "label", lambda name: None)


def test_failed_report_totals_give_a_source_failure_reason_not_too_few_reports(rate_limited_openfda, monkeypatch):
    _stub_chain(monkeypatch)
    report = engine.predict("testmab").to_dict()
    prediction = report["predictions"][0]
    assert prediction["verdict"] == "unknown"
    assert prediction["counts"] == []
    assert prediction["reason"].startswith("openFDA reports unavailable")
    text = str(report)
    assert "FAKEKEY123" not in text
    assert "api_key=" not in text
