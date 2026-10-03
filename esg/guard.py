"""
Garde-fou des chiffres — contrôle déterministe, sans LLM.

Deux contrôles :

1. `check_draft` (AVANT substitution) : le texte écrit par le LLM ne doit
   contenir AUCUN nombre, ni en chiffres ni en lettres. Seuls sont admis :
     - les placeholders connus, sous la forme stricte {{ IDENTIFIANT }}
       (pas de filtre ni d'expression : le LLM ne peut pas calculer) ;
     - les références qui contiennent des chiffres mais ne sont pas des
       données : « GRI 305-1 », « publication 2-7 », codes de crédits
       STARS (« OP-6 »), « champ d'application 1 » / « Scope 2 ».

2. `check_rendered` (APRÈS substitution) : chaque nombre du texte final doit
   provenir d'un fait substitué. Sinon la section est rejetée.
"""

import re

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z][A-Za-z0-9_]*)\s*\}\}")
ANY_TEMPLATE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.S)

# Références autorisées (non des données).
ALLOWED_REFS = [
    re.compile(r"\bGRI\s?\d{1,3}(?:[-‑–]\d{1,2}(?:-[a-z](?:-[ivx]+)?)?)?(?:\s?(?:et|à|,)\s?\d{1,3}-\d{1,2})*", re.I),
    re.compile(r"\b(?:publications?|disclosures?|exigences?)\s+\d{1,3}-\d{1,2}(?:\s?(?:et|à|,)\s?\d{1,3}-\d{1,2})*", re.I),
    re.compile(r"\b(?:AC|EN|OP|PA|IL|PRE)[-‑]\d{1,2}\b"),
    re.compile(r"\b(?:scopes?|champs? d'application)\s?[123](?:\s?(?:et|,)\s?[123])*\b", re.I),
    re.compile(r"\bSTARS\s?[23]\.\d\b|\bv[23]\.\d\b"),
    re.compile(r"\b(?:t|kg\s?)?CO[2₂](?:e|-?éq)?\b|\bm[²³]\b", re.I),
]

DIGIT = re.compile(r"\d")
NUMBER_WORDS = re.compile(
    r"\b(deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|treize|quatorze|quinze|seize|"
    r"vingt|vingtaine|trente|quarante|cinquante|soixante|cent|centaine|centaines|mille|milliers?|"
    r"millions?|milliards?|douzaine|moitié|quart|pour cent|"
    r"two|three|four|five|six|seven|eight|nine|ten|twenty|hundred|thousand|million|billion|half|percent)\b",
    re.I)


def strip_refs(text: str) -> str:
    for rx in ALLOWED_REFS:
        text = rx.sub(" ", text)
    return text


def check_draft(text: str, allowed: set[str]) -> list[str]:
    """Liste des violations (vide = texte accepté)."""
    problems = []
    used = PLACEHOLDER.findall(text)
    for name in sorted(set(used) - allowed):
        problems.append(f"placeholder inconnu {{{{ {name} }}}} : utilise uniquement ceux de la liste")
    rest = PLACEHOLDER.sub(" ", text)
    for bad in ANY_TEMPLATE.findall(rest):
        problems.append(f"syntaxe interdite {bad!r} : seul {{{{ IDENTIFIANT }}}} est permis, sans calcul ni filtre")
    rest = ANY_TEMPLATE.sub(" ", rest)
    for name in sorted(allowed, key=len, reverse=True):         # placeholder mal écrit
        rx = re.compile(r"\{?\s*\b" + re.escape(name) + r"\b\s*\}?")
        if rx.search(rest):
            problems.append(f"placeholder mal écrit : écris exactement {{{{ {name} }}}} (doubles accolades)")
            rest = rx.sub(" ", rest)
    rest = strip_refs(rest)
    for m in re.finditer(r"[^\s]*\d[^\s]*", rest):
        problems.append(f"chiffre écrit directement : {m.group(0)!r}")
    for m in NUMBER_WORDS.finditer(rest):
        problems.append(f"nombre écrit en lettres : {m.group(0)!r}")
    return problems


FR_NUMBER = re.compile(r"\d{1,3}(?:[   ]\d{3})*(?:,\d+)?|\d+(?:,\d+)?")


def numbers_in(text: str) -> list[str]:
    return [m.group(0) for m in FR_NUMBER.finditer(strip_refs(text))]


def check_rendered(text: str, substituted: dict[str, str]) -> list[str]:
    """Chaque nombre du texte final doit apparaître dans une valeur substituée."""
    allowed = set()
    for disp in substituted.values():
        allowed.update(numbers_in(disp))
    return [f"nombre non traçable dans le texte final : {n!r}"
            for n in numbers_in(text) if n not in allowed]
