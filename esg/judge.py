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

# Acceptation : la fidélité (part des affirmations supportées) prime ; la note globale d'un juge 8B
# est bruitée, d'où un seuil de 3/5. Les règles de forme sont déjà vérifiées par le code (lint).
ACCEPT_SCORE = 3
ACCEPT_FAITHFULNESS = 0.8

FORBIDDEN = [
    (re.compile(r"conforme? aux normes GRI|en conformité avec (les )?(normes )?GRI|in accordance with", re.I),
     "écrire « en référence aux normes GRI », jamais « conforme » ou « en conformité »"),
    (re.compile(r"n'a (pas|jamais) (réalisé|mené|conduit|effectué|procédé)[^.]{0,40}matérialité", re.I),
     "ne jamais affirmer que l'université n'a pas mené d'analyse de matérialité : écrire que ce rapport ne peut pas l'établir"),
    (re.compile(r"\bn'a (pas|jamais) (fourni|communiqué|publié|déclaré|transmis)", re.I),
     "ne pas écrire que l'université « n'a pas fourni » une information : écrire que STARS ne la collecte pas "
     "ou que ce rapport ne peut pas l'établir"),
    (re.compile(r"\b(certifié|audité|vérifié) par (un tiers|l'AASHE)", re.I),
     "les données STARS sont autodéclarées et non vérifiées : ne pas les présenter comme auditées"),
]
FR_WORDS = re.compile(r"\b(le|la|les|des|du|une|est|sont|dans|pour|avec|qui|que|par|sur|ce|cette)\b", re.I)
EN_WORDS = re.compile(r"\b(the|and|of|is|are|with|which|that|for|this|its|has|have)\b", re.I)


def lint(text: str, section_codes: list[str]) -> tuple[list[str], list[str], float]:
    """Contrôles déterministes. Renvoie (bloquants, remarques, couverture GRI).

    Bloquant = la section est rejetée avant le juge (langue, formulation interdite,
    longueur aberrante). Remarque = consigne transmise au rédacteur si le juge
    demande une nouvelle version, sans rejeter un texte fidèle pour une question de forme.
    """
    blocking, notes = [], []
    words = len(text.split())
    if words < 120 or words > 500:
        blocking.append(f"longueur aberrante ({words} mots) : vise 180 à 300 mots")
    elif not 160 <= words <= 380:
        notes.append(f"longueur de {words} mots : vise 180 à 300 mots")
    fr, en = len(FR_WORDS.findall(text)), len(EN_WORDS.findall(text))
    if en > 0.25 * max(fr, 1):
        blocking.append("une partie du texte est en anglais : rédige entièrement en français")
    for rx, msg in FORBIDDEN:
        if rx.search(text):
            blocking.append(msg)
    cited = {c for c in section_codes if re.search(rf"(?<![\d-]){re.escape(c)}(?![\d])", text)}
    coverage = len(cited) / len(section_codes) if section_codes else 1.0
    if section_codes and coverage < 0.5:
        missing = [c for c in section_codes if c not in cited][:4]
        notes.append("cite les publications GRI concernées entre parenthèses, par exemple "
                     + ", ".join(f"(GRI {c})" for c in missing))
    return blocking, notes, round(coverage, 2)


SYSTEM = """You are a strict auditor of sustainability reports. You check ONE section of a French-language
university sustainability report against its SOURCES. You never rewrite the section.

Procedure:
1. Split the section into its factual claims (at most 6, the most important ones; keep each claim short). For each claim, decide
   "supported": true only if the SOURCES state it (the VALUES table, the GRI status list, the vigilance
   points or the STARS excerpts). Names of programmes, bodies, policies or plans that do not appear in the
   sources are NOT supported. Generic framing sentences about GRI or STARS are supported.
2. List rule violations (only real ones; an empty list is normal):
   - the report must never claim compliance with GRI;
   - a missing disclosure must be described as something this report cannot establish. The wordings
     "ce rapport ne peut pas établir", "STARS ne collecte pas", "les données ne permettent pas" are the
     REQUIRED wordings and are never a violation. Saying the university failed to do something IS a violation;
   - every vigilance point given must be respected;
   - the section must not present a disclosure as fully reported when the status list says otherwise
     (the section does not have to restate every status);
   - qualitative levels (élevé, faible...) must match the VALUES table.
3. Give a score from 1 (unfaithful) to 5 (fully faithful and compliant).
4. Write "feedback": precise instructions IN FRENCH telling the writer what to remove or fix, consistent with
   the rules above (never ask to replace a required wording). Empty if score is 5.
Return JSON only."""

SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {"type": "array", "maxItems": 6, "items": {
            "type": "object",
            "properties": {"claim": {"type": "string", "maxLength": 140}, "supported": {"type": "boolean"}},
            "required": ["claim", "supported"]}},
        "rule_violations": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 200}},
        "score": {"type": "integer", "minimum": 1, "maximum": 5},
        "feedback": {"type": "string", "maxLength": 500},
    },
    "required": ["claims", "rule_violations", "score", "feedback"],
}

CLAIM_RX = re.compile(r'"claim"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"supported"\s*:\s*(true|false)')


def salvage(raw: str) -> list[dict]:
    """Récupère les affirmations complètes d'un JSON tronqué."""
    return [{"claim": c, "supported": s == "true"} for c, s in CLAIM_RX.findall(raw or "")]


def judge(section_text: str, values: list[str], statuses: list[str], cautions: list[str],
          evidence: list[str]) -> dict:
    """Audit d'une section. Ne lève jamais d'exception : un échec du juge rend un verdict « non accepté »."""
    user = (
        "SOURCES\n"
        "VALUES (inserted by code, always correct):\n" + ("\n".join(values) or "(none)") + "\n\n"
        "GRI STATUS LIST (computed by code):\n" + ("\n".join(statuses) or "(none)") + "\n\n"
        "VIGILANCE POINTS:\n" + ("\n".join(cautions) or "(none)") + "\n\n"
        "STARS EXCERPTS (numbers masked as [n]):\n" + ("\n".join(evidence) or "(none)") + "\n\n"
        "SECTION TO AUDIT:\n<<<\n" + section_text + "\n>>>"
    )
    seconds, last = 0.0, None
    for extra in ("", "\nBe brief: at most 4 claims of one short line each."):
        try:
            out = llm.chat_json([{"role": "system", "content": SYSTEM + extra}, {"role": "user", "content": user}],
                                SCHEMA, model=JUDGE_MODEL, num_predict=1100)
            seconds += out["seconds"]
            v = out["json"]
            break
        except llm.OllamaError as e:
            last = e
    else:
        v = {"claims": salvage(getattr(last, "raw", "")), "rule_violations": [], "score": 0,
             "feedback": "", "error": str(last)[:200]}
    claims = v.get("claims", [])
    faith = sum(1 for c in claims if c.get("supported")) / len(claims) if claims else 0.0
    v["faithfulness"] = round(faith, 2)
    v["seconds"] = seconds
    # Recoupement : une violation que le code sait vérifier et qui est fausse est écartée (et tracée).
    kept, discarded = [], []
    for viol in v.get("rule_violations", []):
        low = viol.lower()
        claims_compliance = re.search(r"complian|conform|accordance", low)
        attacks_required_wording = re.search(r"ne peut pas établir|cannot establish|stars ne collecte", low)
        if (claims_compliance and not FORBIDDEN[0][0].search(section_text)) or attacks_required_wording:
            discarded.append(viol)
        else:
            kept.append(viol)
    v["rule_violations"], v["discarded_violations"] = kept, discarded
    if discarded and not kept:
        v["feedback"] = ""            # la consigne reposait sur une fausse violation
    v["accepted"] = faith >= ACCEPT_FAITHFULNESS and (
        v.get("score", 0) >= ACCEPT_SCORE or bool(discarded and not kept))
    return v
