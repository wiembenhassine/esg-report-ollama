"""
Correspondance des crédits STARS avec GRI, TCFD et ESRS (tables écrites à la main).

- GRI  : déduit de mapping/gri_map.yaml (publications qui citent le crédit) ;
- TCFD : mapping/frameworks.yaml ;
- ESRS : mapping/frameworks.yaml.

Un crédit sans équivalent est affiché « Aucune correspondance » : rien n'est forcé.
Les crédits bonus « Innovation & Leadership » (IL) ne sont pas cartographiés.

    python -m esg.frameworks   -> outputs/correspondance_stars_gri_tcfd_esrs.csv
"""

import csv
import sys
from functools import lru_cache

import yaml

from esg import gri_index, validate
from esg.config import MAPPING, OUTPUTS

NONE = "Aucune correspondance"


@lru_cache(maxsize=None)
def load() -> dict:
    with open(MAPPING / "frameworks.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def credit_names() -> dict[str, str]:
    """Crédits cartographiés : tous les crédits hors bonus, plus les bonus présents dans frameworks.yaml (IL-24)."""
    mapped_bonus = {c for c in load()["credits"] if c.startswith("IL-")}
    names = {}
    for c in validate.validate():
        code = c.row.get("credit_code", "")
        if code and (not code.startswith("IL-") or code in mapped_bonus):
            names.setdefault(code, c.row.get("credit_name", ""))
    return names


def gri_for(code: str) -> list[str]:
    return [f"GRI {d}" for d, spec in gri_index.load_map()["disclosures"].items() if code in spec.get("credits", [])]


def table() -> list[dict]:
    m = load()
    order = {"PRE": 0, "AC": 1, "EN": 2, "OP": 3, "PA": 4}
    rows = []
    for code, name in sorted(credit_names().items(), key=lambda kv: (order.get(kv[0].split("-")[0], 9),
                                                                     int(kv[0].split("-")[1]))):
        spec = m["credits"].get(code)
        if spec is None:
            raise KeyError(f"crédit {code} absent de mapping/frameworks.yaml : à cartographier à la main")
        rows.append({
            "credit_code": code,
            "credit_name": name,
            "gri": ", ".join(gri_for(code)) or NONE,
            "tcfd": ", ".join(spec["tcfd"]) or NONE,
            "esrs": ", ".join(spec["esrs"]) or NONE,
            "note": spec.get("note", ""),
        })
    return rows


def summary(rows: list[dict]) -> str:
    n = len(rows)
    parts = [f"{fw.upper()} : {sum(r[fw] != NONE for r in rows)}/{n} crédits reliés, "
             f"{sum(r[fw] == NONE for r in rows)} sans correspondance" for fw in ("gri", "tcfd", "esrs")]
    return "Correspondance STARS -> " + " | ".join(parts)


def export() -> list[dict]:
    rows = table()
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    with (OUTPUTS / "correspondance_stars_gri_tcfd_esrs.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(summary(rows))
    return rows


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    export()


if __name__ == "__main__":
    main()
