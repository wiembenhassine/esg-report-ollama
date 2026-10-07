"""
Assemblage et rendu : Markdown -> HTML -> PDF (Edge/Chrome headless, déjà présent sous Windows).

Tout ce qui est écrit ici est écrit par le CODE (tableaux, index GRI, annexe de
validation, textes fixes). Seules les sections narratives viennent du LLM, déjà
validées par esg.generate.
"""

import csv
import datetime as dt
import html
import shutil
import subprocess
import time
from pathlib import Path

import markdown

from esg import docx_export, facts, generate, gri_index, guard, markers, names, review, sources, style
from esg.config import GEN_MODEL, INSTITUTIONS, OUTPUTS, PROCESSED, report_url

PILLAR_ORDER = [("ENV", "Environnement"), ("SOC", "Social"), ("GOV", "Gouvernance"),
                ("CTX", "Enseignement, recherche et engagement")]
STATUS_CLASS = {"reported": "ok", "partial": "part", "none": "no", "pending": "pend"}
DECISION_CLASS = {"validée": "ok", "à relire": "part", "repli": "no"}


def esc(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def badge(text: str, cls: str) -> str:
    return f'<span class="badge {cls}">{html.escape(text)}</span>'


# ------------------------------------------------------------------ blocs fixes
def about(key: str) -> str:
    inst = INSTITUTIONS[key]
    head = sources.header(key)
    f = facts.load(key)
    has_fields = any(r["kind"] == "field" for r in f.values())
    n_disc = len(gri_index.load_map()["disclosures"])
    n_std = len(gri_index.load_map()["standards"])
    scope = (
        "Les valeurs détaillées des champs STARS (énergie, émissions, eau, déchets, effectifs…) ont été extraites "
        "des pages authentifiées et alimentent les publications concernées."
        if has_fields else
        "Cette version s'appuie sur les scores publics par crédit et sur les réponses narratives de "
        "l'établissement. Les valeurs détaillées des champs STARS (énergie, émissions, eau, déchets, effectifs…) "
        "exigent un accès authentifié AASHE et n'ont pas encore été extraites : les publications qui en dépendent "
        "sont marquées « Non évalué » plutôt que d'être devinées."
    )
    return f"""**À propos de ce rapport.** Ce rapport est généré automatiquement à partir de la soumission publique
AASHE STARS 3.0 de {inst['name']} ({f['STARS_date']['display']}), mise en correspondance avec les normes GRI.
Il examine les {n_disc} publications GRI de {n_std} normes (dont GRI 101: Biodiversité 2024). Lorsqu'une publication ne peut pas être renseignée à partir
des données STARS, il le dit et explique pourquoi, au lieu d'omettre la question.

**D'où viennent les chiffres, et pourquoi s'y fier.** Le modèle de langage qui rédige le texte
({GEN_MODEL}, exécuté localement avec Ollama) n'a jamais vu un chiffre : les nombres de son contexte sont
masqués, et il écrit des marqueurs nommés que le code remplace ensuite par les valeurs de la table des faits.
Un garde-fou déterministe rejette toute section où le modèle a écrit lui-même un nombre, puis chaque nombre du
texte final est contrôlé contre cette table. Le modèle choisit les phrases ; il ne choisit pas les chiffres.

**Validation automatique.** Chaque section est ensuite auditée par le modèle configuré en juge : il découpe le
texte en affirmations, vérifie chacune contre les sources, contrôle les règles de reporting et note la section.
Une section refusée est régénérée avec les corrections demandées. Le détail figure en annexe « Validation du
rapport ».

**Ce que la garantie ne couvre pas.** Elle porte sur les chiffres. Les énoncés qualitatifs proviennent des
réponses narratives de l'établissement ; le juge les contrôle, mais un juge automatique peut se tromper. Les
sections marquées « à relire » demandent une validation humaine.

**« En référence aux » normes GRI, et non « conformément à ».** GRI réserve la mention « conformément » aux
rapports qui répondent à toutes les publications générales et à toutes celles de chaque thème matériel. Ce
rapport ne le fait pas : il revendique donc la mention plus faible, qui est la mention exacte.

**Portée des données.** {scope}

**Source et attribution.** [{inst['name']} STARS Report]({report_url(key)}), AASHE, note « {head.get('rating', '')} ».
Les données STARS sont accessibles publiquement et utilisées ici avec attribution à l'AASHE ; elles ne sont
pas sous licence ouverte et sont autodéclarées par l'établissement. Extraction initiale des données :
Hakim Chaanbi ([hakimchaanbi/esg-reporting](https://github.com/hakimchaanbi/esg-reporting))."""


def pillar_rows(key: str) -> list[dict]:
    f, b = facts.load(key), facts.bands(key)
    rows = []
    for pid, label in PILLAR_ORDER:
        if f"{pid}_pct" in f:
            rows.append({"pid": pid, "label": label, "points": f[f"{pid}_points"]["display"],
                         "max": f[f"{pid}_max"]["display"], "pct": f[f"{pid}_pct"]["display"],
                         "value": float(f[f"{pid}_pct"]["number"]), "level": b.get(pid, "")})
    return rows


def bar_chart(series: dict[str, list[tuple[str, float, str]]], width: int = 640) -> str:
    """Barres horizontales en SVG (aucune bibliothèque). series = {groupe: [(nom, valeur %, libellé)]}."""
    colors = ["#2f6f5e", "#c07a2c", "#4a6fa5"]
    row_h, gap, left = 18, 10, 250
    groups = list(series.items())
    n_series = max(len(v) for _, v in groups)
    height = len(groups) * (n_series * row_h + gap) + 30
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" xmlns="http://www.w3.org/2000/svg">']
    y = 10
    for g, items in groups:
        out.append(f'<text x="0" y="{y + n_series * row_h / 2 + 4}" class="lbl">{html.escape(g)}</text>')
        for i, (name, value, text) in enumerate(items):
            w = (width - left - 70) * value / 100
            out.append(f'<rect x="{left}" y="{y}" width="{w:.1f}" height="{row_h - 4}" rx="2" fill="{colors[i % 3]}">'
                       f'<title>{html.escape(name)} : {html.escape(text)}</title></rect>')
            out.append(f'<text x="{left + w + 6:.1f}" y="{y + row_h - 7}" class="val">{html.escape(text)}</text>')
            y += row_h
        y += gap
    out.append("</svg>")
    return "".join(out)


def stars_summary(key: str) -> str:
    f = facts.load(key)
    head = sources.header(key)
    rows = pillar_rows(key)
    md = [f"Note STARS : **{head.get('rating', '')}** — score global **{f['STARS_score']['display']}** sur 100.",
          "Les scores STARS 3.0 sont autodéclarés et notés par rapport à un groupe de pairs ; "
          "les piliers ci-dessous regroupent les crédits notés (regroupement du projet, pas une désignation STARS ; "
          "crédits bonus IL exclus).", "",
          "| Pilier | Points obtenus | Points possibles | Part obtenue | Niveau |",
          "|---|---:|---:|---:|---|"]
    for r in rows:
        md.append(f"| {r['label']} | {r['points']} | {r['max']} | {r['pct']} | {r['level']} |")
    md.append("")
    md.append(bar_chart({r["label"]: [(INSTITUTIONS[key]["name"], r["value"], r["pct"])] for r in rows}))
    return "\n".join(md)


def gri_index_md(key: str) -> str:
    entries = gri_index.index(key)
    c = gri_index.counts(entries)
    m = gri_index.load_map()
    f = facts.load(key)
    md = ["| Rapporté | Partiellement rapporté | Non rapporté | Non évalué |", "|:-:|:-:|:-:|:-:|",
          f"| {c['reported']} | {c['partial']} | {c['none']} | {c['pending']} |", "",
          "*Statuts calculés par le code à partir de la table de correspondance écrite à la main "
          "(`mapping/gri_map.yaml`). « Non évalué » : un champ STARS correspondant existe mais sa valeur n'a pas "
          "été extraite.*"]
    for std, title in m["standards"].items():
        rows = [e for e in entries if e.standard == std]
        md += ["", f"### {std} : {title}", "",
               "| Publication | Statut | Valeur ou justification | Remarques |", "|---|---|---|---|"]
        for e in rows:
            value = "<br>".join(f"{esc(f[i]['label'])} : **{f[i]['display']}**" for i in e.fact_ids) or esc(e.reason)
            md.append(f"| **{e.code}** {esc(e.title)} | {badge(e.status_label, STATUS_CLASS[e.status])} "
                      f"| {value} | {esc(e.note)} |")
    return "\n".join(md)


def frameworks_md() -> str:
    from esg import frameworks                      # import local : évite un cycle au chargement
    rows = frameworks.table()
    md = ["Correspondance **thématique** écrite à la main (`mapping/frameworks.yaml`, `mapping/gri_map.yaml`), "
          "jamais générée par le modèle. Un crédit sans équivalent est marqué « Aucune correspondance » plutôt que "
          "forcé. " + esc(frameworks.summary(rows)) + ".", "",
          "| Crédit STARS | GRI | TCFD | ESRS |", "|---|---|---|---|"]
    for r in rows:
        md.append(f"| **{r['credit_code']}** {esc(r['credit_name'])} | {esc(r['gri'])} | {esc(r['tcfd'])} | "
                  f"{esc(r['esrs'])} |")
    return "\n".join(md)


def validation_md(results: list[dict], key: str = "") -> str:
    essais = {1: "un essai", 2: "deux essais", 3: "trois essais"}.get(generate.MAX_ATTEMPTS,
                                                                    f"{generate.MAX_ATTEMPTS} essais")
    md = ["Chaque section narrative a suivi la boucle : rédaction (placeholders) → garde-fou des chiffres → "
          f"substitution par le code → audit par le juge → régénération si refus ({essais} au plus ; "
          "sinon texte de repli écrit par le code).", "",
          "| Section | Décision | Tentatives | Rejets garde-fou | Note du juge | Fidélité | Codes GRI cités dans le texte "
          "| Publications GRI avec données (index) | Durée |",
          "|---|---|:-:|:-:|:-:|:-:|:-:|:-:|--:|"]
    for r in results:
        md.append(
            f"| {esc(r['title'])} | {badge(r['decision'], DECISION_CLASS[r['decision']])} | {r['attempts']} | "
            f"{r['guard_rejections']} | {r['judge_score'] if r['judge_score'] else '—'}/5 | "
            f"{'' if r['faithfulness'] is None else f'{r['faithfulness']:.0%}'} | "
            f"{'—' if r['gri_coverage'] is None or not gri_with_data(key, r['section'])[1] else f'{r['gri_coverage']:.0%}'} | "
            f"{index_cell(key, r['section'])} | {r['seconds'] / 60:.1f} min |")
    md += ["", "*« Codes GRI cités dans le texte » : part des publications GRI de la section dont le code (par exemple "
               "GRI 305-1) est cité dans le texte rédigé ; c'est une mesure de citation, pas de couverture des données. "
               "« Publications GRI avec données » : publications de la section rapportées ou partiellement rapportées "
               "dans l'index de contenu GRI, sur le total de la section.*"]
    ok = sum(r["decision"] == "validée" for r in results)
    faiths = [r["faithfulness"] for r in results if r["faithfulness"] is not None]
    md += ["", f"**Bilan :** {ok} section(s) validée(s) sur {len(results)} ; fidélité moyenne "
               f"{(sum(faiths) / len(faiths)) if faiths else 0:.0%} ; "
               f"{sum(r['guard_rejections'] for r in results)} version(s) rejetée(s) par le garde-fou avant le juge. "
               "Aucun nombre du texte final n'a été écrit par le modèle."]
    disc = sum(len(r.get("discarded_violations", [])) for r in results)
    if disc:
        md += ["", f"{disc} violation(s) signalée(s) par le juge ont été écartées car contredites par le contrôle "
                   "déterministe (par exemple une « revendication de conformité GRI » absente du texte) : "
                   "le juge 8B se trompe parfois, le code tranche sur ce qu'il sait vérifier."]
    n_fix, n_sec = review.count(key) if key else (0, 0)
    if n_fix:
        md += ["", f"**Relecture hors pipeline** (6 octobre 2026) : {n_fix} correction(s) dans {n_sec} section(s). "
                   "Phrases supprimées ou reformulées à partir des textes STARS uniquement, sans chiffre tapé à la "
                   "main. Les corrections ont été proposées par l'assistant Claude Code (IA) à la demande de "
                   "Wiem Ben Hassine, chacune avec sa source STARS ; elles deviennent une relecture humaine une fois "
                   f"validées par elle. Liste détaillée : `relecture/{key}.yaml` et `outputs/relecture_humaine.md`. "
                   "Le texte écrit par le modèle reste consultable dans `outputs/cache/`."]
    to_review = [r for r in results if r["decision"] == "à relire" and r["unsupported_claims"]]
    if to_review:
        md += ["", "**À relire par un humain** — affirmations que le juge n'a pas trouvées dans les sources :"]
        for r in to_review:
            for claim in r["unsupported_claims"]:
                md.append(f"- *{esc(r['title'])}* : « {esc(claim)} »")
    return "\n".join(md)


def gri_with_data(key: str, sec_id: str) -> tuple[int, int]:
    """(publications rapportées ou partiellement rapportées, total) pour une section, d'après l'index GRI."""
    if not key or sec_id not in {s["id"] for s in gri_index.load_map()["sections"]}:
        return 0, 0
    codes = gri_index.section(sec_id)["disclosures"]
    return sum(gri_index.entry(key, c).status in ("reported", "partial") for c in codes), len(codes)


def index_cell(key: str, sec_id: str) -> str:
    n, total = gri_with_data(key, sec_id)
    return f"{n} sur {total}" if total else "—"


STRONG, WEAK = 0.75, 0.40          # point fort : 75 % des points ou plus ; à améliorer : moins de 40 %


def classify(ratio: float) -> str:
    return "fort" if ratio >= STRONG else ("faible" if ratio < WEAK else "partiel")


def strengths_md(key: str, sec_id: str) -> str:
    """Paragraphe « Points forts et points à améliorer », écrit par le code à partir de la table des faits."""
    f, labels = facts.load(key), markers.labels_fr()
    groups = {"fort": [], "partiel": [], "faible": []}
    for c in gri_index.section(sec_id)["credits"]:
        v = facts.credit_var(c)
        if f"{v}_score" not in f:
            continue
        score, mx = f[f"{v}_score"], f[f"{v}_max"]
        ratio = float(score["number"]) / float(mx["number"])
        name = labels.get(c, score["label"].split("— ", 1)[-1]).split(" (")[0]
        groups[classify(ratio)].append((ratio, f"{c} {name} ({score['display']} sur {mx['display']})"))
    if not any(groups.values()):
        return ""
    def items(g, reverse):
        return " ; ".join(t for _, t in sorted(groups[g], key=lambda x: x[0], reverse=reverse)) or "aucun"
    return "\n".join([
        "#### Points forts et points à améliorer", "",
        "*Calculé par le code à partir des scores STARS de la section, sans texte du modèle (point fort : 75 % "
        "des points ou plus ; à améliorer : moins de 40 % ; entre les deux : partiellement atteint).*", "",
        f"- **Points forts** : {items('fort', True)}.",
        f"- **Partiellement atteints** : {items('partiel', True)}.",
        f"- **À améliorer** : {items('faible', False)}."])


def section_indicators(key: str, sec_id: str) -> tuple[str, list[str]]:
    """Tableau des scores STARS des crédits d'une section, écrit par le code."""
    f, b = facts.load(key), facts.bands(key)
    codes = [c for c in gri_index.section(sec_id)["credits"] if facts.credit_var(c) + "_score" in f]
    if not codes:
        return "", []
    md = ["| Crédit STARS | Points obtenus | Niveau |", "|---|---:|---|"]
    used = []
    for c in codes:
        v = facts.credit_var(c)
        md.append(f"| {c} — {esc(f[v + '_score']['label'].split('— ', 1)[-1])} | "
                  f"{f[v + '_score']['display']} / {f[v + '_max']['display']} | {b.get(c, '')} |")
        used += [v + "_score", v + "_max"]
    md.append("")
    md.append("*Valeurs insérées par le code depuis la table des faits ; le texte ci-dessous est rédigé par le "
              "modèle puis validé.*")
    return "\n".join(md), used


def provenance(key: str, results: list[dict]) -> list[dict]:
    f = facts.load(key)
    rows = []
    synth = ["STARS_score", "STARS_date"] + [f"{p}_{s}" for p, _ in PILLAR_ORDER for s in ("points", "max", "pct")]
    for fid in synth:
        if fid in f:
            rows.append({"section": "Synthèse des résultats STARS", "fact_id": fid, "display": f[fid]["display"],
                         "raw_value": f[fid]["raw_value"], "label": f[fid]["label"], "source": f[fid]["source"]})
    for r in results:
        for fid in section_indicators(key, r["section"])[1]:
            rows.append({"section": f"{r['title']} (indicateurs)", "fact_id": fid, "display": f[fid]["display"],
                         "raw_value": f[fid]["raw_value"], "label": f[fid]["label"], "source": f[fid]["source"]})
    for r in results:
        for fid in review.apply(key, r["section"], r["text"])[1]:       # nombres cités par la relecture
            rows.append({"section": f"{r['title']} (relecture)", "fact_id": fid,
                         "display": f[fid]["display"], "raw_value": f[fid]["raw_value"],
                         "label": f[fid]["label"], "source": f[fid]["source"]})
    for r in results:
        for fid in r["used_facts"]:
            fact = f[fid]
            rows.append({"section": r["title"], "fact_id": fid, "display": fact["display"],
                         "raw_value": fact["raw_value"], "label": fact["label"], "source": fact["source"]})
    for e in gri_index.index(key):
        for fid in e.fact_ids:
            rows.append({"section": f"Index GRI {e.code}", "fact_id": fid, "display": f[fid]["display"],
                         "raw_value": f[fid]["raw_value"], "label": f[fid]["label"], "source": f[fid]["source"]})
    return rows


# ------------------------------------------------------------------ documents
def report_md(key: str, results: list[dict]) -> str:
    inst = INSTITUTIONS[key]
    today = dt.date.today().isoformat()
    parts = [f"# Rapport de durabilité — {inst['name']}",
             f"*Établi en référence aux normes GRI · généré le {today} · données AASHE STARS 3.0*", "",
             about(key), "", "## Synthèse des résultats STARS", "", stars_summary(key)]
    for r in results:
        parts += ["", f"## {r['title']}", ""]
        if r["decision"] == "à relire":
            parts.append('<p class="review">Section à relire : le juge automatique n\'a pas pu la valider entièrement '
                         '(voir l\'annexe « Validation du rapport »).</p>')
        if r["section"] == "enseignement":
            parts.append(f"> {gri_index.section('enseignement')['gap_note']}\n")
        table, _ = section_indicators(key, r["section"])
        if table:
            parts += [table, ""]
        for caution in gri_index.cautions(key, r["section"]):   # mise en garde garantie par le code
            parts += [f"> **Point de vigilance.** {caution}", ""]
        text, _, missing = review.apply(key, r["section"], r["text"])     # relecture humaine d'abord
        for c in missing:
            print(f"   ATTENTION relecture : passage introuvable dans {key}/{r['section']} "
                  f"(texte régénéré depuis ?) : « {c['avant'][:70]} »")
        parts.append(style.clean(names.normalize(key, guard.tidy(guard.drop_marker_echo(text), r["title"]))))
        strengths = strengths_md(key, r["section"])                  # écrit par le code : exact sans relecture
        if strengths:
            parts += ["", strengths]
    parts += ["", "## Index de contenu GRI", "", gri_index_md(key),
              "", "## Annexe — Correspondance STARS → GRI, TCFD, ESRS", "", frameworks_md(),
              "", "## Annexe — Validation du rapport", "", validation_md(results, key),
              "", "## Vérifier ce rapport", "",
              f"Chaque chiffre de ce rapport est listé dans `provenance.csv` avec le crédit STARS, le champ et l'URL "
              f"dont il provient. `pytest` recalcule ces chiffres à partir des fichiers bruts, indépendamment du code "
              f"qui les a produits, et vérifie qu'aucun nombre des sections narratives n'est absent de la table des faits."]
    return "\n".join(parts)


def comparison_md(comp: dict) -> str:
    keys = list(INSTITUTIONS)
    today = dt.date.today().isoformat()
    md = ["# Synthèse comparative — Berkeley, Cork et TU Dublin",
          f"*Généré le {today} · données AASHE STARS 3.0 · mêmes règles que les rapports individuels*", "",
          "| | " + " | ".join(INSTITUTIONS[k]["name"] for k in keys) + " |",
          "|---|" + "---:|" * len(keys)]
    md.append("| Note STARS | " + " | ".join(sources.header(k)["rating"] for k in keys) + " |")
    md.append("| Score global | " + " | ".join(facts.load(k)["STARS_score"]["display"] for k in keys) + " |")
    md.append("| Date de soumission | " + " | ".join(facts.load(k)["STARS_date"]["display"] for k in keys) + " |")
    for pid, label in PILLAR_ORDER:
        md.append(f"| {label} | " + " | ".join(facts.load(k)[f"{pid}_pct"]["display"] for k in keys) + " |")
    for status, label in gri_index.STATUS_LABELS.items():
        md.append(f"| Publications GRI — {label.lower()} | "
                  + " | ".join(str(gri_index.counts(gri_index.index(k))[status]) for k in keys) + " |")
    md += ["", bar_chart({label: [(INSTITUTIONS[k]["name"], float(facts.load(k)[f"{pid}_pct"]["number"]),
                                   facts.load(k)[f"{pid}_pct"]["display"]) for k in keys]
                          for pid, label in PILLAR_ORDER}),
           '<p class="legend"><span style="color:#2f6f5e">■</span> Berkeley &nbsp; '
           '<span style="color:#c07a2c">■</span> Cork &nbsp; <span style="color:#4a6fa5">■</span> TU Dublin</p>',
           "", "## Analyse", ""]
    if comp["decision"] == "à relire":
        md.append('<p class="review">Section à relire : validation automatique incomplète.</p>')
    md += [style.clean(names.normalize_all(guard.tidy(guard.drop_marker_echo(comp["text"]), comp["title"]))), "",
           "## Validation", "",
           validation_md([comp])]
    return "\n".join(md)


CSS = """
@page { size: A4; margin: 18mm 16mm; }
:root { --ink:#1d2a26; --muted:#5b6b66; --line:#d9e1de; --accent:#2f6f5e; --bg:#ffffff; }
body { font-family: "Segoe UI", Calibri, Arial, sans-serif; color: var(--ink); background: var(--bg);
       max-width: 860px; margin: 0 auto; padding: 24px 16px; line-height: 1.55; font-size: 10.5pt; }
h1 { color: var(--accent); font-size: 22pt; margin: 0 0 4px; line-height: 1.2; }
h1 + p em { color: var(--muted); }
h2 { color: var(--accent); border-bottom: 2px solid var(--accent); padding-bottom: 3px; margin-top: 30px;
     page-break-after: avoid; }
h3 { font-size: 12pt; margin: 18px 0 6px; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 9pt; page-break-inside: auto; }
th, td { border: 1px solid var(--line); padding: 5px 7px; vertical-align: top; text-align: left; }
th { background: #eef4f2; }
tr { page-break-inside: avoid; }
td:first-child { min-width: 120px; }
blockquote { border-left: 4px solid var(--accent); margin: 10px 0; padding: 4px 12px; background: #f4f8f6; }
.badge { display: inline-block; padding: 1px 7px; border-radius: 9px; font-size: 8.5pt; white-space: nowrap; }
.badge.ok { background: #dcefe6; color: #1e5c45; } .badge.part { background: #fbeccf; color: #7a4d06; }
.badge.no { background: #f1dede; color: #7c2323; } .badge.pend { background: #e3e8f3; color: #2d4573; }
.review { background: #fbeccf; border-left: 4px solid #c07a2c; padding: 6px 10px; font-size: 9.5pt; }
.chart { width: 100%; max-width: 680px; height: auto; margin: 8px 0; }
.chart .lbl { font-size: 11px; fill: #1d2a26; } .chart .val { font-size: 10px; fill: #1d2a26; }
.legend { font-size: 9pt; color: var(--muted); }
code { background: #f1f4f3; padding: 0 3px; border-radius: 3px; }
@media (max-width: 600px) { table { font-size: 8pt; } td:first-child { min-width: 0; } }
"""


def to_html(md_text: str, title: str) -> str:
    body = markdown.markdown(md_text, extensions=["tables", "sane_lists"])
    return (f"<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body>{body}</body></html>")


def browser() -> str | None:
    for p in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"]:
        if Path(p).exists():
            return p
    return shutil.which("msedge") or shutil.which("chrome")


def to_pdf(html_path: Path) -> Path | None:
    exe = browser()
    if not exe:
        return None
    pdf = html_path.resolve().with_suffix(".pdf")       # Edge ne partage pas notre dossier courant
    pdf.unlink(missing_ok=True)
    # Profil dédié : sinon une fenêtre Edge déjà ouverte intercepte la commande et rien n'est écrit.
    profile = PROCESSED / "edge_profile"
    subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--user-data-dir={profile}", f"--print-to-pdf={pdf}", html_path.resolve().as_uri()],
                   check=False, timeout=180, capture_output=True)
    # Le lanceur d'Edge rend la main tout de suite : attendre que le PDF soit écrit et stable.
    deadline, last = time.time() + 120, -1
    while time.time() < deadline:
        if pdf.exists():
            size = pdf.stat().st_size
            if size > 0 and size == last:
                return pdf
            last = size
        time.sleep(1)
    return pdf if pdf.exists() else None


def write(name: str, md_text: str, title: str, prov: list[dict] | None = None) -> dict:
    folder = OUTPUTS / name
    folder.mkdir(parents=True, exist_ok=True)
    stem = Path(name).name                              # « essai_sans_llm/cork » -> rapport_cork
    md_path = folder / f"rapport_{stem}.md"
    md_path.write_text(md_text, encoding="utf-8")
    html_path = folder / f"rapport_{stem}.html"
    html_path.write_text(to_html(md_text, title), encoding="utf-8")
    if prov is not None:
        with (folder / "provenance.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["section", "fact_id", "display", "raw_value", "label", "source"])
            w.writeheader()
            w.writerows(prov)
    docx_path = docx_export.convert(md_text, folder / f"rapport_{stem}.docx", title)
    pdf = to_pdf(html_path)
    return {"md": md_path, "html": html_path, "docx": docx_path, "pdf": pdf}
