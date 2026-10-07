"""
Style des textes du modèle, corrigé au rendu (forme seulement, aucun fait ajouté) :
  - « l'Université » en nom commun -> « l'université » (mais « l'Université de Californie »,
    « l'Université européenne de technologie » gardent leur majuscule : ce sont des noms propres) ;
  - phrases creuses ou promotionnelles retirées (suppression de la phrase entière, comme le garde-fou).
Liste tirée des rapports réels du 5 et 6 octobre (relecture de Wiem).
"""

import re

SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")       # même découpage que guard (sans l'importer : guard utilise style)
CASE = re.compile(r"\b([Ll])'Université\b(?!\s+(?:de\s+[A-Z]|européenne|technologique|[A-Z]))")

HOLLOW = [re.compile(p, re.I) for p in (
    r"favorise la durabilité et la responsabilité",
    r"démontré sa détermination",
    r"de manière significative",
    r"est un aspect clé de (?:sa|la) stratégie",
    r"reflète la forte implication",
    r"mieux-être de l'humanité|bien commun et au mieux-être",
    r"reflète (?:son|sa|l')\s?(?:engagement|volonté|détermination)",
    r"témoigne de (?:son|sa|l')\s?(?:engagement|volonté|détermination)",
    r"engagement (?:fort|profond|indéfectible) (?:envers|en faveur)",
)]


def is_hollow(sentence: str) -> bool:
    return any(rx.search(sentence) for rx in HOLLOW)


def drop_hollow(text: str) -> str:
    out = []
    for line in text.split("\n"):
        if line.lstrip().startswith("#") or not line.strip():
            out.append(line)
            continue
        kept = [s for s in SENTENCE_END.split(line) if not is_hollow(s)]
        if kept:
            out.append(" ".join(kept))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def clean(text: str) -> str:
    return drop_hollow(CASE.sub(r"\1'université", text))
