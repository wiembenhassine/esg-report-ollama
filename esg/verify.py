"""
Contrôle par échantillon : N chiffres tirés au hasard dans les rapports générés, comparés
DIRECTEMENT au CSV de Hakim (sans passer par facts.py, pour un contrôle indépendant).

    python -m esg.verify            # 10 chiffres, tirage aléatoire (graine affichée)
    python -m esg.verify 20 1234    # 20 chiffres, graine 1234 (pour rejouer le même tirage)

Pour chaque chiffre : il doit apparaître dans le texte du rapport, et sa valeur doit être
égale à celle du CSV (score ou max du crédit) ou au total recalculé ici à partir du CSV
(points, max et part d'un pilier).
"""

import csv
import random
import re
import sys

from esg.config import INSTITUTIONS, OUTPUTS, RAW

PILLAR = {"ENV": lambda c: c.startswith("OP-"),
          "SOC": lambda c: c.startswith("PA-") and int(c[3:]) >= 6,
          "GOV": lambda c: c.startswith("PA-") and int(c[3:]) <= 5,
          "CTX": lambda c: c[:3] in ("AC-", "EN-")}


def parse_fr(text: str) -> float:
    t = text.replace(" ", "").replace(" ", "").replace(" ", "").replace("%", "").replace(",", ".")
    return float(t)


def csv_rows() -> list[dict]:
    with open(RAW / "scores" / "combined_esg_dataset.csv", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def expected(key: str, fact_id: str, rows: list[dict]):
    """Valeur attendue lue dans le CSV brut (None si le fait n'est pas un score STARS)."""
    name = INSTITUTIONS[key]["name"]
    mine = [r for r in rows if r["institution"] == name and r["score"].strip()]
    if fact_id == "STARS_score":
        return None, "score global (en-tête STARS, pas dans le CSV)"
    head, _, kind = fact_id.rpartition("_")
    if head in PILLAR:
        sel = [r for r in mine if PILLAR[head](r["credit_code"])]
        pts, mx = sum(float(r["score"]) for r in sel), sum(float(r["max"]) for r in sel)
        value = {"points": pts, "max": mx, "pct": round(100 * pts / mx, 1)}[kind]
        return value, f"pilier {head} recalculé ({len(sel)} crédits du CSV)"
    code = head[:2] + "-" + head[2:] if head[:3] != "PRE" else head
    for r in mine:
        if r["credit_code"] == code:
            return float(r[kind if kind == "max" else "score"]), f"CSV : {code} colonne {kind if kind == 'max' else 'score'}"
    return None, f"{code} introuvable dans le CSV"


def anchor(fact_id: str, label: str) -> str:
    """Texte qui doit figurer sur la même ligne que le chiffre : « OP-1 — » ou « | Environnement | ».
    (« ENV » commence par « EN » : on exige un crédit complet, lettres puis chiffres.)"""
    head = fact_id.rpartition("_")[0]
    m = re.fullmatch(r"(OP|PA|AC|EN)(\d+)", head)
    if m:
        return f"{m[1]}-{m[2]} —"
    return f"| {label.split('pilier ')[-1]} |" if "pilier" in label else ""


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else random.randrange(10_000)
    rows = csv_rows()
    pool = []
    for key in INSTITUTIONS:
        report = (OUTPUTS / key / f"rapport_{key}.md").read_text(encoding="utf-8")
        with open(OUTPUTS / key / "provenance.csv", encoding="utf-8") as fh:
            for p in csv.DictReader(fh):
                if p["fact_id"] != "STARS_date":
                    pool.append((key, p, report))
    random.seed(seed)
    sample = random.sample(pool, min(n, len(pool)))
    print(f"Tirage aléatoire de {len(sample)} chiffres parmi {len(pool)} (graine {seed} ; "
          f"rejouer : python -m esg.verify {n} {seed})\n")
    print(f"| # | Rapport | Chiffre du rapport | Élément | Valeur CSV | Présent dans le texte | Identique |")
    print("|---|---|---|---|---|---|---|")
    ok_all = True
    for i, (key, p, report) in enumerate(sample, 1):
        value, how = expected(key, p["fact_id"], rows)
        shown = p["display"]
        # Le chiffre doit figurer sur la MÊME ligne que son crédit (ou son pilier), pas n'importe où.
        where = anchor(p["fact_id"], p["label"])
        in_text = any(shown in line and where in line for line in report.splitlines())
        same = value is not None and abs(parse_fr(shown) - value) < 0.006
        if value is None:
            verdict = "non comparable"
        else:
            verdict = "OUI" if same and in_text else "NON"
            ok_all &= same and in_text
        csv_val = f"{value:g}" if value is not None else "—"
        print(f"| {i} | {key} | {shown} | {p['label']} | {csv_val} ({how}) | {'oui' if in_text else 'NON'} | {verdict} |")
    print("\nRésultat : " + ("tous les chiffres comparables sont identiques au CSV." if ok_all
                            else "AU MOINS UN ÉCART — voir les lignes « NON »."))


if __name__ == "__main__":
    main()
