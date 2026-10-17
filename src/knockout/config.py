"""Paths and keys. Imported before any Helix module so Helix reads the pinned catalog copy."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
HELIX_SEED_DIR = DATA_DIR / "helix"
ORPHANET_DIR = DATA_DIR / "orphanet"
CACHE_DIR = DATA_DIR / "cache"
MAPPINGS_PATH = DATA_DIR / "mappings" / "hpo.json"

HELIX_COMMIT = "97f3704"
HELIX_RAW_URL = f"https://raw.githubusercontent.com/dheerajkoppu/helix/{HELIX_COMMIT}/data/seed"
HELIX_SEED_FILES = ("catalog.json", "SOURCES.json", "build_report.json")
ORPHANET_PRODUCT6_URL = "https://www.orphadata.com/data/xml/en_product6.xml"

load_dotenv(ROOT_DIR / ".env")
os.environ.setdefault("HELIX_SEED_DIR", str(HELIX_SEED_DIR))


def gemini_api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or None


def gemini_model() -> str | None:
    return os.environ.get("GEMINI_MODEL") or None


def openfda_api_key() -> str | None:
    return os.environ.get("OPENFDA_API_KEY") or None
