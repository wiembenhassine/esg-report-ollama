"""Configuration centrale : chemins, institutions, modèles Ollama."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
HTML_CACHE = DATA / "html_cache"          # pages STARS brutes (non versionnées)
PROCESSED = DATA / "processed"
OUTPUTS = ROOT / "outputs"
MAPPING = ROOT / "mapping"

STARS_BASE = "https://reports.aashe.org"

# Une entrée par université. `key` sert de nom de fichier partout dans le repo.
INSTITUTIONS = {
    "berkeley": {
        "name": "University of California, Berkeley",
        "slug": "university-of-california-berkeley-ca",
        "report_date": "2025-02-19",
        "currency": "USD",
        "country": "États-Unis",
    },
    "cork": {
        "name": "University College Cork",
        "slug": "university-college-cork-national-university-of-ireland-cork-co-corcaigh",
        "report_date": "2026-03-05",
        "currency": "EUR",
        "country": "Irlande",
    },
    "tudublin": {
        "name": "Technological University Dublin",
        "slug": "technological-university-dublin-dublin",
        "report_date": "2024-12-02",
        "currency": "EUR",
        "country": "Irlande",
    },
}

CATEGORY_CODES = ("AC", "EN", "OP", "PA", "IL", "PRE")

# Ollama — tout tourne en local, aucune API payante.
OLLAMA_URL = "http://localhost:11434"
GEN_MODEL = "llama3.1:8b"
JUDGE_MODEL = "llama3.1:8b"
EMBED_MODEL = "nomic-embed-text"


def report_url(key: str) -> str:
    inst = INSTITUTIONS[key]
    return f"{STARS_BASE}/institutions/{inst['slug']}/report/{inst['report_date']}/"
