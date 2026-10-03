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

from esg import facts, gri_index, guard, judge, llm, rag, sources
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
- Pour citer une valeur, recopie exactement son placeholder, par exemple {{ OP6_score }}, tel qu'il figure
  dans la liste VALEURS. Le code le remplacera par la vraie valeur. Tu ne connais pas les valeurs.
- Une valeur sans placeholder ne doit pas être mentionnée. Les « [n] » du contexte sont des nombres masqués :
  ne les reproduis jamais et ne les remplace pas par une estimation.
- Autorisé : les références GRI (« GRI 305-1 ») et les codes de crédits STARS (« OP-6 »).

FIDÉLITÉ
- N'utilise que les informations du CONTEXTE, des VALEURS, des STATUTS et des POINTS DE VIGILANCE.
- N'invente aucun programme, organe, politique, nom ou engagement.
- Pour qualifier un score, utilise uniquement le niveau fourni (maximal, élevé, intermédiaire, faible, nul).
- Si une publication n'est pas couverte, écris « ce rapport ne peut pas établir… » ou « STARS ne collecte pas… » ;
  n'affirme jamais que l'université n'a pas fait quelque chose.
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
    """Faits proposés au rédacteur pour cette section : {placeholder: ligne de fait}."""
    f = facts.load(key)
    out = {}
    for code in sec["credits"]:
        v = facts.credit_var(code)
        for suffix in ("_score", "_max"):
            if v + suffix in f:
                out[v + suffix] = f[v + suffix]
    pillar = SECTION_PILLAR.get(sec["id"])
    if pillar == "STARS":
        out["STARS_score"] = f["STARS_score"]
        out["STARS_date"] = f["STARS_date"]
    elif pillar:
        for suffix in ("_points", "_max", "_pct"):
            if pillar + suffix in f:
                out[pillar + suffix] = f[pillar + suffix]
    for e in entries:
        for fid in e.fact_ids:
            out[fid] = f[fid]
    return out


def describe_values(key: str, values: dict) -> list[str]:
    b = facts.bands(key)
    lines = []
    for name, r in values.items():
        level = ""
        if r["kind"] == "score":
            level = f" — niveau : {b.get(r['credit_code'], '')}"
        elif name.endswith("_pct"):
            level = f" — niveau : {b.get(name[:3], '')}"
        lines.append(f"- {{{{ {name} }}}} : {r['label']}{level}")
    return lines


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
    parts.append("VALEURS (placeholders à recopier tels quels) :\n" + "\n".join(describe_values(key, values)))
    if cautions:
        parts.append("POINTS DE VIGILANCE OBLIGATOIRES :\n" + "\n".join(f"- {c}" for c in cautions))
    parts.append("CONTEXTE — extraits du rapport STARS de l'établissement (anglais, nombres masqués) :\n"
                 + "\n".join(f"[{p['credit']}] {p['text']}" for p in evidence))
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


def _cache_path(key: str, sec_id: str):
    return OUTPUTS / "cache" / key / f"{sec_id}.json"


def validated_generation(*, tag: str, prompt: str, values: dict, judge_statuses: list[str],
                         cautions: list[str], judge_evidence: list[str], section_codes: list[str],
                         fallback: str, cache, use_cache: bool = True, log=print) -> dict:
    """Boucle rédaction -> garde-fou -> substitution -> juge -> régénération (voir docstring du module)."""
    prompt_hash = hashlib.sha256((WRITER_SYSTEM + prompt).encode("utf-8")).hexdigest()[:16]
    if use_cache and cache.exists():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached.get("prompt_hash") == prompt_hash and cached.get("decision") != "repli":
            log(f"   [{tag}] depuis le cache ({cached['decision']})")
            return cached

    judge_values = [f"{r['label']}: {r['display']}" for r in values.values()]
    attempts, feedback = [], []
    t0 = time.time()
    for n in range(1, MAX_ATTEMPTS + 1):
        user = prompt
        if feedback:
            user += ("\n\nCORRECTIONS OBLIGATOIRES (ta version précédente a été rejetée) :\n"
                     + "\n".join(f"- {x}" for x in feedback))
        user += "\n\nRédige maintenant la section."
        out = llm.chat([{"role": "system", "content": WRITER_SYSTEM}, {"role": "user", "content": user}])
        draft = out["text"].strip()
        att = {"attempt": n, "draft": draft, "gen_seconds": out["seconds"],
               "prompt_tokens": out["prompt_tokens"], "output_tokens": out["output_tokens"]}

        problems = guard.check_draft(draft, set(values))
        att["raw_guard_problems"], att["removed_sentences"] = problems, []
        if problems:
            # Le code retire les phrases fautives ; trop de suppressions = version rejetée.
            repaired, removed = guard.repair(draft, set(values))
            if (len(" ".join(removed).split()) <= 0.4 * len(draft.split())
                    and not guard.check_draft(repaired, set(values))):
                log(f"   [{tag}] tentative {n} : {len(removed)} phrase(s) contenant un nombre retirée(s) par le garde-fou")
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
        att["rendered"], att["used_facts"], att["trace_problems"] = rendered, sorted(used), trace_problems
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
        "decision": decision,
        "text": best["rendered"] if best else fallback,
        "used_facts": best["used_facts"] if best else [],
        "judge_score": best["judge"]["score"] if best else None,
        "faithfulness": best["judge"]["faithfulness"] if best else None,
        "gri_coverage": best["gri_coverage"] if best else None,
        "unsupported_claims": [c["claim"] for c in best["judge"]["claims"] if not c["supported"]] if best else [],
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
    evidence = ix.evidence(key, sec["credits"], sec["topic"])
    knowledge = [dict(p, text=p["text"][:400]) for p in ix.knowledge(sec["topic"], k=1)]
    values = section_values(key, sec, entries)
    cache = _cache_path(key, sec_id)
    result = validated_generation(
        tag=f"{key}/{sec_id}",
        prompt=build_prompt(key, sec, evidence, knowledge, values, entries, cautions),
        values=values,
        judge_statuses=[f"GRI {e.code}: {e.status_label}" for e in entries],
        cautions=cautions,
        judge_evidence=[f"[{p['credit']}] {p['text']}" for p in evidence],
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
    out = {}
    for key in INSTITUTIONS:
        f = facts.load(key)
        for fid in ("STARS_score", "ENV_pct", "SOC_pct", "GOV_pct", "CTX_pct"):
            r = dict(f[fid])
            r["label"] = f"{INSTITUTIONS[key]['name']} — {r['label']}"
            out[f"{key}_{fid}"] = r
    return out


def run_comparison(*, use_cache: bool = True, log=print) -> dict:
    values = comparison_values()
    lines = []
    for name, r in values.items():
        key, fid = name.split("_", 1)
        level = facts.bands(key).get(fid[:3], "") if fid.endswith("_pct") else ""
        lines.append(f"- {{{{ {name} }}}} : {r['label']}" + (f" — niveau : {level}" if level else ""))
    ratings = "; ".join(f"{INSTITUTIONS[k]['name']} : note STARS « {sources.header(k)['rating']} »"
                        for k in INSTITUTIONS)
    prompt = "\n\n".join([
        "ÉTABLISSEMENTS : " + ratings + ".",
        "SECTION À RÉDIGER : Synthèse comparative des trois établissements "
        "(résultats STARS par pilier et limites de la comparaison). Ici, ne cite pas de publication GRI.",
        "VALEURS (placeholders à recopier tels quels) :\n" + "\n".join(lines),
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
