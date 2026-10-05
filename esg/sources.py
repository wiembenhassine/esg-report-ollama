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
   voir un chiffre : tout nombre du contexte est supprimé (un marqueur « [n] »,
   utilisé dans une première version, était recopié par le modèle).
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
    """Supprime les nombres (et le % qui les suit) au lieu de les remplacer par un marqueur :
    un « [n] » laissé dans le contexte était recopié par le modèle."""
    text = URL.sub("", text)
    text = re.sub(DIGITS.pattern + r"\s*(%|per ?cent\b)?", " ", text)
    text = WORDS_EN.sub(" ", text)
    text = re.sub(r"\(\s*\)", " ", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


# Années et pourcentages cités dans les textes STARS : extraits par le CODE comme faits « texte »
# (avec leur source), puis remplacés dans le contexte par un marqueur. Le modèle peut ainsi écrire
# « d'ici {{ PA2_t0_1 }} » sans jamais écrire le nombre lui-même. Les autres nombres restent supprimés.
YEAR = re.compile(r"\b(19[5-9]\d|20[0-5]\d)\b")
REF = re.compile(r"\s*\(\s*Refs?\s*[\d,\s]*\)")          # renvois « (Ref 1) » des textes STARS
PERCENT = re.compile(r"\b(\d{1,3}(?:[.,]\d+)?)\s?%")


def text_numbers(line: str) -> list[dict]:
    """Années et pourcentages d'une ligne STARS, dans l'ordre : [{start, end, kind, raw, value}]."""
    clean = URL.sub(lambda m: " " * len(m.group(0)), line)     # jamais un nombre tiré d'une URL
    found = [{"start": m.start(), "end": m.end(), "kind": "percent", "raw": m.group(0),
              "value": float(m.group(1).replace(",", "."))} for m in PERCENT.finditer(clean)]
    taken = [(f["start"], f["end"]) for f in found]
    for m in YEAR.finditer(clean):
        if not any(a <= m.start() < b for a, b in taken):
            found.append({"start": m.start(), "end": m.end(), "kind": "year", "raw": m.group(0),
                          "value": float(m.group(0))})
    return sorted(found, key=lambda f: f["start"])


def text_fact_id(code: str, line_idx: int, k: int) -> str:
    return f"{code.replace('-', '')}_t{line_idx}_{k}"


def mark_line(code: str, line_idx: int, line: str) -> tuple[str, list[str]]:
    """Ligne pour le prompt : années et % remplacés par leur marqueur, autres nombres supprimés."""
    nums = text_numbers(line)
    out, pos, used = [], 0, []
    for k, n in enumerate(nums):
        out.append(line[pos:n["start"]])
        out.append(f" QQMARK{chr(65 + k % 26) * (k // 26 + 1)}QQ ")   # jeton sans chiffre (survit au masquage)
        used.append(text_fact_id(code, line_idx, k))
        pos = n["end"]
    out.append(line[pos:])
    masked = mask_numbers("".join(out))
    for k, fid in enumerate(used):
        masked = masked.replace(f"QQMARK{chr(65 + k % 26) * (k // 26 + 1)}QQ", f"{{{{ {fid} }}}}")
    return masked, used


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


NOT_APPLICABLE = re.compile(r"marked as Not Applicable|Total adjusted for non-applicable credits", re.I)


def not_applicable(key: str, code: str) -> bool:
    """Crédit marqué « Not Applicable » sur sa page STARS (ex. IL-24 pour TU Dublin)."""
    return any(NOT_APPLICABLE.search(l) for l in credits(key).get(code, {}).get("lines", []))


def substantive_lines(key: str, code: str) -> list[str]:
    """Lignes propres à l'établissement, hors mentions « Not Applicable »."""
    return [l for l in credits(key).get(code, {}).get("lines", []) if not NOT_APPLICABLE.search(l)]


def header(key: str) -> dict:
    """Note globale, score global et date de soumission (en-tête de chaque page)."""
    for c in credits(key).values():
        qa = c["qa"]
        if "Overall Score" in qa:
            return {"rating": qa.get("Overall Rating", ""), "score": qa["Overall Score"],
                    "date": qa.get("Submission Date", "")}
    return {}
