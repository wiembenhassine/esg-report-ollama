"""
Étape 0 — Validation des données STARS de Hakim (combined_esg_dataset.csv).

Chaque ligne est contrôlée avant tout calcul :
  - champs obligatoires présents (institution, version, pilier, catégorie, crédit, nom, statut) ;
  - université connue, code de crédit bien formé et cohérent avec sa catégorie ;
  - statut connu ;
  - crédit noté (statut « Complete », hors préface PRE) : score et max présents et numériques,
    max > 0, 0 <= score <= max ;
  - crédit non noté (préface PRE, « Not Applicable ») : pas de score ;
  - pas de doublon (université, crédit).

Les lignes en erreur sont écartées par facts.py : elles n'alimentent aucun chiffre du rapport.

    python -m esg.validate
"""

import csv
import re
import sys
from dataclasses import dataclass, field

from esg.config import INSTITUTIONS, RAW

CSV_PATH = RAW / "scores" / "combined_esg_dataset.csv"
REQUIRED = ["institution", "stars_version", "pillar", "category_code", "credit_code", "credit_name", "status"]
STATUSES = {"Complete", "Not Applicable", "Not Pursuing", "Pursuing"}
CODE = re.compile(r"^(AC|EN|OP|PA|IL|PRE)-\d{1,2}$")
KNOWN = {inst["name"] for inst in INSTITUTIONS.values()}


@dataclass
class RowCheck:
    line: int                       # numéro de ligne dans le fichier (en-tête = 1)
    row: dict
    kind: str = "noté"              # noté | non noté | erreur
    errors: list = field(default_factory=list)


def _num(value: str):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def check_row(line: int, row: dict, seen: set) -> RowCheck:
    c = RowCheck(line, row)
    for name in REQUIRED:
        if not (row.get(name) or "").strip():
            c.errors.append(f"champ obligatoire vide : {name}")
    if row.get("institution") and row["institution"] not in KNOWN:
        c.errors.append(f"université inconnue : {row['institution']}")
    code = (row.get("credit_code") or "").strip()
    if code and not CODE.match(code):
        c.errors.append(f"code de crédit mal formé : {code}")
    elif code and row.get("category_code") and not code.startswith(row["category_code"] + "-"):
        c.errors.append(f"code {code} incohérent avec la catégorie {row['category_code']}")
    if row.get("status") and row["status"] not in STATUSES:
        c.errors.append(f"statut inconnu : {row['status']}")
    key = (row.get("institution"), code)
    if key in seen:
        c.errors.append("doublon (université, crédit)")
    seen.add(key)

    score_raw, max_raw = (row.get("score") or "").strip(), (row.get("max") or "").strip()
    scored = row.get("status") == "Complete" and row.get("category_code") != "PRE"
    if scored:
        score, mx = _num(score_raw), _num(max_raw)
        if score is None or mx is None:
            c.errors.append(f"score ou max manquant ou non numérique (score={score_raw!r}, max={max_raw!r})")
        else:
            if mx <= 0:
                c.errors.append(f"max doit être > 0 (max={mx})")
            if score < 0:
                c.errors.append(f"score négatif ({score})")
            if score > mx:
                c.errors.append(f"score supérieur au max ({score} > {mx})")
    else:
        c.kind = "non noté"
        if score_raw:
            c.errors.append(f"crédit non noté ({row.get('status')}, {row.get('category_code')}) mais score présent")
    if c.errors:
        c.kind = "erreur"
    return c


def validate(path=CSV_PATH) -> list[RowCheck]:
    seen: set = set()
    with open(path, encoding="utf-8") as fh:
        return [check_row(i, row, seen) for i, row in enumerate(csv.DictReader(fh), start=2)]


def valid_rows(path=CSV_PATH) -> list[dict]:
    """Lignes notées et valides : les seules utilisées pour calculer des chiffres."""
    return [c.row for c in validate(path) if c.kind == "noté"]


def report(checks: list[RowCheck]) -> str:
    total = len(checks)
    n_ok = sum(c.kind == "noté" for c in checks)
    n_unscored = sum(c.kind == "non noté" for c in checks)
    n_err = sum(c.kind == "erreur" for c in checks)
    lines = [f"Validation des données : {total} lignes lues -> {n_ok + n_unscored} valides "
             f"({n_ok} notées, {n_unscored} non notées : préface ou non applicable), {n_err} en erreur"]
    for name in sorted(KNOWN):
        mine = [c for c in checks if c.row.get("institution") == name]
        lines.append(f"   {name:<38} {len(mine):>3} lignes | {sum(c.kind == 'noté' for c in mine):>3} notées | "
                     f"{sum(c.kind == 'non noté' for c in mine):>2} non notées | "
                     f"{sum(c.kind == 'erreur' for c in mine):>2} erreurs")
    for c in checks:
        if c.kind == "erreur":
            lines.append(f"   ERREUR ligne {c.line} ({c.row.get('credit_code')}) : " + " ; ".join(c.errors))
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(report(validate()))


if __name__ == "__main__":
    main()
