"""
Assistant de questions-réponses sur les données STARS (Ollama, en local).

    python -m esg.chat                                  # conversation (taper « quitter » pour sortir)
    python -m esg.chat "Cork ou TU Dublin : qui gère le mieux ses déchets ?"

Mêmes règles que les rapports :
  - réponse UNIQUEMENT à partir des données (scores STARS + extraits des rapports STARS) ;
  - le modèle n'écrit AUCUN chiffre : il utilise des marqueurs {{ ... }} que le code remplace
    par les valeurs de facts.csv ; le garde-fou retire toute phrase contenant un nombre écrit
    par le modèle ;
  - comparaison automatique quand plusieurs universités sont citées (ou aucune) ;
  - « Information non disponible dans les données STARS. » quand la donnée n'existe pas.
    Ce cas est d'abord détecté par le CODE (aucun crédit pertinent, ou valeur physique
    demandée — tonnes, MWh, m³… — que le jeu de données ne contient pas), puis par le modèle.
"""

import re
import sys
import unicodedata

from jinja2 import Environment, StrictUndefined

from esg import facts, guard, llm, markers, rag, sources
from esg.config import INSTITUTIONS

NOT_AVAILABLE = "Information non disponible dans les données STARS."
JINJA = Environment(undefined=StrictUndefined, autoescape=False)
SHORT = {"berkeley": "Berkeley", "cork": "Cork", "tudublin": "TU Dublin"}

# Reconnaissance par MOTS ENTIERS, en minuscules et sans accents (voir words()). L'ancienne version
# cherchait des morceaux de mots : « tud » trouvait TU Dublin dans « étudiants », « diversit » la
# diversité ethnique dans « biodiversité », « plan » le plan stratégique dans « planté », etc.
ALIASES = {  # université -> (mots, expressions)
    "berkeley": ({"berkeley", "californie", "california", "ucb"}, []),
    "cork": ({"cork", "ucc"}, ["university college cork"]),
    "tudublin": ({"dublin", "tud", "tudublin"}, ["technological university"]),
}

# Sujets -> crédits STARS (table écrite à la main) : (mots exacts, expressions, crédits).
TOPICS = [
    ({"energie", "energies", "energetique", "energetiques", "electricite", "electrique", "electriques"}, [],
     ["OP-5"]),
    ({"emission", "emissions", "carbone", "ges", "co2", "climat", "climatique", "climatiques"},
     ["gaz a effet de serre"], ["OP-6"]),
    ({"eau", "eaux", "hydrique", "hydriques"}, [], ["OP-3"]),
    ({"dechet", "dechets", "recyclage", "recycler", "recycle", "recycles", "compost", "compostage"}, [],
     ["OP-12", "OP-11"]),
    ({"achat", "achats", "fournisseur", "fournisseurs", "approvisionnement", "approvisionnements"}, [],
     ["OP-9", "OP-10"]),
    ({"alimentation", "aliment", "aliments", "restauration", "nourriture", "repas", "cantine"}, [],
     ["OP-7", "OP-8"]),
    ({"batiment", "batiments", "construction", "constructions", "immobilier"}, [], ["OP-1", "OP-2"]),
    ({"transport", "transports", "deplacement", "deplacements", "mobilite", "velo", "velos", "navette",
      "navettes"}, [], ["OP-14", "OP-13"]),
    ({"avion", "avions", "aerien", "aeriens", "aerienne", "aeriennes", "voyage", "voyages"}, [], ["OP-15"]),
    ({"biodiversite", "ecosysteme", "ecosystemes", "pesticide", "pesticides", "faune", "flore"},
     ["espaces verts", "espace vert"], ["IL-24", "OP-4"]),
    ({"gouvernance", "conseil", "representation"}, [], ["PA-3", "PA-1"]),
    ({"plan", "plans", "planification", "planifier", "engagement", "engagements", "objectif", "objectifs",
      "strategie", "strategique"}, [], ["PA-2"]),
    ({"investissement", "investissements", "dotation", "placement", "placements", "portefeuille"}, [],
     ["PA-4", "PA-5"]),
    ({"diversite", "inclusion", "ethnique", "ethniques", "racial", "raciale", "raciales", "raciaux"}, [],
     ["PA-7", "PA-6"]),
    ({"genre", "parite", "femme", "femmes"}, [], ["PA-8"]),
    ({"salaire", "salaires", "remuneration", "remunerations", "paie"}, ["living wage"], ["PA-13"]),
    ({"sante", "securite"}, ["bien etre"], ["PA-11"]),
    ({"syndicat", "syndicats", "syndical", "reclamation", "reclamations", "lanceur", "lanceurs"},
     ["droits des salaries"], ["PA-12"]),
    ({"reussite", "accessibilite", "bourse", "bourses"}, ["frais de scolarite"], ["PA-9", "PA-10"]),
    ({"cours", "enseignement", "enseignements", "programme", "programmes", "cursus"}, [],
     ["AC-1", "AC-2", "AC-3"]),
    ({"recherche", "recherches", "chercheur", "chercheurs"}, [], ["AC-6", "AC-7"]),
    ({"communaute", "communautes", "communautaire", "communautaires", "partenariat", "partenariats", "civique",
      "benevolat", "benevole", "benevoles"}, [], ["EN-5", "EN-6"]),
]
PILLAR_WORDS = {"pilier", "piliers", "global", "globale", "classement", "meilleur", "meilleure", "environnement",
                "environnemental", "social", "sociale", "gouvernance", "performance", "resultat", "resultats",
                "comparer", "compare", "comparaison", "score", "scores", "note", "notes"}
GENERAL_WORDS = {"pilier", "piliers", "global", "globale", "classement"}
PHYSICAL = re.compile(r"tonnes?|tco2|\bt ?co2|mwh|kwh|gwh|\bm3\b|m³|litres?|mégalitres?|euros?|dollars?|€|\$|"
                      r"budget|combien d'étudiants|nombre d'(étudiants|employés|salariés)|effectifs?", re.I)
RATING = re.compile(r"\b(platinum|gold|silver|bronze|reporter|platine|or|argent)\b", re.I)

SYSTEM = """Tu es l'assistant ESG d'un projet universitaire. Tu réponds en français, en trois à six phrases,
UNIQUEMENT à partir des DONNÉES et des EXTRAITS fournis.

RÈGLES ABSOLUES
- N'écris aucun nombre (ni chiffre, ni nombre en lettres, ni année, ni pourcentage). Pour citer une valeur,
  recopie exactement son marqueur, par exemple « Cork obtient {{ cork_OP12 }}. » Le code le remplace par une
  expression complète (« … points STARS sur … au crédit OP-12, niveau … ») : n'ajoute ni « points », ni « % »,
  ni niveau autour, et ne l'emploie jamais comme date, quantité ou effectif.
- Si la question porte sur une information absente des DONNÉES et des EXTRAITS, commence ta réponse par
  « Information non disponible dans les données STARS. » puis dis brièvement ce qui est disponible.
- N'invente aucun programme, chiffre ou fait. Pour comparer, utilise les niveaux fournis (maximal, élevé,
  intermédiaire, faible, nul) et les marqueurs.
- La note STARS (Platinum, Gold…) est la note GLOBALE de l'université : ne la relie jamais au score d'un crédit.
- Rappelle, si tu compares des universités, que les scores STARS sont autodéclarés et que les périmètres diffèrent."""


def words(text: str) -> list[str]:
    """Mots de la question, en minuscules et sans accents : « Biodiversité » -> « biodiversite »."""
    t = unicodedata.normalize("NFKD", text.replace("’", "'").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.findall(r"[a-z0-9]+", t)


def _matches(tokens: list[str], exact: set, phrases: list) -> bool:
    joined = f" {' '.join(tokens)} "
    return bool(exact & set(tokens)) or any(f" {p} " in joined for p in phrases)


def institutions(question: str) -> list[str]:
    tokens = words(question)
    found = [k for k, (exact, phrases) in ALIASES.items() if _matches(tokens, exact, phrases)]
    return found or list(INSTITUTIONS)


def credits_for(question: str) -> list[str]:
    tokens = words(question)
    out = []
    for exact, phrases, codes in TOPICS:
        if _matches(tokens, exact, phrases):
            out += [c for c in codes if c not in out]
    return out[:4]


def wants_pillars(question: str, credits: list[str]) -> bool:
    tokens = set(words(question))
    return bool(tokens & PILLAR_WORDS) and (not credits or bool(tokens & GENERAL_WORDS))


def values_for(keys: list[str], credits: list[str], pillars: bool) -> dict[str, dict]:
    """Marqueurs complets (voir esg/markers.py), préfixés par l'université : cork_OP12, tudublin_ENV…"""
    vals = {}
    for key in keys:
        for c in credits:
            mk = markers.credit(key, c)
            if mk:
                vals[f"{key}_{facts.credit_var(c)}"] = dict(mk, label=f"{SHORT[key]} — {mk['label']}")
        if pillars or not credits:
            for pid in markers.PILLARS:
                mk = markers.pillar(key, pid)
                if mk:
                    vals[f"{key}_{pid}"] = dict(mk, label=f"{SHORT[key]} — {mk['label']}")
            mk = markers.overall(key)
            vals[f"{key}_STARS_score"] = dict(mk, label=f"{SHORT[key]} — {mk['label']}")
    return vals


def missing_for(keys: list[str], credits: list[str], vals: dict) -> list[tuple[str, str]]:
    """(université, crédit) demandés mais sans score pour cette université."""
    return [(k, c) for k in keys for c in credits if f"{k}_{facts.credit_var(c)}" not in vals]


def build_prompt(question: str, keys: list[str], credits: list[str], vals: dict, evidence: list[dict]) -> str:
    lines = [markers.describe(n, mk) for n, mk in vals.items()]
    ratings = "; ".join(f"{SHORT[k]} : note STARS globale « {sources.header(k).get('rating', '')} »"
                        for k in keys)
    missing = [f"{SHORT[k]} : {c} {markers.labels_fr().get(c, '')} — aucune donnée"
               for k, c in missing_for(keys, credits, vals)]
    parts = [f"QUESTION : {question}", f"UNIVERSITÉS CONCERNÉES : {ratings}.",
             "DONNÉES (marqueurs à recopier tels quels, sans rien autour) :\n" + ("\n".join(lines) or "(aucune)")]
    if missing:
        parts.append("CRÉDITS SANS DONNÉE : " + "; ".join(missing))
    parts.append("EXTRAITS DES RAPPORTS STARS (anglais ; années et % remplacés par des marqueurs recopiables, "
                 "autres nombres retirés) :\n"
                 + ("\n".join(f"[{SHORT[p['inst']]} {p['credit']}] {p['text']}" for p in evidence) or "(aucun)"))
    sigles = guard.glossary_lines(*(p["text"] for p in evidence))
    if sigles:
        parts.append("SIGLES (ne développe aucun autre sigle) :\n" + "\n".join(sigles))
    return "\n\n".join(parts)


def fallback(vals: dict) -> str:
    """Réponse écrite par le code quand le texte du modèle n'est pas utilisable."""
    if not vals:
        return NOT_AVAILABLE
    rows = [f"- {mk['label'].split(' — ', 1)[0]} : {mk['display']}" for mk in vals.values()]
    return "Voici les données STARS disponibles sur ce sujet :\n" + "\n".join(rows)


def answer(question: str, *, log=print) -> dict:
    keys = institutions(question)
    credits = credits_for(question)
    physical = bool(PHYSICAL.search(question))
    # Les piliers ne sont ajoutés que pour une question générale (sinon le prompt s'alourdit sur CPU).
    pillars = wants_pillars(question, credits)
    if not credits and not pillars:
        return {"text": NOT_AVAILABLE + " Aucun crédit STARS ne correspond à cette question.",
                "keys": keys, "credits": [], "source": "code"}

    vals = values_for(keys, credits, pillars)
    ix = rag.get_index()
    evidence = []
    for k in keys:
        raw = ix.evidence(k, credits, question, k=3, max_chars=900) if credits else []
        items, _, text_markers = markers.evidence_markers(k, raw, max_chars=450)
        evidence += items
        vals |= {f"{k}_{fid}": dict(mk, label=f"{SHORT[k]} — {mk['label']}") for fid, mk in text_markers.items()}
        for p in items:                              # marqueurs préfixés par l'université, comme les autres
            for fid in text_markers:
                p["text"] = p["text"].replace(f"{{{{ {fid} }}}}", f"{{{{ {k}_{fid} }}}}")
    out = llm.chat([{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": build_prompt(question, keys, credits, vals, evidence)}],
                   temperature=0.2, num_predict=320)
    draft = guard.tidy(out["text"])
    allowed = set(vals)
    # Le code retire toute phrase qui relie le score d'un crédit à la note globale (Platinum, Gold…).
    kept, removed = [], []
    for sentence in guard.SENTENCE_END.split(draft):
        credit_markers = [n for n in guard.PLACEHOLDER.findall(sentence) if vals.get(n, {}).get("kind") == "credit"]
        (removed if credit_markers and RATING.search(sentence) else kept).append(sentence)
    draft = " ".join(kept).strip()
    if guard.check_draft(draft, allowed, vals):
        draft, more = guard.repair(draft, allowed, vals)
        removed += more
    if not draft or guard.check_draft(draft, allowed, vals):
        text, source = fallback(vals), "code (texte du modèle rejeté par le garde-fou)"
    else:
        used = {n: vals[n]["display"] for n in guard.PLACEHOLDER.findall(draft)}
        text = JINJA.from_string(draft).render(**used)
        assert not guard.check_rendered(text, used), "nombre non traçable"
        source = "modèle (chiffres insérés par le code)"
    if physical and NOT_AVAILABLE not in text:
        text = (NOT_AVAILABLE + " Le jeu de données contient les scores STARS, pas les valeurs physiques "
                "(tonnes, MWh, m³…). " + text)
    absent = missing_for(keys, credits, vals)      # dit par le code, sans dépendre du modèle
    if absent:
        text += "\n\n" + " ".join(
            f"Les données STARS ne contiennent aucun résultat {c} ({markers.labels_fr().get(c, c)}) pour {SHORT[k]}"
            + (" : ce crédit est marqué « Non applicable » dans son rapport STARS (raison non fournie dans les "
               "données)." if sources.not_applicable(k, c) else ".")
            for k, c in absent)
    return {"text": text, "keys": keys, "credits": credits, "source": source,
            "removed": removed, "seconds": out["seconds"]}


def show(question: str) -> None:
    print(f"\nQuestion : {question}")
    print("… recherche dans les données et rédaction (Ollama sur CPU : une à trois minutes)")
    r = answer(question)
    print("\n" + r["text"])
    srcs = ", ".join(r["credits"]) or "piliers et score global"
    print(f"\n[universités : {', '.join(SHORT[k] for k in r['keys'])} | crédits STARS : {srcs} | "
          f"réponse : {r['source']}"
          + (f" | {len(r['removed'])} phrase(s) retirée(s) par le garde-fou" if r.get("removed") else "")
          + (f" | {r['seconds']:.0f} s" if r.get("seconds") else "") + "]")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1:
        show(" ".join(sys.argv[1:]))
        return
    print("Assistant ESG (données STARS : Berkeley, Cork, TU Dublin). Tapez « quitter » pour sortir.")
    while True:
        try:
            q = input("\nVotre question > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in {"quitter", "exit", "quit", "q"}:
            break
        if q:
            show(q)


if __name__ == "__main__":
    main()
