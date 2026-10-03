"""
Module ⑥ — Évaluation et contrôle qualité (LLM-as-judge + règles).

Le juge (Ollama, température 0, sortie JSON contrainte) reçoit la section
FINALE (avec les valeurs substituées), la table des valeurs utilisées et les
extraits STARS donnés au rédacteur. Il :
  1. découpe la section en affirmations et marque chacune « supportée » ou
     non par les sources  -> score de fidélité (faithfulness, au sens RAGAS) ;
  2. vérifie les règles de reporting (« en référence aux » GRI, pas
     d'affirmation négative sur ce que l'université n'a pas fait, points de
     vigilance respectés) ;
  3. attribue une note de 1 à 5 et rédige une consigne de correction.

S'y ajoutent des contrôles déterministes (`lint`) : langue, longueur,
formulations interdites, couverture des publications GRI de la section.
"""

import re

from esg import llm
from esg.config import JUDGE_MODEL

ACCEPT_SCORE = 4
ACCEPT_FAITHFULNESS = 0.75

FORBIDDEN = [
    (re.compile(r"conforme? aux normes GRI|en conformité avec (les )?(normes )?GRI|in accordance with", re.I),
     "écrire « en référence aux normes GRI », jamais « conforme » ou « en conformité »"),
    (re.compile(r"n'a (pas|jamais) (réalisé|mené|conduit|effectué|procédé)[^.]{0,40}matérialité", re.I),
     "ne jamais affirmer que l'université n'a pas mené d'analyse de matérialité : écrire que ce rapport ne peut pas l'établir"),
    (re.compile(r"\b(certifié|audité|vérifié) par (un tiers|l'AASHE)", re.I),
     "les données STARS sont autodéclarées et non vérifiées : ne pas les présenter comme auditées"),
]
FR_WORDS = re.compile(r"\b(le|la|les|des|du|une|est|sont|dans|pour|avec|qui|que|par|sur|ce|cette)\b", re.I)
EN_WORDS = re.compile(r"\b(the|and|of|is|are|with|which|that|for|this|its|has|have)\b", re.I)


def lint(text: str, section_codes: list[str]) -> tuple[list[str], float]:
    """Contrôles déterministes. Renvoie (problèmes, couverture GRI)."""
    problems = []
    words = len(text.split())
    if words < 100:
        problems.append(f"section trop courte ({words} mots) : vise 180 à 300 mots")
    if words > 450:
        problems.append(f"section trop longue ({words} mots) : vise 180 à 300 mots")
    fr, en = len(FR_WORDS.findall(text)), len(EN_WORDS.findall(text))
    if en > 0.25 * max(fr, 1):
        problems.append("une partie du texte est en anglais : rédige entièrement en français")
    for rx, msg in FORBIDDEN:
        if rx.search(text):
            problems.append(msg)
    cited = {c for c in section_codes if re.search(rf"(?<![\d-]){re.escape(c)}(?![\d])", text)}
    coverage = len(cited) / len(section_codes) if section_codes else 1.0
    if section_codes and not cited:
        problems.append("aucune publication GRI de la section n'est citée (ex. « GRI " + section_codes[0] + " »)")
    return problems, round(coverage, 2)


SYSTEM = """You are a strict auditor of sustainability reports. You check ONE section of a French-language
university sustainability report against its SOURCES. You never rewrite the section.

Procedure:
1. Split the section into its factual claims (at most 6, the most important ones; keep each claim short). For each claim, decide
   "supported": true only if the SOURCES state it (the VALUES table, the GRI status list, the vigilance
   points or the STARS excerpts). Names of programmes, bodies, policies or plans that do not appear in the
   sources are NOT supported. Generic framing sentences about GRI or STARS are supported.
2. List rule violations:
   - the report must say "en référence aux normes GRI", never claim compliance;
   - a missing disclosure must be described as something this report cannot establish, never as something
     the university failed to do;
   - every vigilance point given must be respected;
   - the GRI status of a disclosure must match the status list;
   - qualitative levels (élevé, faible...) must match the VALUES table.
3. Give a score from 1 (unfaithful) to 5 (fully faithful and compliant).
4. Write "feedback": precise instructions IN FRENCH telling the writer what to remove or fix. Empty if score is 5.
Return JSON only."""

SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {"type": "array", "maxItems": 6, "items": {
            "type": "object",
            "properties": {"claim": {"type": "string"}, "supported": {"type": "boolean"}},
            "required": ["claim", "supported"]}},
        "rule_violations": {"type": "array", "items": {"type": "string"}},
        "score": {"type": "integer", "minimum": 1, "maximum": 5},
        "feedback": {"type": "string"},
    },
    "required": ["claims", "rule_violations", "score", "feedback"],
}


def judge(section_text: str, values: list[str], statuses: list[str], cautions: list[str],
          evidence: list[str]) -> dict:
    user = (
        "SOURCES\n"
        "VALUES (inserted by code, always correct):\n" + ("\n".join(values) or "(none)") + "\n\n"
        "GRI STATUS LIST (computed by code):\n" + "\n".join(statuses) + "\n\n"
        "VIGILANCE POINTS:\n" + ("\n".join(cautions) or "(none)") + "\n\n"
        "STARS EXCERPTS (numbers masked as [n]):\n" + "\n".join(evidence) + "\n\n"
        "SECTION TO AUDIT:\n<<<\n" + section_text + "\n>>>"
    )
    out = llm.chat_json([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                        SCHEMA, model=JUDGE_MODEL, num_predict=500)
    v = out["json"]
    claims = v.get("claims", [])
    faith = sum(1 for c in claims if c.get("supported")) / len(claims) if claims else 0.0
    v["faithfulness"] = round(faith, 2)
    v["seconds"] = out["seconds"]
    v["accepted"] = v.get("score", 0) >= ACCEPT_SCORE and faith >= ACCEPT_FAITHFULNESS
    return v
