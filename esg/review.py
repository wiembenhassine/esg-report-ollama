"""
Relecture hors pipeline (6 et 7 octobre 2026) : corrections proposées par l'assistant Claude Code (IA), à la
demande de Wiem Ben Hassine, après avoir relu les sections validées contre les textes STARS. Elles
deviennent une relecture humaine une fois validées par elle. Elles sont écrites dans `relecture/<univ>.yaml` et
appliquées par le code au moment du rendu. Le cache du modèle n'est pas modifié : on garde la trace
de ce que le modèle a écrit, et de ce que la relecture a changé.

Règles vérifiées par le code (et par les tests) :
  - chaque « avant » figure tel quel dans le texte validé de sa section ;
  - « apres » ne contient aucun chiffre tapé à la main : un nombre vient de facts.csv par un
    marqueur {{ ID }} (année ou % du texte STARS, ou score d'un crédit), comme pour le rédacteur ;
  - chaque correction donne sa raison et sa source STARS (crédit, ligne).

    python -m esg.review        # écrit outputs/relecture_humaine.md (liste lisible des corrections)
"""

import re
import sys
from functools import lru_cache

import yaml
from jinja2 import Environment, StrictUndefined

from esg import guard, markers
from esg.config import INSTITUTIONS, OUTPUTS, ROOT

FOLDER = ROOT / "relecture"
JINJA = Environment(undefined=StrictUndefined, autoescape=False)
CREDIT_MARKER = re.compile(r"(AC|EN|OP|PA|IL|PRE)(\d+)")
CODES = re.compile(r"\b(?:AC|EN|OP|PA|IL|PRE)-\d+\b|\bGRI \d+(?:-\d+)?\b|"    # codes, pas des chiffres
                   r"\bscopes? [123](?: et [123])?\b|\bISO \d{3,5}(?:-\d+)?\b")


class ReviewError(ValueError):
    pass


def marker(key: str, name: str) -> dict:
    m = CREDIT_MARKER.fullmatch(name)
    return markers.credit(key, f"{m[1]}-{m[2]}") if m else markers.text(key, name)


@lru_cache(maxsize=None)
def load(key: str) -> dict:
    """{section: [corrections]} ; lève ReviewError si une correction enfreint les règles."""
    path = FOLDER / f"{key}.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    for section, items in data.items():
        for c in items:
            for field in ("avant", "apres", "raison", "source"):
                if field not in c:
                    raise ReviewError(f"{key}/{section} : champ « {field} » manquant")
            if guard.DIGIT.search(CODES.sub(" ", guard.PLACEHOLDER.sub(" ", c["apres"]))):
                raise ReviewError(f"{key}/{section} : chiffre tapé à la main dans « {c['apres']} » "
                                  "(utilise un marqueur {{ ID }})")
            if guard.NUMBER_WORDS.search(guard.PLACEHOLDER.sub(" ", c["apres"])):
                raise ReviewError(f"{key}/{section} : nombre en lettres dans « {c['apres']} »")
    return data


def apply(key: str, section: str, text: str) -> tuple[str, list[str], list[dict]]:
    """Applique les corrections d'une section. Renvoie (texte, faits utilisés, corrections introuvables)."""
    used, missing = [], []
    for c in load(key).get(section, []):
        if c["avant"] not in text:
            missing.append(c)                      # texte régénéré depuis la relecture : à refaire
            continue
        names = guard.PLACEHOLDER.findall(c["apres"])
        mk = {n: marker(key, n) for n in names}
        new = JINJA.from_string(c["apres"]).render(**{n: m["display"] for n, m in mk.items()})
        text = text.replace(c["avant"], new, 1)
        used += [fid for m in mk.values() for fid in m["fact_ids"]]
    return text, used, missing


def count(key: str) -> tuple[int, int]:
    data = load(key)
    return sum(len(v) for v in data.values()), sum(1 for v in data.values() if v)


def md_list() -> str:
    md = ["# Relecture des rapports (hors pipeline, à valider)", "",
          "Corrections proposées par l'assistant Claude Code (IA) à la demande de Wiem Ben Hassine, après "
          "relecture des sections validées contre les textes STARS (6 octobre 2026, puis 7 octobre pour la nouvelle génération). **À valider par elle** : "
          "c'est cette validation qui en fait une relecture humaine. Elles sont appliquées par le code au rendu (`esg/review.py`) depuis "
          "`relecture/<université>.yaml` ; le texte du modèle reste dans `outputs/cache/`. "
          "« Supprimée » = la phrase est retirée sans remplacement.", ""]
    for key in INSTITUTIONS:
        data = load(key)
        if not data:
            continue
        n, s = count(key)
        md += [f"## {INSTITUTIONS[key]['name']} — {n} corrections dans {s} section(s)", ""]
        for section, items in data.items():
            if not items:
                continue
            md += [f"### {section}", "", "| # | Passage fautif | Pourquoi c'est faux | Source STARS | Correction |",
                   "|---|---|---|---|---|"]
            for i, c in enumerate(items, 1):
                fix = f"« {c['apres']} »" if c["apres"].strip() else "supprimée"
                avant = " ".join(c["avant"].split())         # une ligne de tableau
                md.append(f"| {i} | « {avant} » | {c['raison']} | {c['source']} | {fix} |")
            md.append("")
    return "\n".join(md)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    out = OUTPUTS / "relecture_humaine.md"
    out.write_text(md_list(), encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
