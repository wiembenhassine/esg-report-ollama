"""
Marqueurs « complets » : chaque marqueur est remplacé par une expression qui dit ce que mesure
le chiffre, par exemple {{ EN5 }} -> « 4,5 points STARS sur 8 au crédit EN-5, niveau intermédiaire ».

Pourquoi : avec des marqueurs nus ({{ EN5_score }} -> « 4,5 »), le modèle plaçait de vrais
chiffres du CSV dans de faux contextes (« 4,5 étudiants sur 8 », « d'ici 6 »). Un marqueur
complet ne peut plus devenir un effectif ou une année, et guard.misuse() refuse les contextes
interdits.

Chaque marqueur est un dict :
  label     ce que le modèle voit (sans aucun chiffre)
  display   ce que le code écrit à sa place
  kind      credit | pillar | overall | date | field | text
  level     niveau qualitatif (maximal, élevé, intermédiaire, faible, nul) ou ""
  fact_ids  faits de facts.csv utilisés (provenance)
"""

from functools import lru_cache

import yaml

from esg import facts
from esg.config import MAPPING

PILLARS = {"ENV": "Environnement", "SOC": "Social", "GOV": "Gouvernance",
           "CTX": "Enseignement, recherche et engagement"}
LEVELS = ("maximal", "élevé", "intermédiaire", "faible", "nul")


@lru_cache(maxsize=None)
def labels_fr() -> dict[str, str]:
    with open(MAPPING / "credits_fr.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def level_word(band: str) -> str:
    return band.split(" ")[0] if band else ""


def credit(key: str, code: str) -> dict | None:
    f = facts.load(key)
    v = facts.credit_var(code)
    if f"{v}_score" not in f:
        return None
    s, m = f[f"{v}_score"], f[f"{v}_max"]
    level = level_word(facts.bands(key).get(code, ""))
    name_en = s["label"].split("— ", 1)[-1]
    name_fr = labels_fr().get(code, name_en)
    return {
        "label": f"score STARS du crédit {code} {name_fr} ({name_en})",
        "display": f"{s['display']} points STARS sur {m['display']} au crédit {code}, niveau {level}",
        "kind": "credit", "level": level, "code": code, "fact_ids": [f"{v}_score", f"{v}_max"],
    }


def pillar(key: str, pid: str) -> dict | None:
    f = facts.load(key)
    if f"{pid}_pct" not in f:
        return None
    level = level_word(facts.bands(key).get(pid, ""))
    return {
        "label": f"part des points STARS obtenus dans le pilier {PILLARS[pid]}",
        "display": (f"{f[pid + '_pct']['display']} des points STARS du pilier {PILLARS[pid]} "
                    f"({f[pid + '_points']['display']} sur {f[pid + '_max']['display']}), niveau {level}"),
        "kind": "pillar", "level": level, "code": "",
        "fact_ids": [f"{pid}_pct", f"{pid}_points", f"{pid}_max"],
    }


def overall(key: str) -> dict:
    f = facts.load(key)
    return {"label": "score STARS global de l'établissement",
            "display": f"un score STARS global de {f['STARS_score']['display']}",
            "kind": "overall", "level": "", "code": "", "fact_ids": ["STARS_score"]}


def date(key: str) -> dict:
    f = facts.load(key)
    return {"label": "date de soumission du rapport STARS", "display": f["STARS_date"]["display"],
            "kind": "date", "level": "", "code": "", "fact_ids": ["STARS_date"]}


def field(key: str, fid: str) -> dict:
    r = facts.load(key)[fid]
    return {"label": f"valeur STARS « {r['label']} » ({r['credit_code']})", "display": r["display"],
            "kind": "field", "level": "", "code": r["credit_code"], "fact_ids": [fid]}


def describe(name: str, mk: dict) -> str:
    """Ligne de prompt pour le rédacteur : sens du marqueur, jamais sa valeur."""
    shape = {
        "credit": f"le code écrira « … points STARS sur … au crédit {mk['code']}, niveau {mk['level']} »",
        "pillar": f"le code écrira « … % des points STARS du pilier … (… sur …), niveau {mk['level']} »",
        "overall": "le code écrira « un score STARS global de … »",
        "date": "le code écrira une date complète (jour, mois, année)",
        "field": "le code écrira la valeur et son unité",
        "text": "le code écrira la valeur exacte citée dans le texte STARS",
    }[mk["kind"]]
    return f"- {{{{ {name} }}}} : {mk['label']} — {shape}"
