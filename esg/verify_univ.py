"""
Contrôle par université : 10 chiffres de score tirés au hasard par rapport, comparés au CSV brut
(via esg.verify), plus 5 nombres « texte » (années, %) comparés à la ligne STARS d'origine.

    python -m esg.verify_univ          # graine aléatoire (affichée)
    python -m esg.verify_univ 2026     # rejouer le tirage du bilan
"""

import csv
import random
import re
import sys

from esg import sources, verify
from esg.config import INSTITUTIONS, OUTPUTS

TEXT_ID = re.compile(r"^([A-Z]+)(\d+)_t(\d+)_(\d+)$")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else random.randrange(10_000)
    rows = verify.csv_rows()
    print(f"Graine {seed} (rejouer : python -m esg.verify_univ {seed})\n")
    bad = 0
    for key in INSTITUTIONS:
        report = (OUTPUTS / key / f"rapport_{key}.md").read_text(encoding="utf-8")
        with open(OUTPUTS / key / "provenance.csv", encoding="utf-8") as fh:
            prov = [p for p in csv.DictReader(fh) if p["fact_id"] not in ("STARS_date", "STARS_score")]
        scores = list({p["fact_id"]: p for p in prov if not TEXT_ID.match(p["fact_id"])}.values())
        texts = list({p["fact_id"]: p for p in prov if TEXT_ID.match(p["fact_id"])}.values())
        rnd = random.Random(f"{seed}-{key}")
        print(f"## {INSTITUTIONS[key]['name']} — {len(scores)} chiffres de score, {len(texts)} nombres de texte\n")
        print("| # | Chiffre | Élément | Valeur CSV | Dans le texte | Identique |\n|---|---|---|---|---|---|")
        for i, p in enumerate(rnd.sample(scores, min(10, len(scores))), 1):
            value, how = verify.expected(key, p["fact_id"], rows)
            where = verify.anchor(p["fact_id"], p["label"])     # même ligne que son crédit ou son pilier
            in_text = any(re.search(rf"(?<![\d,]){re.escape(p['display'])}(?![\d,])", line) and where in line
                          for line in report.splitlines())
            same = value is not None and abs(verify.parse_fr(p["display"]) - value) < 0.006
            bad += not (same and in_text)
            csv_val = f"{value:g}" if value is not None else "—"
            print(f"| {i} | {p['display']} | {p['label']} | {csv_val} ({how}) | {'oui' if in_text else 'NON'} | "
                  f"{'OUI' if same and in_text else 'NON'} |")
        if texts:
            print("\n| # | Nombre | Source | Ligne STARS (extrait) | Dans le texte | Identique |\n|---|---|---|---|---|---|")
            cred = sources.credits(key)
            for i, p in enumerate(rnd.sample(texts, min(5, len(texts))), 1):
                pre, num, line_idx, k = TEXT_ID.match(p["fact_id"]).groups()
                line = cred[f"{pre}-{num}"]["lines"][int(line_idx)]
                n = sources.text_numbers(line)[int(k)]
                same = abs(verify.parse_fr(p["display"]) - n["value"]) < 0.006 and n["raw"] in line
                in_text = p["display"] in report
                bad += not (same and in_text)
                s = max(0, n["start"] - 40)
                print(f"| {i} | {p['display']} | {pre}-{num}, ligne {int(line_idx) + 1} | …{line[s:n['end'] + 20]}… | "
                      f"{'oui' if in_text else 'NON'} | {'OUI' if same and in_text else 'NON'} |")
        print()
    print("Résultat :", "aucun écart." if not bad else f"{bad} écart(s).")


if __name__ == "__main__":
    main()
