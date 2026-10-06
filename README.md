# Rapport ESG automatisé avec Ollama — universités STARS (GRI, TCFD, ESRS)

## Objectif

Transformer les données de durabilité publiques de trois universités (AASHE STARS 3.0 :
**UC Berkeley**, **University College Cork**, **TU Dublin**) en **rapports ESG rédigés en
français**, établis « en référence aux » normes **GRI**, avec une correspondance vers **TCFD** et
**ESRS**, un **tableau de bord** et un **assistant de questions-réponses**. Tout tourne **en
local** avec Ollama (`llama3.1:8b`, `nomic-embed-text`) : aucune API payante.

Règle absolue du projet : **le modèle de langage n'écrit jamais un chiffre**. Il écrit des
marqueurs ; le code les remplace par les vraies valeurs ; un garde-fou et un juge contrôlent
chaque section.

## Répartition du travail : Hakim / Wiem

Projet en binôme. **La collecte des données est le travail de Hakim Chaanbi**
([hakimchaanbi/esg-reporting](https://github.com/hakimchaanbi/esg-reporting)) ; ce dépôt la
réutilise telle quelle et ne la refait pas.

| Ce qui vient de Hakim (copié dans `data/raw/`, inchangé) | Ce que j'ai ajouté (Wiem) |
|---|---|
| Scraping AASHE STARS des 3 universités (scorecards, pages de crédits) | Validation des données ligne par ligne (`esg/validate.py`) |
| `combined_esg_dataset.csv` (scores par crédit, regroupement en piliers) | Correspondance STARS → **GRI** (86 publications, dont GRI 101 Biodiversité 2024), **TCFD**, **ESRS**, écrite à la main (`mapping/`) |
| `*_credits.txt` (textes des pages de crédits) | Base de connaissances : découpage, embeddings `nomic-embed-text`, recherche par similarité (`esg/rag.py`) |
| `knowledge_sources/` (corpus de référence ESG) | Génération des rapports avec Ollama, section par section, sans chiffre écrit par le modèle (`esg/generate.py`, `esg/guard.py`) |
| Le choix des 3 universités et le regroupement E/S/G | Validation par Ollama (juge LLM), régénération, recoupement par le code (`esg/judge.py`) |
| | Sorties : Word (.docx), PDF, HTML, Markdown, provenance de chaque chiffre, tableau de bord (`esg/render.py`, `esg/docx_export.py`, `esg/dashboard.py`) |
| | Assistant de questions-réponses (`esg/chat.py`) ; tests automatiques (`tests/`) |

Code inspiré de Hakim, crédité dans le fichier concerné : `esg/fetch.py` (extension
facultative de téléchargement, adaptée de son « deep scraper v2 », non utilisée pour les
résultats livrés) et le regroupement en piliers (`esg/facts.py`, repris de son
`combine_universities.py`). La vérification fichier par fichier des deux dépôts est décrite
plus bas (« Vérifier la non-redondance »).

## Le pipeline, étape par étape

| # | Étape | Fichier | Ce qui se passe |
|---|---|---|---|
| 0 | Validation des données | `esg/validate.py` | chaque ligne du CSV : champs obligatoires, université connue, code de crédit, 0 ≤ score ≤ max, pas de doublon. Affiche le nombre de lignes valides / en erreur ; les lignes en erreur ne servent à aucun chiffre |
| 1 | Table des faits | `esg/facts.py` | une ligne par chiffre (scores, totaux par pilier, score global) avec sa source ; c'est la **seule** source des chiffres du rapport |
| 2 | Correspondances | `mapping/gri_map.yaml`, `mapping/frameworks.yaml`, `esg/frameworks.py` | crédit STARS → GRI / TCFD / ESRS, à la main ; un crédit sans équivalent est marqué « Aucune correspondance », jamais forcé |
| 3 | Base de connaissances | `esg/sources.py`, `esg/rag.py` | textes STARS découpés en passages, texte d'aide du formulaire retiré, **nombres supprimés**, embeddings `nomic-embed-text`, recherche par similarité cosinus |
| 4 | Génération | `esg/generate.py` | `llama3.1:8b` rédige chaque section (organisation, gouvernance, environnement, social…) avec des marqueurs `{{ OP6_score }}` ; seuls les marqueurs de la section sont acceptés |
| 5 | Garde-fou | `esg/guard.py` | rejette tout chiffre ou nombre en lettres écrit par le modèle, et tout marqueur étranger à la section ; retire les phrases fautives (suppression uniquement) ; vérifie que chaque nombre final vient de `facts.csv` |
| 6 | Juge (LLM-as-judge) | `esg/judge.py` | Ollama relit la section, vérifie chaque affirmation contre les sources, donne une **note /5** et une **fidélité %** (affichées dans le terminal) ; sous le seuil, la section est régénérée avec ses consignes |
| 7 | Sorties | `esg/render.py`, `esg/docx_export.py`, `esg/dashboard.py` | rapport **Word (.docx)**, PDF, HTML et Markdown par université, synthèse comparative, `provenance.csv`, table des correspondances, tableau de bord HTML |
| 7 bis | Relecture hors pipeline | `relecture/*.yaml`, `esg/review.py` | corrections de sens proposées après lecture des sources STARS (Claude Code, à valider par Wiem), appliquées au rendu ; chaque correction cite sa source, aucun chiffre tapé à la main |
| 8 | Questions-réponses | `esg/chat.py` | réponses tirées des seules données, comparaisons entre universités, « Information non disponible » si la donnée n'existe pas |

Le marqueur choisi est `{{ OP6_score }}` (syntaxe Jinja2, ex. `[[OP-6]]` dans le cahier des
charges) : Jinja2 en mode `StrictUndefined` refuse tout marqueur inconnu, ce qui fait du
rejet une garantie du moteur de gabarits, pas seulement une convention.

## Installation (sur n'importe quel PC Windows)

Prérequis : **Python 3.12 ou plus récent**, **Git**, **Ollama** (<https://ollama.com/download>),
et Microsoft Edge ou Google Chrome pour l'export PDF (présents par défaut sous Windows).

```powershell
git clone https://github.com/wiembenhassine/esg-report-ollama.git
cd esg-report-ollama
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
ollama pull llama3.1:8b
ollama pull nomic-embed-text
.venv\Scripts\python -m pytest -q
```

La dernière commande doit afficher tous les tests au vert. Les données de Hakim sont déjà dans
le dépôt (`data/raw/`) : aucun téléchargement supplémentaire n'est nécessaire.

## Commandes

```powershell
.venv\Scripts\python -m esg.validate                    # validation des données (secondes)
.venv\Scripts\python -m esg.frameworks                  # table STARS -> GRI / TCFD / ESRS (secondes)
.venv\Scripts\python -m esg.pipeline                    # pipeline complet, reprend les sections validées en cache
.venv\Scripts\python -m esg.pipeline --no-cache --log outputs\logs\full_run.log   # tout régénérer avec Ollama (~4 h sur CPU)
.venv\Scripts\python -m esg.pipeline cork               # une seule université
.venv\Scripts\python -m esg.pipeline --render-only      # re-rendre Word/PDF/HTML depuis le cache (~1 min)
.venv\Scripts\python -m esg.pipeline --dry-run          # chaîne complète sans LLM (écrit dans outputs\essai_sans_llm\)
.venv\Scripts\python -m esg.chat                        # assistant de questions-réponses
.venv\Scripts\python -m esg.chat "Compare Cork et TU Dublin sur les déchets"
.venv\Scripts\python -m esg.demo                        # démonstration du garde-fou (instantanée)
.venv\Scripts\python -m esg.demo --juge                 # + test du juge sur un texte volontairement faux
.venv\Scripts\python -m esg.verify_univ 2026           # 10 chiffres par université comparés au CSV
.venv\Scripts\python -m esg.review                     # liste des corrections de relecture (outputs/relecture_humaine.md)
.venv\Scripts\python -m pytest -v                       # tests automatiques
```

Sorties :

| Fichier | Contenu |
|---|---|
| `outputs/<université>/rapport_<université>.docx` | rapport Word (structure du rapport de référence : à propos, sections, index de contenu GRI par norme, annexes) |
| `outputs/<université>/rapport_<université>.pdf` / `.html` / `.md` | le même rapport dans les autres formats |
| `outputs/<université>/provenance.csv` | chaque chiffre du rapport → crédit STARS, valeur brute, URL source |
| `outputs/comparatif/` | synthèse comparative des trois universités |
| `outputs/correspondance_stars_gri_tcfd_esrs.csv` | table des correspondances |
| `outputs/tableau_de_bord.html` | tableau de bord (hors ligne, thème clair/sombre) |
| `outputs/cache/` | sections validées et historique complet des tentatives et verdicts du juge |
| `outputs/relecture_humaine.md` | corrections de relecture : passage fautif, raison, source STARS, correction |
| `outputs/verification_chiffres.md` | 10 chiffres tirés au hasard par université, comparés au CSV |

**Durée** : sans GPU, `llama3.1:8b` produit 2 à 4 mots-unités par seconde ; une section prend
5 à 15 minutes (rédaction + juge). Laisser le PC branché et éveillé : une mise en veille
interrompt la génération (le cache permet de reprendre).

## Choix techniques

| Choix | Pourquoi |
|---|---|
| Ollama + `llama3.1:8b` en local | aucune donnée envoyée à l'extérieur, aucun coût, reproductible |
| Marqueurs + Jinja2 `StrictUndefined` | le modèle ne peut ni inventer, ni arrondir, ni recopier un chiffre ; un marqueur inconnu fait échouer le rendu |
| Nombres **supprimés** du contexte | un premier essai les remplaçait par « [n] », que le modèle recopiait |
| Garde-fou déterministe + juge LLM | le code garantit ce qu'il sait vérifier (chiffres, formulations, marqueurs) ; le juge contrôle le sens des phrases |
| Recoupement des verdicts du juge | un juge 8B signale parfois de fausses violations : le code écarte celles qu'il peut réfuter (et les trace) |
| Correspondances écrites à la main (YAML) | une correspondance inventée par un LLM serait une faute d'intégrité dans un outil ESG |
| Index d'embeddings numpy (pas ChromaDB) | ~1 200 passages seulement ; ChromaDB s'installe mal sous Python 3.14 |
| Statuts GRI calculés par le code | « Rapporté », « Partiellement rapporté », « Non rapporté », « Non évalué » ne dépendent jamais du modèle |
| Points de vigilance et tableaux d'indicateurs rendus par le code | des mises en garde obligatoires ne doivent pas dépendre de ce que le modèle écrit |
| PDF via Edge en mode headless | aucune bibliothèque lourde à installer sous Windows |

## Limites (à présenter)

- **Valeurs physiques absentes** : le jeu de données de Hakim contient les **scores** STARS et les
  textes, pas les valeurs détaillées (MWh, tCO2e, m³), réservées aux comptes AASHE. Les
  publications GRI chiffrées sont donc « Non évalué » (jamais devinées) et l'assistant répond
  « non disponible » à ces questions.
- **Correspondances TCFD/ESRS thématiques** : aucun organisme ne publie de table STARS → TCFD/ESRS ;
  la table proposée est raisonnée et à valider.
- **Évolution GRI à venir** : GRI 101: Biodiversité 2024 (en vigueur depuis le 1er janvier 2026) est intégrée ;
  GRI 102: Climate Change 2025 remplacera les publications 305-1 à 305-5 le 1er janvier 2027 (pas encore appliqué,
  GRI 305 reste valable pour un rapport publié en 2026).
- **Juge 8B imparfait** : il garantit peu le sens. Sur les 8 sections de Dublin relues à la main, il a
  vu 1 erreur sur 24 (contenu inventé, mauvais rattachement, traduction fausse), alors que les chiffres
  étaient tous justes. D'où la relecture hors pipeline (`relecture/`) des 24 sections des trois rapports,
  proposée par Claude Code et à valider par Wiem (voir `BILAN_TESTS.md`, sections 9 et 10). Une section
  régénérée doit être relue à nouveau (le rendu signale toute correction qui ne correspond plus au texte).
- **Peu de chiffres dans la prose** : le modèle utilise rarement les marqueurs ; les scores sont
  surtout présentés dans les tableaux écrits par le code en tête de chaque section.
- **Piliers E/S/G** : regroupement raisonné des crédits STARS (repris de Hakim), pas officiel.
- **Scores STARS** : autodéclarés, notés par rapport à un groupe de pairs, non vérifiés par
  l'AASHE ; les périmètres diffèrent (Cork exclut ses filiales ; TU Dublin n'a pas de fonds de
  dotation).
- **Lenteur** : environ 4 heures pour tout régénérer sur un processeur sans GPU.

## Vérifier la non-redondance avec le dépôt de Hakim

Comparaison faite le 4 octobre 2026 (empreinte SHA-256 de chaque fichier, puis lignes de code
communes) : les **30 fichiers identiques** sont tous des **données** de Hakim placées dans
`data/raw/` ; aucun fichier de code de Hakim n'est copié. Seul `esg/fetch.py` partage des lignes
avec ses scrapers (détection du mur de connexion, cache, encodage) : il est explicitement
crédité et n'a pas servi aux résultats. Tout le reste du code (`esg/`, `mapping/`, `tests/`) est
propre à ce dépôt.

## Extension facultative : valeurs détaillées STARS (compte AASHE gratuit)

1. Créer un compte sur <https://reports.aashe.org/accounts/signup/> et se connecter.
2. `F12` → **Application** → **Cookies** → `https://reports.aashe.org` → copier la valeur de `sessionid`.
3. `copy .env.example .env` puis coller la valeur après `AASHE_SESSIONID=` (ne jamais la partager).
4. `.venv\Scripts\python -m esg.fetch`, contrôler avec
   `.venv\Scripts\python -m esg.parse_fields berkeley OP-5`, puis relancer le pipeline.

Cette extension n'a pas pu être testée sur de vraies pages (pas de compte AASHE).

## Structure

```
esg/
  config.py        chemins, universités, modèles Ollama
  validate.py      étape 0 : validation du CSV de Hakim
  facts.py         table des faits (seule source des chiffres) + niveaux qualitatifs
  frameworks.py    table STARS -> GRI / TCFD / ESRS
  gri_index.py     statuts des 86 publications GRI (14 normes)
  sources.py       textes STARS : retrait du texte d'aide, suppression des nombres
  rag.py           embeddings nomic-embed-text + recherche par similarité
  llm.py           client Ollama (chat, JSON contraint, embeddings)
  guard.py         garde-fou des chiffres, réparation, traçabilité
  judge.py         juge LLM + règles déterministes
  generate.py      boucle rédaction -> garde-fou -> juge -> régénération
  render.py        Markdown, HTML, PDF, index GRI, annexes, provenance
  review.py        relecture hors pipeline (relecture/*.yaml) appliquée au rendu
  docx_export.py   export Word
  dashboard.py     tableau de bord HTML
  chat.py          assistant de questions-réponses
  demo.py          démonstrations pour la soutenance
  pipeline.py      commande principale
  verify.py        contrôle de chiffres tirés au hasard contre le CSV (verify_univ.py : par université)
  fetch.py         extension facultative, adaptée du code de Hakim (crédité)
  parse_fields.py  extension facultative, non testée sur de vraies pages
mapping/           correspondances écrites à la main (GRI, TCFD, ESRS)
relecture/         corrections de relecture par université (passage, raison, source STARS)
data/raw/          données de Hakim (inchangées)
tests/             tests automatiques
```

## Données et attribution

- Données STARS collectées et structurées par **Hakim Chaanbi**
  ([hakimchaanbi/esg-reporting](https://github.com/hakimchaanbi/esg-reporting)).
- Source : *[Institution] STARS Report. AASHE. [date]. reports.aashe.org.* Les données STARS sont
  accessibles publiquement et utilisées avec attribution à l'AASHE ; elles **ne sont pas** sous
  licence ouverte et sont autodéclarées.

| Université | Note | Score | Date du rapport STARS |
|---|---|---|---|
| UC Berkeley | Platinum | 86.76 | 2025-02-19 |
| University College Cork | Platinum | 85.99 | 2026-03-05 |
| TU Dublin | Gold | 83.35 | 2024-12-02 |
