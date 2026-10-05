"""
Génération d'une section : rédaction -> garde-fou -> substitution -> juge -> régénération.

    LLM (placeholders, aucun chiffre)
        │
        ▼
    guard.check_draft + judge.lint ── échec ──► nouvelle tentative avec les corrections
        │ ok
        ▼
    Jinja2 StrictUndefined (le CODE insère les valeurs de facts.csv)
        │
        ▼
    guard.check_rendered (tout nombre doit venir d'un fait)
        │
        ▼
    juge Ollama ── refus ──► nouvelle tentative avec la consigne du juge
        │ accepté
        ▼
    section validée (mise en cache)

Après MAX_ATTEMPTS refus : la meilleure version sûre (garde-fou passé) est
gardée mais marquée « à relire » (validation humaine) si sa fidélité reste
correcte ; sinon un texte de repli écrit par le code est utilisé.
"""

import hashlib
import json
import time

from jinja2 import Environment, StrictUndefined

from esg import facts, gri_index, guard, judge, llm, markers, rag, sources
from esg.config import INSTITUTIONS, OUTPUTS

MAX_ATTEMPTS = 2          # CPU lent : une régénération au plus
HUMAN_REVIEW_FAITHFULNESS = 0.6
JINJA = Environment(undefined=StrictUndefined, autoescape=False)

SECTION_PILLAR = {"organisation": "STARS", "gouvernance": "GOV", "strategie": "GOV",
                  "environnement": "ENV", "social": "SOC", "enseignement": "CTX",
                  "parties_prenantes": None, "materialite": None}

WRITER_SYSTEM = """Tu rédiges UNE section d'un rapport de durabilité universitaire établi « en référence aux normes GRI ».
Langue : français uniquement. Ton : factuel, sobre, style rapport institutionnel.

RÈGLE ABSOLUE SUR LES NOMBRES
- N'écris AUCUN nombre : ni chiffre, ni nombre en lettres, ni année, ni date, ni pourcentage.
- Pour citer une valeur, recopie exactement son marqueur, par exemple {{ OP6 }}, tel qu'il figure dans la
  liste VALEURS. Le code le remplace par une expression COMPLÈTE (par exemple « … points STARS sur … au crédit
  OP-6, niveau intermédiaire ») : écris simplement « L'université obtient {{ OP6 }}. ». N'ajoute autour du
  marqueur ni « points », ni « % », ni niveau, et ne l'emploie jamais comme date, durée, quantité ou effectif.
- Dans le CONTEXTE, les années et pourcentages cités par l'établissement sont remplacés par des marqueurs
  (par exemple {{ PA2_t0_3 }}) : tu peux les recopier, dans le même sens que dans l'extrait (« d'ici {{ PA2_t0_3 }} »).
- Les autres nombres ont été retirés : ne les devine pas, et n'écris pas de phrase qui en aurait besoin
  (« d'ici . », « produit de MWh ») ; décris alors le dispositif sans quantité.
- Autorisé : les références GRI (« GRI 305-1 ») et les codes de crédits STARS (« OP-6 »).

FIDÉLITÉ
- N'utilise que les informations du CONTEXTE, des VALEURS, des STATUTS et des POINTS DE VIGILANCE.
- N'invente aucun programme, organe, politique, nom ou engagement.
- Pour qualifier un score, utilise uniquement le niveau fourni (maximal, élevé, intermédiaire, faible, nul).
- Si une publication n'est pas couverte, écris « ce rapport ne peut pas établir… » ou « STARS ne collecte pas… » ;
  n'affirme jamais que l'université n'a pas fait quelque chose.
- Les domaines d'objectifs STARS sont fixés par STARS : n'écris jamais que l'université « a identifié » ou
  « a déterminé » ses thèmes matériels.
- Ne développe un sigle que s'il figure dans le lexique SIGLES ou s'il est développé dans le CONTEXTE.
- Respecte chaque POINT DE VIGILANCE.
- Écris « en référence aux normes GRI », jamais « conforme ».

FORME
- Markdown, entre 180 et 300 mots, deux à quatre sous-titres « ### », pas de titre principal.
- Chaque paragraphe se termine par la référence entre parenthèses de la publication GRI qu'il traite,
  prise dans la liste STATUTS, sous la forme (GRI X-Y).

CONTENU ATTENDU
- La plus grande partie du texte décrit CONCRÈTEMENT ce que l'établissement déclare dans le CONTEXTE :
  organes, plans, politiques, dispositifs, sites, en les nommant tels qu'ils apparaissent (noms propres
  conservés en anglais si besoin), reformulés en français. Pas de phrases génériques valables pour
  n'importe quelle université.
- Puis la sous-partie « Limites et omissions » explique ce que les données ne permettent pas d'établir.
- Termine par un sous-titre « ### Limites et omissions » qui résume ce que les données ne couvrent pas.
- Pas d'introduction générique, pas de conclusion, pas de liste de sources."""


def section_values(key: str, sec: dict, entries: list) -> dict[str, dict]:
    """Marqueurs proposés au rédacteur pour cette section : {nom: marqueur complet} (voir esg/markers.py)."""
    out = {}
    for code in sec["credits"]:
        mk = markers.credit(key, code)
        if mk:
            out[facts.credit_var(code)] = mk
    pillar = SECTION_PILLAR.get(sec["id"])
    if pillar == "STARS":
        out["STARS_score"] = markers.overall(key)
        out["STARS_date"] = markers.date(key)
    elif pillar:
        mk = markers.pillar(key, pillar)
        if mk:
            out[pillar] = mk
    for e in entries:
        for fid in e.fact_ids:
            out[fid] = markers.field(key, fid)
    return out


def describe_values(key: str, values: dict) -> list[str]:
    return [markers.describe(name, mk) for name, mk in values.items()]


def status_lines(entries: list) -> list[str]:
    covered = [f"- GRI {e.code} {e.title} — {e.status_label}. {e.note}".rstrip()
               for e in entries if e.status != "none"]
    absent = [f"GRI {e.code}" for e in entries if e.status == "none"]
    if absent:
        covered.append("- Non couvertes par STARS (Non rapporté) : " + ", ".join(absent))
    return covered


def build_prompt(key: str, sec: dict, evidence: list[dict], knowledge: list[dict],
                 values: dict, entries: list, cautions: list[str]) -> str:
    inst = INSTITUTIONS[key]
    rating = sources.header(key).get("rating", "")
    parts = [
        f"ÉTABLISSEMENT : {inst['name']} ({inst['country']}), rapport AASHE STARS 3.0, note STARS « {rating} ».",
        f"SECTION À RÉDIGER : {sec['title']}",
    ]
    if entries:
        parts.append("STATUTS DES PUBLICATIONS GRI (calculés par le code, à respecter) :\n" + "\n".join(status_lines(entries)))
    if sec.get("gap_note"):
        parts.append("À EXPLIQUER : " + sec["gap_note"])
    parts.append("VALEURS (marqueurs à recopier tels quels, sans rien autour) :\n" + "\n".join(describe_values(key, values)))
    if cautions:
        parts.append("POINTS DE VIGILANCE OBLIGATOIRES :\n" + "\n".join(f"- {c}" for c in cautions))
    parts.append("CONTEXTE — extraits du rapport STARS de l'établissement (anglais ; années et pourcentages "
                 "remplacés par des marqueurs, autres nombres retirés) :\n"
                 + "\n".join(f"[{p['credit']}] {p['text']}" for p in evidence))
    sigles = guard.glossary_lines(*(p["text"] for p in evidence))
    if sigles:
        parts.append("SIGLES (lexique ; ne développe aucun autre sigle que ceux-ci ou ceux développés dans le "
                     "CONTEXTE) :\n" + "\n".join(sigles))
    if knowledge:
        parts.append("VOCABULAIRE ESG (référence générale, ne pas citer comme fait sur l'établissement) :\n"
                     + "\n".join(p["text"] for p in knowledge))
    return "\n\n".join(parts)


def fallback_text(key: str, sec: dict, entries: list, values: dict) -> str:
    """Texte de repli entièrement écrit par le code (aucune affirmation hors données)."""
    f = facts.load(key)
    lines = ["*Section de repli générée par le code : aucune version rédigée par le modèle n'a passé la validation.*", ""]
    scored = [c for c in sec["credits"] if facts.credit_var(c) + "_score" in f]
    if scored:
        lines.append("### Résultats STARS des crédits concernés")
        for c in scored:
            v = facts.credit_var(c)
            lines.append(f"- {c} — {f[v + '_score']['label'].split('— ')[-1]} : "
                         f"{f[v + '_score']['display']} / {f[v + '_max']['display']} points")
    if entries:
        lines.append("")
        lines.append("### Statut des publications GRI")
        for e in entries:
            lines.append(f"- GRI {e.code} {e.title} : {e.status_label.lower()}.")
    return "\n".join(lines)


def judge_values_of(values: dict) -> list[str]:
    """Valeurs vues par le juge : le texte complet que le code insère (niveau compris), pour qu'il le vérifie."""
    return [f"{mk['label']}: {mk['display']}" for mk in values.values()]


def _cache_path(key: str, sec_id: str):
    return OUTPUTS / "cache" / key / f"{sec_id}.json"


def validated_generation(*, tag: str, prompt: str, values: dict, judge_statuses: list[str],
                         cautions: list[str], judge_evidence: list[str], section_codes: list[str],
                         fallback: str, cache, use_cache: bool = True, log=print) -> dict:
    """Boucle rédaction -> garde-fou -> substitution -> juge -> régénération (voir docstring du module)."""
    prompt_hash = hashlib.sha256((WRITER_SYSTEM + prompt).encode("utf-8")).hexdigest()[:16]
    round_ = 0                      # nouvelle série après un repli : autre graine, sinon même texte
    if use_cache and cache.exists():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached.get("prompt_hash") == prompt_hash and cached.get("decision") != "repli":
            log(f"   [{tag}] depuis le cache ({cached['decision']})")
            return cached
        round_ = cached.get("round", 0) + 1

    judge_values = judge_values_of(values)
    attempts, feedback = [], []
    t0 = time.time()
    for n in range(1, MAX_ATTEMPTS + 1):
        user = prompt
        if feedback:
            user += ("\n\nCORRECTIONS OBLIGATOIRES (ta version précédente a été rejetée) :\n"
                     + "\n".join(f"- {x}" for x in feedback))
        user += "\n\nRédige maintenant la section."
        out = llm.chat([{"role": "system", "content": WRITER_SYSTEM}, {"role": "user", "content": user}],
                       seed=42 + 100 * round_ + n, num_predict=700)
        draft = guard.tidy(out["text"])
        att = {"attempt": n, "draft": draft, "gen_seconds": out["seconds"],
               "prompt_tokens": out["prompt_tokens"], "output_tokens": out["output_tokens"]}

        problems = guard.check_draft(draft, set(values), values)
        att["raw_guard_problems"], att["removed_sentences"] = problems, []
        if problems:
            # Le code retire les phrases fautives ; trop de suppressions = version rejetée.
            repaired, removed = guard.repair(draft, set(values), values)
            if (len(" ".join(removed).split()) <= 0.4 * len(draft.split())
                    and not guard.check_draft(repaired, set(values), values)):
                log(f"   [{tag}] tentative {n} : {len(removed)} phrase(s) retirée(s) par le garde-fou "
                    f"(nombre écrit par le modèle ou marqueur mal employé)")
                draft, problems, att["removed_sentences"] = repaired, [], removed
        lint_problems, lint_notes, coverage = judge.lint(guard.PLACEHOLDER.sub("X", draft), section_codes)
        att["guard_problems"], att["lint_problems"], att["gri_coverage"] = problems, lint_problems, coverage
        att["lint_notes"] = lint_notes
        if problems or lint_problems:
            log(f"   [{tag}] tentative {n} rejetée par le garde-fou : " + " ; ".join((problems + lint_problems)[:3]))
            attempts.append(att)
            feedback = (problems + lint_problems)[:10]
            continue

        used = set(guard.PLACEHOLDER.findall(draft))
        substituted = {name: values[name]["display"] for name in used}
        rendered = JINJA.from_string(draft).render(**substituted)
        trace_problems = guard.check_rendered(rendered, substituted)
        fact_ids = sorted({fid for name in used for fid in values[name]["fact_ids"]})   # provenance
        att["rendered"], att["used_facts"], att["trace_problems"] = rendered, fact_ids, trace_problems
        att["used_markers"] = sorted(used)
        if trace_problems:                                   # ne devrait jamais arriver
            attempts.append(att)
            feedback = trace_problems
            continue

        verdict = judge.judge(rendered, judge_values, judge_statuses, cautions, judge_evidence)
        att["judge"] = verdict
        attempts.append(att)
        log(f"   [{tag}] tentative {n} : juge {verdict['score']}/5, "
            f"fidélité {verdict['faithfulness']:.0%} -> {'acceptée' if verdict['accepted'] else 'refusée'}")
        if verdict["accepted"]:
            break
        unsupported = [c["claim"] for c in verdict.get("claims", []) if not c.get("supported")]
        feedback = ([verdict["feedback"]] if verdict.get("feedback") else []) \
            + [f"retire ou corrige cette affirmation non supportée par les sources : « {c} »" for c in unsupported] \
            + verdict.get("rule_violations", []) + lint_notes
        feedback = [x for x in feedback if x][:10]

    judged = [a for a in attempts if "judge" in a]
    accepted = [a for a in judged if a["judge"]["accepted"]]
    if accepted:
        best, decision = accepted[-1], "validée"
    elif judged and max(a["judge"]["faithfulness"] for a in judged) >= HUMAN_REVIEW_FAITHFULNESS:
        best = max(judged, key=lambda a: (a["judge"]["score"], a["judge"]["faithfulness"]))
        decision = "à relire"
    else:
        best, decision = None, "repli"

    result = {
        "prompt_hash": prompt_hash,
        "round": round_,
        "decision": decision,
        "text": best["rendered"] if best else fallback,
        "used_facts": best["used_facts"] if best else [],
        "judge_score": best["judge"]["score"] if best else None,
        "faithfulness": best["judge"]["faithfulness"] if best else None,
        "gri_coverage": best["gri_coverage"] if best else None,
        "unsupported_claims": [c["claim"] for c in best["judge"]["claims"] if not c["supported"]] if best else [],
        "discarded_violations": best["judge"].get("discarded_violations", []) if best else [],
        "attempts": len(attempts),
        "guard_rejections": sum(1 for a in attempts if a["guard_problems"] or a["lint_problems"]),
        "seconds": round(time.time() - t0, 1),
        "history": attempts,
    }
    log(f"   [{tag}] {decision} en {result['seconds']:.0f} s ({len(attempts)} tentative(s))")
    return result


def _save(cache, result: dict) -> dict:
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def dry_section(key: str, sec_id: str) -> dict:
    """Section sans LLM (texte de repli du code) : sert à tester le rendu rapidement."""
    sec = gri_index.section(sec_id)
    entries = [gri_index.entry(key, c) for c in sec["disclosures"]]
    return {"institution": key, "section": sec_id, "title": sec["title"], "decision": "repli",
            "text": fallback_text(key, sec, entries, section_values(key, sec, entries)),
            "used_facts": [], "judge_score": None, "faithfulness": None, "gri_coverage": None,
            "unsupported_claims": [], "attempts": 0, "guard_rejections": 0, "seconds": 0.0, "history": []}


def run_section(key: str, sec_id: str, *, use_cache: bool = True, log=print) -> dict:
    sec = gri_index.section(sec_id)
    entries = [gri_index.entry(key, c) for c in sec["disclosures"]]
    cautions = gri_index.cautions(key, sec_id)
    ix = rag.get_index()
    raw_evidence = ix.evidence(key, sec["credits"], sec["topic"])
    # Années et % des extraits -> marqueurs « texte » ; le juge, lui, lit les extraits avec leurs nombres.
    evidence, judge_lines, text_markers = markers.evidence_markers(key, raw_evidence)
    knowledge = [dict(p, text=p["text"][:400]) for p in ix.knowledge(sec["topic"], k=1)]
    values = section_values(key, sec, entries) | text_markers
    cache = _cache_path(key, sec_id)
    result = validated_generation(
        tag=f"{key}/{sec_id}",
        prompt=build_prompt(key, sec, evidence, knowledge, values, entries, cautions),
        values=values,
        judge_statuses=[f"GRI {e.code}: {e.status_label}" for e in entries],
        cautions=cautions,
        judge_evidence=judge_lines,
        section_codes=[e.code for e in entries if e.status != "none"] or [e.code for e in entries],
        fallback=fallback_text(key, sec, entries, values),
        cache=cache, use_cache=use_cache, log=log)
    if "institution" in result:                      # venu du cache
        return result
    result.update({"institution": key, "section": sec_id, "title": sec["title"],
                   "evidence": [{"credit": p["credit"], "text": p["text"]} for p in evidence]})
    return _save(cache, result)


COMPARISON_CAUTIONS = [
    "Les trois établissements n'ont pas le même périmètre de reporting (Cork exclut ses filiales) : "
    "un écart ne doit jamais être présenté comme une pure différence de performance.",
    "Les scores STARS sont autodéclarés et notés par rapport à un groupe de pairs (STARS 3.0) ; "
    "ils ne sont pas vérifiés par l'AASHE.",
    "TU Dublin n'a pas de fonds de dotation : ses crédits d'investissement PA-4 et PA-5 sont non applicables, "
    "ce qui change la base de son pilier Gouvernance.",
    "Les dates de soumission diffèrent d'un établissement à l'autre.",
]


def comparison_values() -> dict[str, dict]:
    """Marqueurs complets des trois établissements (score global et piliers), préfixés par l'université."""
    out = {}
    for key in INSTITUTIONS:
        name = INSTITUTIONS[key]["name"]
        items = [("STARS_score", markers.overall(key))] + [(pid, markers.pillar(key, pid)) for pid in markers.PILLARS]
        for suffix, mk in items:
            if mk:
                mk = dict(mk, label=f"{name} — {mk['label']}",
                          display=f"{mk['display']} ({name})" if suffix == "STARS_score" else mk["display"],
                          fact_ids=[f"{key}:{fid}" for fid in mk["fact_ids"]])
                out[f"{key}_{suffix}"] = mk
    return out


def run_comparison(*, use_cache: bool = True, log=print) -> dict:
    values = comparison_values()
    lines = [markers.describe(name, mk) for name, mk in values.items()]
    ratings = "; ".join(f"{INSTITUTIONS[k]['name']} : note STARS « {sources.header(k)['rating']} »"
                        for k in INSTITUTIONS)
    prompt = "\n\n".join([
        "ÉTABLISSEMENTS : " + ratings + ".",
        "SECTION À RÉDIGER : Analyse de la comparaison des trois établissements. Le tableau des scores par "
        "pilier est déjà affiché par le code au-dessus de ta section : ne recopie pas pilier par pilier les "
        "niveaux de chaque établissement. Explique plutôt ce que les écarts entre établissements peuvent "
        "signifier et surtout ce qu'ils ne permettent pas de conclure, en t'appuyant sur les POINTS DE "
        "VIGILANCE. Si tu cites un niveau, recopie exactement celui de la liste VALEURS pour cet "
        "établissement et ce pilier. EXCEPTION aux règles de forme : cette section ne correspond à aucune "
        "publication GRI, n'écris donc aucune référence « GRI ».",
        "VALEURS (marqueurs à recopier tels quels, sans rien autour) :\n" + "\n".join(lines),
        "POINTS DE VIGILANCE OBLIGATOIRES :\n" + "\n".join(f"- {c}" for c in COMPARISON_CAUTIONS),
        "CONTEXTE : les piliers regroupent les crédits STARS : Environnement = OP ; Social = PA-6 à PA-13 ; "
        "Gouvernance = PA-1 à PA-5 ; Enseignement, recherche et engagement = AC et EN. Ce regroupement est un "
        "choix raisonné du projet, pas une désignation officielle STARS.",
    ])
    cache = OUTPUTS / "cache" / "comparatif.json"
    result = validated_generation(
        tag="comparatif", prompt=prompt, values=values, judge_statuses=[],
        cautions=COMPARISON_CAUTIONS, judge_evidence=[], section_codes=[],
        fallback="*Section de repli générée par le code : voir le tableau comparatif ci-dessus.*",
        cache=cache, use_cache=use_cache, log=log)
    if "section" in result:
        return result
    result.update({"institution": "comparatif", "section": "comparatif", "title": "Synthèse comparative"})
    return _save(cache, result)
