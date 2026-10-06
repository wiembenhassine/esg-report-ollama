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
import unicodedata
from functools import lru_cache

import yaml

from esg.config import MAPPING

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


# Contexte d'emploi d'un marqueur de SCORE (crédit, pilier, score global, valeur de champ).
SCORE_KINDS = {"credit", "pillar", "overall", "field"}
BAD_BEFORE = re.compile(r"(d'ici|depuis|\ben|dès|environ|de l'ordre de|inférieure?s? à|supérieure?s? à|plus de|"
                        r"moins de|jusqu'à|près de|au moins|au plus)\s*$", re.I)
BAD_AFTER = re.compile(r"^(%|pour ?cent|étudiant|personne|salarié|employé|membre|projet|cours|module|ans?\b|"
                       r"année|tonne|euro|dollar|mwh|kwh|m³|m3|heure|arbre|bâtiment|site|panneau)", re.I)
SCORE_INTRO = re.compile(r"obtien|obtenu|atteint|atteign|totalis|score|note|résultat|évalu|avec|soit|recueill|"
                         r"récolt|niveau|crédit|pilier|part\b|points?\b", re.I)
YEAR_BEFORE = re.compile(r"(\ben|d'ici|depuis|dès|jusqu'en|avant|après|horizon|année|entre|et|de|du|à|au|vers|"
                         r"–|-|le|plan|période|calendrier)\s*$", re.I)
# Repère temporel parmi les 3 derniers mots : « plan stratégique {{ année }} – {{ année }} ».
YEAR_ANCHOR = re.compile(r"\b(plan|plans|stratégique|stratégie|période|calendrier|programme|exercice|années?|"
                         r"horizon|feuille de route|"
                         r"janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|"
                         r"act|loi|law|charte|accord|règlement|directive|rapport|report|code|policy|politique)\b",
                         re.I)


def drop_double_percent(text: str, markers: dict) -> str:
    """Supprime un « % » écrit juste après un marqueur de pourcentage qui le contient déjà
    (« {{ PA2_t0_2 }} % » -> « {{ PA2_t0_2 }} ») : suppression seule, le sens ne change pas."""
    return re.sub(r"\{\{\s*(\w+)\s*\}\}\s*(?:%|pour ?cent)", lambda m: (
        f"{{{{ {m.group(1)} }}}}" if markers.get(m.group(1), {}).get("unit") == "%" else m.group(0)), text)


# Marqueur complet « répété » par le modèle (cas réels du 5 octobre, 27 phrases) :
#   « {{ PA12 }} points STARS sur {{ PA12 }} au crédit PA-12 »  et  « un score STARS global de {{ STARS_score }} ».
CREDIT_SHOWN = (r"(?P<d>\d+(?:,\d+)? points? STARS sur \d+(?:,\d+)? au crédit (?P<c>[A-Z]{2,3}-\d+), "
                r"niveau (?P<l>\w+))")
CREDIT_ECHO = re.compile(CREDIT_SHOWN + r"(?:\s+points?(?:\s+STARS)?\s+sur\s+(?P=d))?"
                         r"(?:\s+au crédit (?P=c))?(?:,?\s+niveau (?P=l))?")
OVERALL_ECHO = re.compile(r"(?:\b(?:un |le )?score STARS global(?: de)?\s+)+(?=un score STARS global de \d)")


def drop_marker_echo(text: str) -> str:
    """Retire les mots que le modèle a répétés autour d'un marqueur complet, dans le texte rendu
    (suppression seule : la valeur, le crédit et le niveau restent ceux du marqueur)."""
    return OVERALL_ECHO.sub("", CREDIT_ECHO.sub(lambda m: m.group("d"), text))
# Phrase vidée de son nombre (le nombre a été retiré du contexte et le modèle a gardé le reste).
EMPTIED = re.compile(r"\b(d'ici|depuis|dès|jusqu'en)\s*(?=[.,;:)]|\bet\b|$)|"
                     r"\b(de|à|en|environ|soit)\s+(MWh|kWh|GWh|watts?|W/unit|watt/unit|tonnes?|m³|m3|heures?|%)(?=\W|$)",
                     re.I)
LEVEL_WORD = re.compile(r"\b(maximale?s?|élevée?s?|intermédiaires?|faibles?|nulle?s?)\b", re.I)
CODE_LIKE = re.compile(r"\(?\b[A-Z]{2,}\d*_?(?:Pct|pct|Score|score|Max|max|Points|points)\b\)?")


def _level(word: str) -> str:
    w = word.lower()
    for base in ("maximal", "élevé", "intermédiaire", "faible", "nul"):
        if w.startswith(base):
            return base
    return w


def misuse(text: str, markers: dict) -> list[str]:
    """Marqueurs employés hors de leur sens : un score STARS utilisé comme date, quantité ou effectif,
    suivi d'un « % » en double, sans verbe de score, ou avec un niveau qui contredit le vrai niveau."""
    problems = []
    for m in PLACEHOLDER.finditer(text):
        name, mk = m.group(1), markers.get(m.group(1))
        if not mk:
            continue
        sentence_before = re.split(r"[.!?\n]", text[:m.start()])[-1]
        before = " ".join(sentence_before.split()[-4:])
        after = text[m.end():].lstrip()
        if mk["kind"] == "text":                       # année ou % cité dans le texte STARS
            if mk.get("unit") == "année" and not (YEAR_BEFORE.search(before) or YEAR_ANCHOR.search(before)):
                problems.append(f"marqueur {{{{ {name} }}}} est une ANNÉE : emploie-le comme une date (« en », "
                                "« d'ici », « depuis »…)")
            elif mk.get("unit") == "%" and after.startswith("%"):
                problems.append(f"marqueur {{{{ {name} }}}} contient déjà le signe % : ne l'ajoute pas")
            continue
        if mk["kind"] not in SCORE_KINDS:
            continue
        if BAD_BEFORE.search(before):
            problems.append(f"marqueur {{{{ {name} }}}} employé comme date ou quantité après « {before.split()[-1]} » : "
                            "c'est un score STARS")
        elif BAD_AFTER.match(after):
            problems.append(f"marqueur {{{{ {name} }}}} suivi de « {after.split()[0]} » : c'est un score STARS complet, "
                            "pas un nombre à compléter")
        elif mk["kind"] != "field" and not SCORE_INTRO.search(sentence_before):
            problems.append(f"marqueur {{{{ {name} }}}} sans verbe de score : écris par exemple « obtient {{{{ {name} }}}} »")
    for sentence in SENTENCE_END.split(text):
        names = [n for n in PLACEHOLDER.findall(sentence) if markers.get(n, {}).get("level")]
        if len(names) == 1:
            said = {_level(w) for w in LEVEL_WORD.findall(PLACEHOLDER.sub(" ", sentence))}
            wrong = said - {markers[names[0]]["level"]}
            if wrong:
                problems.append(f"niveau « {', '.join(sorted(wrong))} » faux pour {{{{ {names[0]} }}}} "
                                f"(vrai niveau : {markers[names[0]]['level']})")
    return problems


@lru_cache(maxsize=None)
def glossary() -> dict:
    with open(MAPPING / "glossary.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _plain(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


# Formulations interdites : la phrase est retirée par repair() (avant, toute la version était rejetée).
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

# Affirmation interdite : les domaines STARS ne sont pas une analyse de matérialité de l'université.
MATERIALITY = re.compile(r"(a|ont|avait|avoir)\s+(identifié|déterminé|défini|sélectionné|retenu)\s+"
                         r"(les\s+|ses\s+|des\s+)?(thèmes|enjeux|sujets)\s+matériels|thèmes\s+matériels\s+suivants|"
                         r"\bses\s+thèmes\s+matériels", re.I)


def glossary_lines(*texts: str) -> list[str]:
    """Lignes du lexique pour les sigles présents dans ces textes (prompt du rédacteur et du juge)."""
    joined = " ".join(texts)
    return [f"- {acr} = {e['meaning']}" for acr, e in glossary().items() if re.search(rf"\b{acr}s?\b", joined)]


def wrong_expansions(text: str) -> list[str]:
    """Sigle du lexique développé avec des mots sans rapport : « Services de l'État (SEC) »."""
    problems = []
    for acr, entry in glossary().items():
        keys = [_plain(k) for k in entry["keywords"]]
        for m in re.finditer(rf"([^.()\n]{{3,90}})\(\s*{acr}s?\s*\)", text):          # « développé (SEC) »
            before = _plain(" ".join(m.group(1).split()[-8:]))
            if not any(k in before for k in keys):
                problems.append(f"sigle {acr} mal développé (« {m.group(1).strip()[-60:]} ») : {acr} = {entry['meaning']}")
        for m in re.finditer(rf"\b{acr}s?\s*\(([^)]{{4,120}})\)", text):               # « SEC (développé) »
            if not any(k in _plain(m.group(1)) for k in keys):
                problems.append(f"sigle {acr} mal développé (« {m.group(1)[:60]} ») : {acr} = {entry['meaning']}")
    return problems


def check_draft(text: str, allowed: set[str], markers: dict | None = None) -> list[str]:
    """Liste des violations (vide = texte accepté)."""
    problems = misuse(text, markers) if markers else []
    problems += wrong_expansions(text)
    for rx, msg in FORBIDDEN:
        if rx.search(text):
            problems.append(f"formulation interdite : {msg}")
    if MATERIALITY.search(text):
        problems.append("les domaines STARS ne sont pas une analyse de matérialité : n'écris pas que l'université "
                        "a identifié ou déterminé ses thèmes matériels")
    for m in CODE_LIKE.finditer(PLACEHOLDER.sub(" ", text)):
        problems.append(f"identifiant technique recopié : {m.group(0)!r}")
    for m in EMPTIED.finditer(PLACEHOLDER.sub(" X ", text)):
        problems.append(f"phrase vidée de son nombre : « {m.group(0).strip()} » — retire la phrase ou cite le marqueur")
    used = PLACEHOLDER.findall(text)
    for name in sorted(set(used) - allowed):
        problems.append(f"placeholder inconnu {{{{ {name} }}}} : utilise uniquement ceux de la liste")
    rest = PLACEHOLDER.sub(" ", text)
    for bad in ANY_TEMPLATE.findall(rest):
        problems.append(f"syntaxe interdite {bad!r} : seul {{{{ IDENTIFIANT }}}} est permis, sans calcul ni filtre")
    rest = ANY_TEMPLATE.sub(" ", rest)
    if re.search(r"\[\s*n\s*\]", rest):                         # nombre masqué recopié
        problems.append("« [n] » est un nombre masqué : ne le recopie pas, reformule la phrase sans quantité")
        rest = re.sub(r"\[\s*n\s*\]", " ", rest)
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


SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def repair(text: str, allowed: set[str], markers: dict | None = None) -> tuple[str, list[str]]:
    """Retire les phrases (et titres) qui violent le garde-fou ; renvoie (texte, phrases retirées).

    Le code ne fait que SUPPRIMER : il n'ajoute ni ne modifie aucun mot. Une phrase fautive
    disparaît donc du rapport au lieu de faire rejeter tout le texte.
    """
    kept_lines, removed = [], []
    for line in text.splitlines():
        if not line.strip():
            kept_lines.append(line)
            continue
        if line.lstrip().startswith(("#", "-", "*")) and check_draft(line, allowed, markers):
            removed.append(line.strip())
            continue
        kept = []
        for sentence in SENTENCE_END.split(line):
            if check_draft(sentence, allowed, markers):
                removed.append(sentence.strip())
            else:
                kept.append(sentence)
        if kept:
            kept_lines.append(" ".join(kept))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept_lines)).strip(), removed


def tidy(text: str, section_title: str = "") -> str:
    """Nettoyage de forme par le code (suppression uniquement, aucun mot ajouté) :
    titre de section répété, marqueurs « ### ### » doublés, phrase finale coupée par la
    limite de longueur du modèle, titre final resté sans contenu."""
    lines = text.strip().splitlines()
    while lines and lines[0].lstrip("#").strip().lower() in {section_title.lower(), ""} and lines[0].startswith("#"):
        lines.pop(0)
    lines = [re.sub(r"^(#{2,6})(\s+#{1,6})+\s+", r"\1 ", l) for l in lines]
    lines = [re.sub(r"\s*\(\s*Refs?[\s\d]*(?:,\s*Refs?[\s\d]*|,[\s\d]*)*\)", "", l)   # « (Ref ) », « (Ref, Ref) »
             for l in lines]
    text = drop_orphan_colons("\n".join(lines).strip())
    last = text.splitlines()[-1] if text else ""
    if text and not re.search(r"[.!?»)\]]\s*$", text) and not LIST_ITEM.match(last):   # fin coupée (pas une liste)
        cut = max(text.rfind(". "), text.rfind(".\n"), text.rfind("\n\n"))
        text = text[:cut + 1] if cut > 0 else text
    text = drop_repeats(text)
    text = re.sub(r"(\n#{2,6} [^\n]*\s*)+$", "", text.rstrip())  # titre final sans contenu
    return text.strip()


LIST_ITEM = re.compile(r"^\s*([*\-•]\s|\||\d+[.)]\s)")      # « **Gras** » n'est pas une liste


def drop_orphan_colons(text: str) -> str:
    """Retire une phrase qui annonce une liste (« … étaient : ») quand aucune liste ne suit
    (suppression seule ; cas réels : liste retirée par le garde-fou, « Voici la section rédigée : »)."""
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        if re.search(r":\s*$", line) and not line.lstrip().startswith("#"):
            nxt = next((l for l in lines[i + 1:] if l.strip()), "")
            if not LIST_ITEM.match(nxt):
                line = " ".join(SENTENCE_END.split(line.strip())[:-1])
                if not line:
                    continue
        out.append(line)
    return "\n".join(out)


STOPWORDS = set("""le la les l un une des de du d et ou a au aux en dans par pour sur avec qui que qu est sont
ont ce cette ces son sa ses leur leurs il elle ils elles se s y ne pas plus egalement aussi ainsi enfin notamment
tres tout tous toute toutes comme dont""".split())


def _content(sentence: str) -> tuple[set, set]:
    """(mots porteurs de sens, éléments protégés = marqueurs et tokens contenant un chiffre)."""
    marks = {m.group(1) for m in PLACEHOLDER.finditer(sentence)}
    words = re.findall(r"[\w%-]+", _plain(PLACEHOLDER.sub(" ", sentence)))
    protected = marks | {w for w in words if DIGIT.search(w)}
    return {w for w in words if w not in STOPWORDS and len(w) > 1} | marks, protected


def near_repeat(sentence: str, earlier: list[tuple[set, set]]) -> bool:
    """Phrase presque identique à une phrase déjà écrite : au moins 90 % de ses mots porteurs de sens
    y figurent déjà, et aucun chiffre, code ou marqueur nouveau (deux crédits différents ne sont jamais
    confondus)."""
    words, protected = _content(sentence)
    if len(words) < 6:
        return False
    return any(protected <= p and len(words & w) >= 0.9 * len(words) for w, p in earlier)


def drop_repeats(text: str) -> str:
    """Supprime une phrase identique ou presque identique à une phrase déjà écrite (suppression seule)."""
    seen, earlier, out_lines = set(), [], []
    for line in text.splitlines():
        if line.lstrip().startswith("#") or not line.strip():
            out_lines.append(line)
            continue
        kept = []
        for sentence in SENTENCE_END.split(line):
            key = " ".join(sentence.lower().split())
            if len(key) > 25 and (key in seen or near_repeat(sentence, earlier)):
                continue
            seen.add(key)
            earlier.append(_content(sentence))
            kept.append(sentence)
        if kept:
            out_lines.append(" ".join(kept))
    return re.sub(r"(#{2,6} [^\n]*\n)(\s*\n)*(?=#{2,6} |\Z)", "", "\n".join(out_lines))   # titres devenus vides


# Nombre à séparateur de milliers (« 78 414,00 ») ou nombre simple (« 2028 », « 86,76 ») : la 1re forme
# exige au moins un groupe de milliers, sinon « 2028 » était découpé en « 202 » + « 8 ».
FR_NUMBER = re.compile(r"\d{1,3}(?:[   ]\d{3})+(?:,\d+)?|\d+(?:,\d+)?")


def numbers_in(text: str) -> list[str]:
    return [m.group(0) for m in FR_NUMBER.finditer(strip_refs(text))]


def check_rendered(text: str, substituted: dict[str, str]) -> list[str]:
    """Chaque nombre du texte final doit apparaître dans une valeur substituée."""
    allowed = set()
    for disp in substituted.values():
        allowed.update(numbers_in(disp))
    return [f"nombre non traçable dans le texte final : {n!r}"
            for n in numbers_in(text) if n not in allowed]
