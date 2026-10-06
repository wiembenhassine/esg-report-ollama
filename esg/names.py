"""
Nom des universités dans les textes du modèle, uniformisé au rendu (forme seulement, aucun fait ajouté) :
la première mention d'une section donne le nom complet et le sigle (« University College Cork (UCC) »),
les suivantes le sigle (« l'UCC », « TU Dublin », « UC Berkeley »). Remplace les variantes du modèle :
« L'Université College Cork », « La TU Dublin », « L'université de Californie, Berkeley, »…
Les parties écrites par le code (en-têtes, tableaux) ne passent pas par ici.
"""

import re

NAMES = {
    "cork": {"full": "University College Cork", "abbr": "UCC", "short": "l'UCC",
             "variants": r"Universit[éey] College Cork"},
    "tudublin": {"full": "Technological University Dublin", "abbr": "TU Dublin", "short": "TU Dublin",
                 "variants": r"(?:[Uu]niversité\s+)?Technological University Dublin|[Uu]niversité technologique de Dublin"},
    "berkeley": {"full": "University of California, Berkeley", "abbr": "UC Berkeley", "short": "UC Berkeley",
                 "variants": r"[Uu]niversité de Californie(?:, Berkeley| à Berkeley)|University of California, Berkeley"},
}
ARTICLE = r"(?:\b[Ll]'|\b[Ll]a\s+|\b[Ll]e\s+)?"
SENTENCE_START = re.compile(r"(?:^|[.!?]\s+|\n\s*(?:[-*]\s+)?|\*\*\s*)$")


def _full_pattern(n: dict) -> re.Pattern:
    # La virgule qui ferme l'apposition (« de Californie, Berkeley, a déclaré ») est capturée à part.
    return re.compile(ARTICLE + rf"(?:{n['variants']})(?:\s*\({re.escape(n['abbr'])}\))?(?P<comma>,(?=\s))?")


def normalize(key: str, text: str) -> str:
    n = NAMES[key]
    seen = False

    def repl(m: re.Match) -> str:
        nonlocal seen
        start = bool(SENTENCE_START.search(text[:m.start()]))
        new = n["short"] if seen else f"{n['full']} ({n['abbr']})"
        seen = True
        if start:
            new = new[0].upper() + new[1:]
        # en tête de phrase, la virgule d'apposition disparaît (« UC Berkeley a déclaré ») ; sinon elle reste
        return new + ("" if start or not m.group("comma") else ",")

    text = _full_pattern(n).sub(repl, text)
    if n["short"] == n["abbr"]:                       # sigle sans article : « la TU Dublin » -> « TU Dublin »,
        text = re.sub(rf"\b(?:[Ll]a\s+|[Ll]e\s+|[Ll]'){re.escape(n['abbr'])}\b(?!\s+[A-Z][a-z])",   # mais pas
                      n["abbr"], text)                # « le TU Dublin Strategic Plan » (l'article va au plan)
    return text


def normalize_all(text: str) -> str:
    for key in NAMES:
        text = normalize(key, text)
    return text
