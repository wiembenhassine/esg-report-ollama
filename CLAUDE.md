# CLAUDE.md — esg-report-ollama

Rapport ESG « en référence aux » normes GRI pour 3 universités STARS (Berkeley, Cork,
TU Dublin), généré par un LLM local (Ollama) avec validation automatique. Projet de
Wiem Ben Hassine ; données initiales de Hakim Chaanbi (hakimchaanbi/esg-reporting).
Les livrables (rapports) sont en **français**.

## Règles non négociables

1. **Le LLM n'écrit jamais un chiffre.** Il écrit des placeholders `{{ ID }}` ; le code
   (Jinja2 StrictUndefined) insère les valeurs de `facts.csv`. Le contexte qu'il reçoit est
   masqué (`sources.mask_numbers`). Ne jamais passer une valeur dans un prompt du rédacteur.
   Le juge, lui, peut voir les valeurs (il n'écrit pas le rapport).
2. **La correspondance STARS → GRI est écrite à la main** (`mapping/gri_map.yaml`), jamais
   générée par un LLM. Les statuts GRI sont calculés par `gri_index.py`.
3. **Pas de statut « Rapporté » sans valeur extraite** (test `test_mapping.py`).
4. Formulations : « en référence aux normes GRI » ; une donnée absente = « ce rapport ne peut
   pas établir », jamais « l'université n'a pas fait ».

## Pièges connus

- **CPU uniquement, RAM juste** : `llama3.1:8b` ≈ 2–4 tokens/s. Garder les prompts courts
  (`rag.evidence` max_chars, `num_ctx` 4096). Sections en cache (`outputs/cache`), clé =
  hash du prompt : modifier un prompt invalide le cache de cette section.
- **Pages STARS détaillées = compte AASHE** (cookie `AASHE_SESSIONID` dans `.env`, ignoré par
  git). Sans elles, seules les données de score et les récits existent ; les publications
  chiffrées restent « Non évalué ». `parse_fields.py` est heuristique (lignes libellé/valeur) :
  le vérifier avec `python -m esg.parse_fields <univ> <CODE>` dès la première extraction réelle.
- **Texte d'aide STARS** : retiré en supprimant les lignes communes à ≥ 2 institutions pour un
  même crédit (`sources.load_all`).
- **Périmètres différents** : Cork exclut ses filiales (Campus Accommodation…) → ratios par
  personne non comparables. TU Dublin : PA-4/PA-5 non applicables (pas de fonds de dotation).
- STARS v2.2 et v3.0 ne sont pas comparables (notation des crédits Opérations différente).
- `nomic-embed-text` exige les préfixes `search_document:` / `search_query:`.
- **Nombres du contexte supprimés, pas masqués** : un marqueur « [n] » était recopié par le
  modèle. `guard.repair` retire les phrases fautives (suppression seulement) au lieu de jeter
  tout le texte ; au-delà de 40 % de suppression, la version est rejetée.
- **Juge 8B bruité** : il invente des violations (« revendique la conformité GRI ») et en rate
  d'autres. `judge.judge` écarte celles que le code réfute ; l'acceptation repose sur la
  fidélité (≥ 80 %) plus la note (≥ 3/5) ou des violations toutes écartées. Les points de
  vigilance et les tableaux d'indicateurs sont rendus par le code, pas confiés au modèle.
- Sortie du rédacteur coupée par `num_predict` : `guard.tidy` retire la phrase incomplète.
- Une section en « repli » n'est jamais reprise du cache ; une nouvelle série change la graine.
- Lancer les longues exécutions en processus détaché (`Start-Process`) avec un journal dans
  `outputs/logs/` ; une mise en veille du PC tue la génération (le cache permet de reprendre).
- Console Windows : `sys.stdout.reconfigure(encoding="utf-8")` dans les points d'entrée.

## Commandes

```
.venv\Scripts\python -m esg.pipeline [univ...] [--sections ...] [--dry-run] [--render-only] [--no-cache]
.venv\Scripts\python -m pytest
```
