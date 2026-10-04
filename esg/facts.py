"""
Table des faits : la SEULE source des chiffres du rapport.

Chaque ligne = un chiffre, son identifiant de placeholder et sa provenance.
Le LLM ne reçoit que les identifiants et un niveau qualitatif calculé par le
code (« élevé », « faible »…), jamais les valeurs.

Sources :
  - scores par crédit      data/raw/scores/combined_esg_dataset.csv
  - en-tête STARS          note, score global, date (data/raw/narratives)
  - agrégats par pilier    calculés ici, formule écrite dans la colonne source
  - champs STARS           data/html_cache (si les pages authentifiées existent)

Usage :
    python -m esg.facts      -> data/processed/facts.csv
"""

import csv
import re
import sys
from functools import lru_cache

from esg import parse_fields, sources, validate
from esg.config import INSTITUTIONS, PROCESSED, RAW, report_url

FIELDS = ["fact_id", "institution", "kind", "credit_code", "label", "raw_value",
          "number", "unit", "display", "source"]

# Regroupement en piliers (repris de Hakim, combine_universities.py) — choix
# raisonné, pas une désignation officielle STARS.
PILLARS = {
    "ENV": ("Environnement", lambda c: c.startswith("OP-")),
    "SOC": ("Social", lambda c: c.startswith("PA-") and int(c[3:]) >= 6),
    "GOV": ("Gouvernance", lambda c: c.startswith("PA-") and int(c[3:]) <= 5),
    "CTX": ("Enseignement, recherche et engagement", lambda c: c[:3] in ("AC-", "EN-")),
}

UNITS_FR = {
    "megawatt-hours": "MWh", "kilowatt-hours": "kWh",
    "kilowatt-hours per square meter": "kWh/m²",
    "metric tons of co2 equivalent": "tCO2e", "metric tons": "t",
    "kilograms of co2 equivalent": "kg CO2e", "kilograms per square meter": "kg/m²",
    "cubic meters": "m³", "%": "%", "percent": "%", "weeks": "semaines",
}


def fr_number(x: float, decimals: int) -> str:
    """1234.5 -> '1 234,5' (espace fine insécable comme séparateur de milliers)."""
    s = f"{x:,.{decimals}f}"
    return s.replace(",", " ").replace(".", ",")


MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre"]


def fr_date(raw: str) -> str:
    """'Feb. 19, 2025' / 'March 5, 2026' -> '19 février 2025'."""
    m = re.match(r"([A-Za-z]+)\.?\s+(\d{1,2}),\s*(\d{4})", raw.strip())
    if not m:
        return raw
    month = next(i for i, name in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug",
                                             "sep", "oct", "nov", "dec"])
                 if m.group(1).lower().startswith(name))
    return f"{int(m.group(2))} {MONTHS_FR[month]} {m.group(3)}"


def decimals_of(raw: str) -> int:
    m = re.search(r"\.(\d+)", raw.split()[0]) if raw else None
    return len(m.group(1)) if m else 0


def credit_var(code: str) -> str:
    return code.replace("-", "")


def band(score: float, max_: float) -> str:
    """Niveau qualitatif calculé par le code ; c'est tout ce que le LLM voit d'un score."""
    if max_ <= 0:
        return "non applicable"
    r = score / max_
    if r >= 0.999:
        return "maximal (tous les points obtenus)"
    if r >= 0.75:
        return "élevé"
    if r >= 0.40:
        return "intermédiaire"
    if r > 0:
        return "faible"
    return "nul (aucun point obtenu)"


def _row(key, fact_id, kind, code, label, raw, number, unit, display, source):
    return {"fact_id": fact_id, "institution": key, "kind": kind, "credit_code": code,
            "label": label, "raw_value": raw, "number": "" if number is None else number,
            "unit": unit, "display": display, "source": source}


def build(key: str) -> list[dict]:
    rows = []
    url = report_url(key)
    name = INSTITUTIONS[key]["name"]

    head = sources.header(key)
    if head:
        sc = float(head["score"])
        rows.append(_row(key, "STARS_score", "overall", "", "Score STARS global",
                         head["score"], sc, "", fr_number(sc, decimals_of(head["score"])), url))
        rows.append(_row(key, "STARS_date", "meta", "", "Date de soumission STARS",
                         head["date"], None, "", fr_date(head["date"]), url))

    credit_rows = [r for r in validate.valid_rows() if r["institution"] == name]   # lignes en erreur écartées
    scored = {}
    for r in credit_rows:
        code = r["credit_code"]
        if not r["score"].strip() or not r["max"].strip():
            continue
        s, m = float(r["score"]), float(r["max"])
        scored[code] = (s, m)
        src = f"{url}{r['category_code']}/ ({code})"
        v = credit_var(code)
        rows.append(_row(key, f"{v}_score", "score", code, f"Points obtenus — {r['credit_name']}",
                         r["score"], s, "pts", fr_number(s, decimals_of(r["score"]) if s % 1 else 0), src))
        rows.append(_row(key, f"{v}_max", "max", code, f"Points possibles — {r['credit_name']}",
                         r["max"], m, "pts", fr_number(m, 0 if m % 1 == 0 else 2), src))

    for pid, (label, pred) in PILLARS.items():
        codes = sorted(c for c in scored if pred(c))
        if not codes:
            continue
        pts = round(sum(scored[c][0] for c in codes), 2)
        mx = round(sum(scored[c][1] for c in codes), 2)
        pct = round(100 * pts / mx, 1)
        formula = f"calcul : somme de {', '.join(codes)} (crédits notés uniquement)"
        rows.append(_row(key, f"{pid}_points", "pillar", "", f"Points obtenus — pilier {label}",
                         str(pts), pts, "pts", fr_number(pts, 2), formula))
        rows.append(_row(key, f"{pid}_max", "pillar", "", f"Points possibles — pilier {label}",
                         str(mx), mx, "pts", fr_number(mx, 0 if mx % 1 == 0 else 2), formula))
        rows.append(_row(key, f"{pid}_pct", "pillar", "", f"Part des points obtenus — pilier {label}",
                         str(pct), pct, "%", fr_number(pct, 1) + " %",
                         formula + " ; points obtenus / points possibles × 100"))

    for f in parse_fields.build(key):
        if f["number"] is None:
            continue                       # réponses Oui/Non : contexte qualitatif, pas des chiffres
        num = float(f["number"])
        unit = UNITS_FR.get(f["unit"].lower(), f["unit"])
        if "year" in f["label"].lower() and num.is_integer():
            disp = str(int(num))           # une année ne prend pas de séparateur de milliers
        else:
            disp = fr_number(num, decimals_of(f["value"])) + (f" {unit}" if unit else "")
        fid = f"{credit_var(f['credit_code'])}__{parse_fields.slug(f['label'])}"
        rows.append(_row(key, fid, "field", f["credit_code"], f["label"], f["value"], num, unit, disp,
                         f"{url} ({f['credit_code']} / {f['label']})"))

    ids = [r["fact_id"] for r in rows]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"identifiants de faits en double pour {key}: {sorted(dupes)[:5]}")
    return rows


@lru_cache(maxsize=None)
def load(key: str) -> dict[str, dict]:
    """{fact_id: ligne} pour une université (reconstruit si besoin)."""
    return {r["fact_id"]: r for r in build(key)}


def bands(key: str) -> dict[str, str]:
    """Niveau qualitatif par crédit noté et par pilier (utilisé dans les prompts)."""
    f = load(key)
    out = {}
    for fid, r in f.items():
        if r["kind"] == "score":
            m = f[fid.replace("_score", "_max")]
            out[r["credit_code"]] = band(float(r["number"]), float(m["number"]))
        elif fid.endswith("_pct"):
            out[fid[:3]] = band(float(r["number"]), 100.0)
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out = PROCESSED / "facts.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for key in INSTITUTIONS:
            rows = build(key)
            w.writerows(rows)
            kinds = {}
            for r in rows:
                kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
            print(f"{key:<9} {len(rows):>4} faits  {kinds}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
