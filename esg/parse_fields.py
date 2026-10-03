"""
Extraction des champs STARS (valeurs chiffrées et réponses Oui/Non) depuis
les pages de crédits téléchargées par `esg.fetch`.

Le parseur de Hakim ne gardait que les lignes de tableau à exactement deux
cellules : les vraies valeurs tombaient ailleurs et étaient perdues
(CLAUDE.md de Hakim, §6.5). Ici on ne dépend pas de la structure HTML :
la page est convertie en lignes de texte, et chaque « libellé » est associé
à la ligne de valeur qui le suit.

Une valeur est reconnue si elle est :
  - un nombre, éventuellement suivi d'une unité (« 78,414.00 Megawatt-hours ») ;
  - une réponse fermée (Yes / No / Not Applicable…) ;
  - un texte court après un libellé terminé par « ? » ou « : ».

Diagnostic sur une page réelle :
    python -m esg.parse_fields berkeley OP-5
"""

import csv
import re
import sys

from bs4 import BeautifulSoup

from esg.config import HTML_CACHE, INSTITUTIONS, PROCESSED

NUMBER_VALUE = re.compile(r"^-?\d[\d,]*(?:\.\d+)?\s*(%|[A-Za-z][A-Za-z0-9 /²³\-().,]*)?$")
CLOSED_VALUES = {"yes", "no", "not applicable", "unknown", "not pursuing", "n/a"}
SKIP = re.compile(
    r"^(overall rating|overall score|submission date|status|score|points|"
    r"the information presented here|the reporting tool will automatically)", re.I)


def page_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    main = soup.find(id="main") or soup.find("main") or soup.body or soup
    text = main.get_text("\n")
    return [re.sub(r"\s+", " ", l).strip() for l in text.splitlines() if l.strip()]


def is_label(line: str) -> bool:
    return (8 <= len(line) <= 220 and not NUMBER_VALUE.match(line)
            and line.lower() not in CLOSED_VALUES and not SKIP.match(line))


def parse_value(line: str):
    """Renvoie (valeur, nombre, unité) ou None si la ligne n'est pas une valeur."""
    if line.lower() in CLOSED_VALUES:
        return line, None, ""
    m = NUMBER_VALUE.match(line)
    if m:
        num = float(line.split()[0].replace(",", "").rstrip("%"))
        unit = (m.group(1) or "").strip()
        return line, num, unit
    return None


def extract_fields(html: str) -> list[dict]:
    lines = page_lines(html)
    fields, seen = [], set()
    for i, line in enumerate(lines[:-1]):
        if not is_label(line):
            continue
        parsed = parse_value(lines[i + 1])
        if parsed is None and line.endswith(("?", ":")) and len(lines[i + 1]) <= 160 \
                and not is_label_like_question(lines[i + 1]):
            parsed = (lines[i + 1], None, "")
        if parsed is None:
            continue
        label = line.rstrip(":").strip()
        if label in seen:
            continue
        seen.add(label)
        value, num, unit = parsed
        fields.append({"label": label, "value": value, "number": num, "unit": unit})
    return fields


def is_label_like_question(line: str) -> bool:
    return line.endswith("?")


def slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return s[:60]


def build(key: str) -> list[dict]:
    """Lignes de faits « field » pour une université (vide si pas de cache)."""
    folder = HTML_CACHE / key
    rows = []
    if not folder.exists():
        return rows
    for page in sorted(folder.glob("*.html")):
        code = page.stem
        for f in extract_fields(page.read_text(encoding="utf-8")):
            rows.append({"credit_code": code, **f})
    return rows


def main(args: list[str]) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(args) == 2:                       # diagnostic d'une page
        key, code = args
        html = (HTML_CACHE / key / f"{code}.html").read_text(encoding="utf-8")
        print("---- lignes de texte ----")
        for l in page_lines(html):
            print("  ", l[:150])
        print("\n---- champs reconnus ----")
        for f in extract_fields(html):
            print(f"  {f['label'][:80]!r} -> {f['value']!r}")
        return
    PROCESSED.mkdir(parents=True, exist_ok=True)
    for key in INSTITUTIONS:
        rows = build(key)
        out = PROCESSED / f"fields_{key}.csv"
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["credit_code", "label", "value", "number", "unit"])
            w.writeheader()
            w.writerows(rows)
        print(f"{key}: {len(rows)} champs -> {out.name}")


if __name__ == "__main__":
    main(sys.argv[1:])
