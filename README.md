# Rapport ESG automatisé (GRI) avec Ollama — universités STARS

Génère, pour UC Berkeley, University College Cork et TU Dublin, un rapport de
durabilité **« en référence aux » normes GRI** à partir de leurs soumissions
publiques AASHE STARS 3.0, avec un LLM **local** (Ollama, aucune API payante)
et un module de **validation automatique**.

## Principe : le LLM n'écrit jamais un chiffre

1. Le code extrait chaque valeur STARS dans `data/processed/facts.csv`
   (une ligne = un chiffre + sa provenance : crédit, champ, URL).
2. `llama3.1:8b` rédige le texte avec des **placeholders** (`{{ OP6_SCOPE1 }}`) ;
   il ne voit jamais les valeurs.
3. Jinja2 (`StrictUndefined`) remplace les placeholders par les vraies valeurs.
4. **Validation** : un garde-fou déterministe rejette tout chiffre écrit par le
   LLM, puis un juge Ollama vérifie la fidélité de chaque section aux données ;
   en cas d'échec, la section est régénérée avec les remarques du juge.

## Pipeline

| # | Étape | Module | État |
|---|-------|--------|------|
| 1 | Télécharger les pages de crédits STARS (authentifié) | `esg/fetch.py` | ✅ |
| 2 | Extraire les champs → `facts.csv` + provenance | `esg/facts.py` | à faire |
| 3 | Table de correspondance STARS → GRI (écrite à la main) | `mapping/gri_map.yaml` | à faire |
| 4 | RAG local (nomic-embed-text) | `esg/rag.py` | à faire |
| 5 | Génération par section (placeholders + Jinja2) | `esg/generate.py` | à faire |
| 6 | Validation : garde-fou chiffres + juge LLM + régénération | `esg/guard.py`, `esg/judge.py` | à faire |
| 7 | Rendu du rapport + index de contenu GRI | `esg/render.py` | à faire |

## Installation (Windows / PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

## Étape 1 — Compte AASHE et téléchargement des pages

Les scorecards STARS sont publiques, mais les **valeurs** (MWh, tCO2e, m³,
effectifs…) sont sur les pages de crédits, réservées aux comptes AASHE
(**gratuits**, ouverts à tous).

1. Crée un compte sur <https://reports.aashe.org/accounts/signup/> et connecte-toi.
2. Ouvre une page de crédit, par exemple
   [OP-5 Berkeley](https://reports.aashe.org/institutions/university-of-california-berkeley-ca/report/2025-02-19/OP/energy-climate/OP-5/),
   et vérifie que tu vois les questions et les réponses chiffrées.
3. `F12` → onglet **Application** (Chrome/Edge) ou **Stockage** (Firefox) →
   **Cookies** → `https://reports.aashe.org` → copie la **valeur** de `sessionid`.
4. `copy .env.example .env` puis colle la valeur après `AASHE_SESSIONID=`.
5. Lance le téléchargement (354 pages, ~10 min, pause polie de 1,5 s) :

```powershell
.venv\Scripts\python -m esg.fetch
```

Le script teste d'abord une seule page et s'arrête si la connexion échoue.
Les pages sont mises en cache dans `data/html_cache/` (non versionné).

## Données et attribution

- Données STARS extraites et structurées par **Hakim Chaanbi**
  ([hakimchaanbi/esg-reporting](https://github.com/hakimchaanbi/esg-reporting)),
  copiées dans `data/raw/`.
- Source : *[Institution] STARS Report. AASHE. [date]. reports.aashe.org.*
  Les données STARS sont accessibles publiquement et utilisées ici avec
  attribution à l'AASHE ; elles **ne sont pas** sous licence ouverte.

| Université | Note | Score | Date du rapport |
|---|---|---|---|
| UC Berkeley | Platinum | 86.76 | 2025-02-19 |
| University College Cork | Platinum | 85.99 | 2026-03-05 |
| TU Dublin | Gold | 83.35 | 2024-12-02 |
