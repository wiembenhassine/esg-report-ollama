# Rapport ESG automatisé (GRI) avec Ollama — universités STARS

Génère, pour **UC Berkeley**, **University College Cork** et **TU Dublin**, un rapport de
durabilité **« en référence aux » normes GRI** (78 publications, 13 normes) à partir de
leurs soumissions publiques AASHE STARS 3.0, plus une **synthèse comparative**.
Le LLM tourne **en local** (Ollama, `llama3.1:8b` + `nomic-embed-text`), sans API payante,
et chaque section passe par un **module de validation** avant d'entrer dans le rapport.

## Principe : le LLM n'écrit jamais un chiffre

```
facts.csv ──(identifiants + niveau qualitatif, JAMAIS les valeurs)──► llama3.1:8b
                                                                        │ texte + {{ OP6_score }}
                                                                        ▼
                                              garde-fou : 0 chiffre écrit par le LLM ?
                                                                        │
                                              Jinja2 StrictUndefined : le CODE insère les valeurs
                                                                        │
                                              contrôle : chaque nombre final vient d'un fait ?
                                                                        │
                                              juge Ollama : affirmations fidèles aux sources ?
                                                 │ refus                │ accepté
                                                 ▼                      ▼
                                   régénération avec la consigne     section validée
```

- Les **nombres du contexte sont masqués** (`[n]`) avant d'arriver au LLM : il ne peut ni
  recopier, ni arrondir, ni inventer une valeur.
- Pour qualifier un score, il reçoit un **niveau calculé par le code** (maximal, élevé,
  intermédiaire, faible, nul), jamais le score.
- La **correspondance STARS → GRI** (`mapping/gri_map.yaml`) est **écrite à la main** ;
  le **statut** de chaque publication GRI est calculé par le code, pas par le LLM.

## Module de validation (⑥)

| Contrôle | Type | Ce qu'il vérifie |
|---|---|---|
| Garde-fou des chiffres | déterministe | aucun chiffre, nombre en lettres, calcul ou placeholder inconnu dans le texte du LLM |
| Traçabilité | déterministe | chaque nombre du texte final = valeur d'un fait de `facts.csv` |
| Règles de reporting | déterministe | français, longueur, « en référence aux » (jamais « conforme »), publications GRI citées |
| Juge LLM | Ollama, T = 0, JSON | découpe en affirmations → **fidélité** (style RAGAS), règles, note /5, consigne de correction |
| Régénération | boucle | section refusée → réécrite avec les corrections (2 tentatives max. sur CPU) |
| Humain dans la boucle | annexe | sections « à relire » listées avec les affirmations non supportées |

Résultats par section en annexe de chaque rapport (« Validation du rapport »).

## Installation (Windows / PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

## Utilisation

```powershell
.venv\Scripts\python -m esg.pipeline                    # 3 rapports + synthèse comparative
.venv\Scripts\python -m esg.pipeline cork               # une université
.venv\Scripts\python -m esg.pipeline cork --sections gouvernance social
.venv\Scripts\python -m esg.pipeline --dry-run          # sans LLM, pour tester le rendu (secondes)
.venv\Scripts\python -m esg.pipeline --render-only      # re-rendre depuis le cache
.venv\Scripts\python -m pytest                          # tests
```

Sorties dans `outputs/<université>/` : `rapport_*.md`, `.html`, `.pdf` (via Edge headless)
et `provenance.csv` (chaque chiffre → crédit, champ, URL STARS). Les sections validées sont
en cache (`outputs/cache/`) : une relance ne recalcule que ce qui a changé.

**Durée.** Sans GPU, `llama3.1:8b` produit 2 à 4 tokens/s : compter 5 à 15 min par section
(rédaction + juge), soit plusieurs heures pour les 3 rapports. Fermer les applications
gourmandes (Oracle, Jenkins, MongoDB, PostgreSQL, onglets de navigateur) accélère nettement.

## Données détaillées STARS (compte AASHE gratuit)

Les scores et les réponses narratives sont publics ; les **valeurs détaillées** (MWh, tCO2e,
m³, effectifs…) ne sont visibles qu'avec un compte AASHE **gratuit**. Sans elles, les
publications chiffrées sont marquées « Non évalué » plutôt que devinées.

1. Crée un compte sur <https://reports.aashe.org/accounts/signup/> et connecte-toi.
2. `F12` → **Application** → **Cookies** → `https://reports.aashe.org` → copie la valeur de `sessionid`.
3. `copy .env.example .env` et colle-la après `AASHE_SESSIONID=` (ne la partage jamais).
4. Puis :

```powershell
.venv\Scripts\python -m esg.fetch                # 354 pages, ~10 min, préflight + cache
.venv\Scripts\python -m esg.parse_fields berkeley OP-5   # contrôle du parseur sur une page
.venv\Scripts\python -m esg.pipeline             # les champs extraits alimentent l'index GRI
```

## Structure

```
esg/
  config.py        chemins, universités, modèles Ollama
  fetch.py         téléchargement authentifié des pages STARS (préflight, cache sûr)
  parse_fields.py  extraction des champs (libellé -> valeur) des pages STARS
  sources.py       récits STARS : retrait du texte d'aide commun, masquage des nombres
  facts.py         table des faits (seule source des chiffres) + niveaux qualitatifs
  gri_index.py     statuts GRI calculés à partir de mapping/gri_map.yaml
  rag.py           index nomic-embed-text (numpy) : passages pertinents par section
  llm.py           client Ollama (chat, JSON contraint, embeddings)
  guard.py         garde-fou des chiffres + traçabilité
  judge.py         juge LLM + règles déterministes (module ⑥)
  generate.py      boucle rédaction -> validation -> régénération
  render.py        Markdown, HTML, PDF, index GRI, annexe de validation, provenance
  pipeline.py      commande principale
mapping/gri_map.yaml   correspondance STARS -> GRI écrite à la main
data/raw/              données de Hakim (scores, scorecards, récits, corpus ESG)
tests/                 garde-fou, faits recalculés, cohérence du mapping, rapports
```

## Données et attribution

- Données STARS extraites et structurées par **Hakim Chaanbi**
  ([hakimchaanbi/esg-reporting](https://github.com/hakimchaanbi/esg-reporting)), copiées dans `data/raw/`.
- Source : *[Institution] STARS Report. AASHE. [date]. reports.aashe.org.* Les données STARS
  sont accessibles publiquement et utilisées avec attribution à l'AASHE ; elles **ne sont pas**
  sous licence ouverte et sont autodéclarées.

| Université | Note | Score | Date du rapport |
|---|---|---|---|
| UC Berkeley | Platinum | 86.76 | 2025-02-19 |
| University College Cork | Platinum | 85.99 | 2026-03-05 |
| TU Dublin | Gold | 83.35 | 2024-12-02 |
