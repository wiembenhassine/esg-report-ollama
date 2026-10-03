"""
Lecture des textes narratifs STARS (data/raw/narratives/*_credits.txt).

Deux traitements essentiels :

1. Suppression du texte d'aide STARS. Les pages de crédits mélangent les
   consignes du formulaire (« The Reporting Tool will automatically
   calculate… ») et les réponses de l'université. Les consignes sont
   identiques pour toutes les institutions : toute ligne présente chez au
   moins deux universités pour le même crédit est donc considérée comme du
   texte d'aide et retirée. Ce qui reste est propre à l'institution.

2. Masquage des nombres (`mask_numbers`). Le LLM rédacteur ne doit jamais
   voir un chiffre : tout nombre du contexte est remplacé par « [n] ».
   Il ne peut donc ni le recopier, ni l'arrondir, ni le transformer.
"""

import re
from collections import Counter
from functools import lru_cache

from esg.config import INSTITUTIONS, RAW

CREDIT_HEADER = re.compile(r"^([A-Z]{2,3}-\d+)\s+\[([A-Z]+)\]\s+(.*)$")
URL = re.compile(r"https?://\S+|www\.\S+")

# Nombres en chiffres (12, 1,234.5, 9.83 %, 2019…) et en toutes lettres (EN/FR).
DIGITS = re.compile(r"\d+(?:[.,   ]\d+)*")
NUMBER_WORDS_EN = (
    "two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty "
    "seventy eighty ninety hundred hundreds thousand thousands million millions "
    "billion billions dozen dozens half third quarter percent"
).split()
WORDS_EN = re.compile(r"\b(" + "|".join(NUMBER_WORDS_EN) + r")\b", re.IGNORECASE)


def fix_text(s: str) -> str:
    """Répare les caractères abîmés lors du scraping (apostrophes typographiques)."""
    return s.replace("�", "'").replace("’", "'").strip()


def mask_numbers(text: str) -> str:
    text = URL.sub("", text)
    text = DIGITS.sub("[n]", text)
    return WORDS_EN.sub("[n]", text)


def _parse_file(key: str) -> dict:
    """{code: {"title", "url", "qa": {question: answer}, "lines": [...]}}"""
    path = RAW / "narratives" / f"{key}_credits.txt"
    credits, cur, mode, last_q = {}, None, None, None
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, raw in enumerate(lines):
        line = raw.rstrip()
        m = CREDIT_HEADER.match(line)
        if m:
            code = m.group(1)
            url = lines[i + 1].strip() if i + 1 < len(lines) else ""
            cur = credits.setdefault(code, {"title": fix_text(m.group(3)), "url": url,
                                            "qa": {}, "lines": []})
            mode = None
            continue
        if cur is None or line.startswith("=====") or line == cur["url"]:
            continue
        if line.startswith("--- narrative ---"):
            mode = "narrative"
        elif line.startswith("Q: "):
            last_q = line[3:].strip()
        elif line.startswith("A: ") and last_q:
            cur["qa"][last_q] = line[3:].strip()
            last_q = None
        elif mode == "narrative" and line.strip():
            cur["lines"].append(fix_text(line))
    return credits


@lru_cache(maxsize=None)
def load_all() -> dict:
    """Charge les 3 fichiers et retire le texte d'aide commun."""
    parsed = {k: _parse_file(k) for k in INSTITUTIONS}
    codes = set().union(*(p.keys() for p in parsed.values()))
    for code in codes:
        seen = Counter()
        for p in parsed.values():
            seen.update(set(p.get(code, {}).get("lines", [])))
        for p in parsed.values():
            if code in p:
                p[code]["lines"] = [
                    l for l in dict.fromkeys(p[code]["lines"])
                    if seen[l] < 2 and len(URL.sub("", l).strip()) > 25
                ]
    return parsed


def credits(key: str) -> dict:
    return load_all()[key]


def header(key: str) -> dict:
    """Note globale, score global et date de soumission (en-tête de chaque page)."""
    for c in credits(key).values():
        qa = c["qa"]
        if "Overall Score" in qa:
            return {"rating": qa.get("Overall Rating", ""), "score": qa["Overall Score"],
                    "date": qa.get("Submission Date", "")}
    return {}
