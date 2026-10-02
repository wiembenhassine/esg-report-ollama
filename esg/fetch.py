"""
Étape 1 — Télécharger les pages détaillées STARS (authentifié)
==============================================================

Les scorecards STARS sont publiques, mais les pages de crédits (où se trouvent
les vraies valeurs : MWh, tCO2e, m³…) exigent un compte AASHE gratuit.

Ce script :
  1. lit la liste des 118 crédits de chaque université dans les scorecards
     publiques (data/raw/scorecards/*.html) ;
  2. télécharge chaque page avec le cookie de session AASHE ;
  3. enregistre le HTML brut dans data/html_cache/<université>/<CODE>.html.

Garde-fous (leçons tirées du repo de Hakim, CLAUDE.md §6) :
  - préflight : une seule page testée d'abord ; arrêt immédiat si mur de login ;
  - une page de login n'est JAMAIS mise en cache (pas de cache empoisonné) ;
  - pause de 1,5 s entre requêtes, cache réutilisé aux exécutions suivantes ;
  - encodage forcé en UTF-8 si le serveur annonce latin-1.

Le cookie se lit dans la variable AASHE_SESSIONID ou dans le fichier .env
(jamais écrit en dur, .env est ignoré par git).

Usage :
    python -m esg.fetch                 # les 3 universités
    python -m esg.fetch berkeley        # une seule
"""

import os
import sys
import time

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from esg.config import CATEGORY_CODES, HTML_CACHE, INSTITUTIONS, RAW, ROOT, STARS_BASE

PAUSE_SECONDS = 1.5
LOGIN_MARKERS = ("log in with your aashe account", "aashe accounts are free", "please log in")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def is_login_wall(html: str) -> bool:
    low = html.lower()
    return any(m in low for m in LOGIN_MARKERS)


def credit_urls(key: str) -> list[tuple[str, str]]:
    """(code, url) de chaque crédit, dans l'ordre de la scorecard publique."""
    inst = INSTITUTIONS[key]
    tag = f"/report/{inst['report_date']}/"
    html = (RAW / "scorecards" / f"{key}.html").read_text(encoding="utf-8")
    out, seen = [], set()
    for a in BeautifulSoup(html, "lxml").find_all("a", href=True):
        href = a["href"]
        parts = [p for p in href.split("/") if p]
        if tag not in href or len(parts) < 3 or parts[-3] not in CATEGORY_CODES:
            continue
        code = parts[-1]
        if code not in seen:
            seen.add(code)
            out.append((code, href if href.startswith("http") else STARS_BASE + href))
    return out


def make_session(session_id: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.cookies.set("sessionid", session_id, domain="reports.aashe.org")
    return s


def fetch(session: requests.Session, key: str, code: str, url: str) -> tuple[str, bool]:
    """Renvoie (html, depuis_cache). Ne met jamais un mur de login en cache."""
    folder = HTML_CACHE / key
    folder.mkdir(parents=True, exist_ok=True)
    cache = folder / f"{code}.html"
    if cache.exists():
        html = cache.read_text(encoding="utf-8")
        if not is_login_wall(html):
            return html, True
        cache.unlink()

    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    html = resp.text
    time.sleep(PAUSE_SECONDS)
    if not is_login_wall(html):
        cache.write_text(html, encoding="utf-8")
    return html, False


def stop_login_wall() -> None:
    print("=" * 66)
    print("ARRÊT — le site renvoie encore la page de connexion AASHE.")
    print("=" * 66)
    print("Rien n'a été enregistré. Vérifie dans l'ordre :")
    print("  1. Le fichier .env contient bien AASHE_SESSIONID=<valeur>")
    print("  2. Tu as copié la VALEUR du cookie 'sessionid' (pas son nom)")
    print("  3. La session est encore valide : reconnecte-toi et recopie-la")
    print("  4. Connecté(e) dans ton navigateur, vois-tu les questions/réponses")
    print("     d'une page de crédit ? Sinon, un compte gratuit ne suffit pas.")
    sys.exit(1)


def main(keys: list[str]) -> None:
    load_dotenv(ROOT / ".env")
    session_id = os.environ.get("AASHE_SESSIONID", "").strip()
    if not session_id:
        print("[erreur] AASHE_SESSIONID manquant. Copie .env.example en .env et")
        print("         colle la valeur du cookie (voir README, étape 1).")
        sys.exit(1)

    session = make_session(session_id)

    # Préflight : une page, avant d'envoyer 354 requêtes.
    code, url = credit_urls(keys[0])[0]
    html, _ = fetch(session, keys[0], code, url)
    if is_login_wall(html):
        stop_login_wall()
    print("[auth] préflight OK — contenu réel reçu.\n")

    for key in keys:
        urls = credit_urls(key)
        print(f"== {INSTITUTIONS[key]['name']} : {len(urls)} crédits")
        fetched = cached = blocked = 0
        for i, (code, url) in enumerate(urls, 1):
            html, from_cache = fetch(session, key, code, url)
            if is_login_wall(html):
                blocked += 1
                print(f"  [{i:>3}/{len(urls)}] {code:<7} BLOQUÉ (login)")
                if blocked >= 3:
                    print("[erreur] session expirée en cours de route ; relance après reconnexion.")
                    sys.exit(1)
                continue
            cached += from_cache
            fetched += not from_cache
            if not from_cache:
                print(f"  [{i:>3}/{len(urls)}] {code:<7} ok")
        print(f"   -> {fetched} téléchargées, {cached} depuis le cache, {blocked} bloquées\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:] or list(INSTITUTIONS)
    unknown = [a for a in args if a not in INSTITUTIONS]
    if unknown:
        sys.exit(f"Université inconnue : {unknown}. Choix : {list(INSTITUTIONS)}")
    main(args)
