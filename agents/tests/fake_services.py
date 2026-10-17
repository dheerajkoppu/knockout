"""A stand-in Knockout API, ChEMBL, UniProt and Fetch.ai ledger on one local port. Test fixtures only.

`eculizumab_engine_output.json` is a real engine run from 17 Oct 2026 (step 5 had no Gemini key). The mapped
report below is a FIXTURE: it fills in step 5 for one phenotype with the figures verified live on 17 Oct
(86 of 54,046 eculizumab reports, 311 reports of the reaction, 20,692,690 in all, boxed warning "SERIOUS
MENINGOCOCCAL INFECTIONS"). The trend and alert rows are invented for the tests and are not data.
"""

import copy
import json
import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURE_NOTE = "FIXTURE for agent tests, not a result"


def engine_output() -> dict:
    return json.loads((FIXTURES / "eculizumab_engine_output.json").read_text())


def prr(a: int, drug: int, reaction: int, total: int) -> float:
    return (a / drug) / ((reaction - a) / (total - drug))


def chi_squared(a: int, drug: int, reaction: int, total: int) -> float:
    b, c = drug - a, reaction - a
    d = total - drug - c
    denominator = (a + b) * (c + d) * (a + c) * (b + d)
    return total * max(abs(a * d - b * c) - total / 2, 0.0) ** 2 / denominator


def mapped_report() -> dict:
    report = engine_output()
    report["_fixture"] = FIXTURE_NOTE
    report["problems"] = []
    a, drug, reaction, total = 86, 54046, 311, 20692690
    for prediction in report["predictions"]:
        if prediction["hpo_id"] != "HP:0005381":
            prediction.update(kind="laboratory", reaction_terms=[], reason="no reaction term survived step 5")
            continue
        prediction.update(
            kind="clinical",
            reaction_terms=["MENINGOCOCCAL INFECTION"],
            label_section="boxed_warning",
            label_term="MENINGOCOCCAL INFECTION",
            label_sentence="WARNING: SERIOUS MENINGOCOCCAL INFECTIONS",
            verdict="on_label",
            reason=None,
            counts=[{
                "term": "MENINGOCOCCAL INFECTION", "a": a, "drug": drug, "reaction": reaction, "all": total,
                "prr": prr(a, drug, reaction, total), "chi_squared": chi_squared(a, drug, reaction, total),
                "signal": True, "expected": drug * reaction / total, "query": "https://api.fda.gov/drug/event.json",
            }],
        )
    return report


def trend() -> dict:
    return {"drug": "eculizumab", "_fixture": FIXTURE_NOTE, "last_run_at": "2026-10-17T21:00:00Z", "terms": [
        {"term": "MENINGOCOCCAL INFECTION", "quarters": [{"quarter": "2026Q1", "reports": 3},
                                                         {"quarter": "2026Q2", "reports": 5}]},
    ]}


def alerts() -> dict:
    return {"drug": "eculizumab", "_fixture": FIXTURE_NOTE, "alerts": []}


class QuickServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer.server_bind does a reverse DNS lookup that can take half a minute on macOS
        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


class Services:
    """Routes are plain dicts so a test can break one source and watch the agents report it."""

    def __init__(self):
        self.reports: dict[str, dict] = {"eculizumab": mapped_report()}
        self.broken: set[str] = set()
        self.ledger: dict[str, dict] = {}
        self.calls: list[str] = []
        self.asi_one_prompts: list[str] = []
        self.server = QuickServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exception):
        self.server.shutdown()
        self.server.server_close()

    def route(self, path: str, query: dict[str, list[str]]) -> tuple[int, dict]:
        self.calls.append(path)
        if path.startswith("/api/") and "api" in self.broken:
            return 500, {"detail": "fixture: API broken on purpose"}
        if path == "/api/health":
            return 200, {"status": "ok", "gemini_key": False, "openfda_key": False, "store": "files"}
        parts = path.split("/")
        if path.startswith("/api/drugs/") and len(parts) == 5:
            drug, kind = unquote(parts[3]), parts[4]
            if kind == "report":
                if drug not in self.reports:
                    return 404, {"detail": f"ChEMBL has no molecule named {drug!r}"}
                return 200, self.reports[drug] | {"cached_at": "2026-10-17T21:00:00Z"}
            if kind == "trend":
                return (503, {"detail": "fixture: store down"}) if "trend" in self.broken else (200, trend())
            if kind == "alerts":
                return 200, alerts()
        if path == "/chembl/molecule.json":
            name = (query.get("pref_name__iexact") or query.get("molecule_synonyms__molecule_synonym__iexact")
                    or [""])[0].lower()
            if "pref_name__iexact" in query and name == "eculizumab":
                return 200, {"molecules": [{"molecule_chembl_id": "CHEMBL1201828", "pref_name": "ECULIZUMAB",
                                            "max_phase": "4.0", "first_approval": 2007}]}
            if "molecule_chembl_id__in" in query:
                return 200, {"molecules": [
                    {"molecule_chembl_id": "CHEMBL1201828", "pref_name": "ECULIZUMAB", "max_phase": "4.0",
                     "first_approval": 2007},
                    {"molecule_chembl_id": "CHEMBL4594316", "pref_name": "RAVULIZUMAB", "max_phase": "4.0",
                     "first_approval": 2018},
                ]}
            return 200, {"molecules": []}
        if path == "/uniprot/uniprotkb/search":
            found = "gene_exact:C5 " in (query.get("query") or [""])[0]
            return 200, {"results": [{"primaryAccession": "P01031"}] if found else []}
        if path == "/chembl/target.json":
            if (query.get("target_components__accession") or [""])[0] == "P01031":
                synonyms = [{"component_synonym": "C5", "syn_type": "GENE_SYMBOL"}]
                return 200, {"targets": [{
                    "target_chembl_id": "CHEMBL2364163", "pref_name": "Complement C5", "target_type": "SINGLE PROTEIN",
                    "organism": "Homo sapiens",
                    "target_components": [{"accession": "P01031", "target_component_synonyms": synonyms}],
                }]}
            return 200, {"targets": []}
        if path == "/chembl/target/search.json":
            return 200, {"targets": []}
        if path == "/chembl/mechanism.json":
            return 200, {"mechanisms": [
                {"molecule_chembl_id": "CHEMBL1201828", "parent_molecule_chembl_id": "CHEMBL1201828",
                 "action_type": "INHIBITOR"},
                {"molecule_chembl_id": "CHEMBL4594316", "parent_molecule_chembl_id": "CHEMBL4594316",
                 "action_type": "INHIBITOR"},
            ]}
        if path.startswith("/ledger/cosmos/tx/v1beta1/txs/"):
            transaction = self.ledger.get(parts[-1])
            return (200, transaction) if transaction else (404, {"detail": "not found"})
        return 404, {"detail": f"fixture has no route {path}"}

    def route_post(self, path: str, body: dict) -> tuple[int, dict]:
        if path == "/asi1/chat/completions":
            self.asi_one_prompts.append(body["messages"][-1]["content"])
            content = json.dumps({"drug": "Eculizumab", "protein": "C5", "effect": "meningitis"})
            return 200, {"choices": [{"message": {"content": content}}]}
        return 404, {"detail": f"fixture has no route {path}"}

    def _handler(self):
        services = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                status, body = services.route(parsed.path, parse_qs(parsed.query))
                payload = json.dumps(body, default=lambda value: None).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                request_body = json.loads(self.rfile.read(length) or b"{}")
                services.calls.append(self.path)
                status, body = services.route_post(urlparse(self.path).path, request_body)
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *arguments):
                return None

        return Handler


def without_infinity(report: dict) -> dict:
    """What the real API sends: an infinite PRR becomes null plus prr_infinite."""
    copied = copy.deepcopy(report)
    for prediction in copied["predictions"]:
        for count in prediction["counts"]:
            if isinstance(count.get("prr"), float) and math.isinf(count["prr"]):
                count["prr"], count["prr_infinite"] = None, True
    return copied
