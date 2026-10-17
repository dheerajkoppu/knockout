"""The store interface on JSON files under data/store/, used when DATABASE_URL is not set."""

import json
import os
import re
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from knockout.config import DATA_DIR

DEFAULT_DIRECTORY = DATA_DIR / "store"


def drug_key(drug: str) -> str:
    return " ".join(drug.split()).lower()


def term_key(term: str) -> str:
    return " ".join(term.split()).upper()


def utc_iso(value: str | datetime | None = None) -> str:
    if value is None:
        moment = datetime.now(UTC)
    elif isinstance(value, datetime):
        moment = value
    else:
        moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="seconds")


class FileStore:
    kind = "files"

    def __init__(self, directory: Path | str = DEFAULT_DIRECTORY):
        self.directory = Path(directory)
        self._lock = threading.RLock()

    def _drug_path(self, folder: str, drug: str) -> Path:
        slug = re.sub(r"[^a-z0-9]+", "-", drug_key(drug)).strip("-") or "_"
        return self.directory / folder / f"{slug}.json"

    def _read(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        return json.loads(path.read_text())

    def _write(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write then rename, so a reader never sees half a file.
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
        with os.fdopen(handle, "w") as stream:
            json.dump(value, stream, indent=1, default=str)
        os.replace(temporary, path)

    def save_report(self, drug: str, report_dict: dict) -> None:
        with self._lock:
            self._write(
                self._drug_path("reports", drug),
                {"drug": drug_key(drug), "cached_at": utc_iso(), "report": report_dict},
            )

    def get_report(self, drug: str) -> dict | None:
        """The stored report with its `cached_at` time, or None."""
        with self._lock:
            stored = self._read(self._drug_path("reports", drug), None)
        if stored is None:
            return None
        return stored["report"] | {"cached_at": stored["cached_at"]}

    def add_watch(self, drug: str) -> None:
        with self._lock:
            path = self.directory / "watchlist.json"
            drugs = self._read(path, [])
            if drug_key(drug) not in drugs:
                drugs.append(drug_key(drug))
                self._write(path, drugs)

    def watchlist(self) -> list[str]:
        with self._lock:
            return list(self._read(self.directory / "watchlist.json", []))

    def save_signal_run(self, payload: dict) -> tuple[int, int]:
        """Store one watch-agent run. Returns (rows stored, new alerts), with the same rules as PostgresStore.

        An alert is a term whose latest-quarter signal was false in the previous run of this drug and is true
        in this one. The first run of a drug sets the baseline and raises none. Sending a run_id again updates
        its rows, keeps its original run_at and adds no alert twice.
        """
        drug = drug_key(payload["drug"])
        run_id = str(payload["run_id"]).strip()
        if not run_id:
            raise ValueError("run_id is empty")
        rows: dict[tuple[str, str], dict] = {}
        for item in payload.get("terms") or []:
            term = term_key(item["term"])
            if int(item["reports"]) < 0:
                raise ValueError(f"reports for {term} {item['quarter']} is negative")
            rows[(term, item["quarter"])] = {
                "term": term,
                "quarter": item["quarter"],
                "reports": int(item["reports"]),
                "prr": None if item.get("prr") is None else float(item["prr"]),
                "signal": bool(item["signal"]),
                "run_id": run_id,
            }
        with self._lock:
            path = self._drug_path("signals", drug)
            history = self._read(path, {"drug": drug, "runs": [], "rows": [], "alerts": []})
            existing = next((run for run in history["runs"] if run["run_id"] == run_id), None)
            if existing is None:
                existing = {"run_id": run_id, "run_at": utc_iso(payload["run_at"])}
                history["runs"].append(existing)
            existing["term_source"] = payload.get("term_source") or "report"
            existing["received_at"] = utc_iso()
            run_at = existing["run_at"]
            for row in rows.values():
                row["run_at"] = run_at
            history["rows"] = [
                row for row in history["rows"]
                if not (row["run_id"] == run_id and (row["term"], row["quarter"]) in rows)
            ] + list(rows.values())

            earlier = [run for run in history["runs"] if (run["run_at"], run["run_id"]) < (run_at, run_id)]
            previous = max(earlier, key=lambda run: (run["run_at"], run["run_id"]), default=None)
            new_alerts = 0
            if previous is not None:
                current_states = _latest_states(history["rows"], run_id)
                previous_states = _latest_states(history["rows"], previous["run_id"])
                alerted = {(alert["term"], alert["run_id"]) for alert in history["alerts"]}
                for term, state in sorted(current_states.items()):
                    before = previous_states.get(term)
                    if state["signal"] and before is not None and not before["signal"] and (term, run_id) not in alerted:
                        history["alerts"].append({
                            "term": term, "quarter": state["quarter"], "prr": state["prr"], "run_id": run_id,
                            "previous_run_id": previous["run_id"], "crossed_at": run_at,
                        })
                        new_alerts += 1
            self._write(path, history)
        return len(rows), new_alerts

    def _history(self, drug: str) -> dict:
        with self._lock:
            return self._read(self._drug_path("signals", drug), {"runs": [], "rows": [], "alerts": []})

    def trend(self, drug: str) -> dict:
        """Per term and quarter, the values from the latest run that reported that quarter."""
        history = self._history(drug)
        sources = {run["run_id"]: run.get("term_source", "report") for run in history["runs"]}
        latest: dict[tuple[str, str], dict] = {}
        for row in history["rows"]:
            key = (row["term"], row["quarter"])
            if key not in latest or row["run_at"] >= latest[key]["run_at"]:
                latest[key] = row
        terms: dict[str, list[dict]] = {}
        term_sources: dict[str, tuple[str, str]] = {}
        for (term, quarter), row in sorted(latest.items()):
            terms.setdefault(term, []).append(
                {"quarter": quarter, "reports": row["reports"], "prr": row["prr"], "signal": row["signal"]}
            )
            if term not in term_sources or row["run_at"] >= term_sources[term][0]:
                term_sources[term] = (row["run_at"], sources.get(row["run_id"], "report"))
        return {
            "drug": drug_key(drug),
            "terms": [
                {"term": term, "source": term_sources[term][1], "quarters": quarters}
                for term, quarters in terms.items()
            ],
            "last_run_at": max((run["run_at"] for run in history["runs"]), default=None),
        }

    def alerts(self, drug: str) -> dict:
        history = self._history(drug)
        ordered = sorted(history["alerts"], key=lambda alert: alert["term"])
        ordered.sort(key=lambda alert: alert["crossed_at"], reverse=True)
        return {
            "drug": drug_key(drug),
            "alerts": [
                {"term": alert["term"], "quarter": alert["quarter"], "prr": alert["prr"],
                 "crossed_at": alert["crossed_at"], "run_id": alert["run_id"]}
                for alert in ordered
            ],
        }


def _latest_states(rows: list[dict], run_id: str) -> dict[str, dict]:
    """Each term's row for its latest quarter within one run."""
    states: dict[str, dict] = {}
    for row in rows:
        if row["run_id"] == run_id and (row["term"] not in states or row["quarter"] > states[row["term"]]["quarter"]):
            states[row["term"]] = row
    return states
