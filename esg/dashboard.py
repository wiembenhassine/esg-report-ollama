"""
Tableau de bord BI (étape 6 « Output ») : une page HTML autonome, hors ligne,
générée par le code à partir de facts.csv, de l'index GRI et des résultats de
validation. Aucun LLM ici.

    python -m esg.dashboard   -> outputs/tableau_de_bord.html

Couleurs : palette catégorielle de référence (3 premiers emplacements, validés
toutes paires pour le daltonisme, clair et sombre) ; rampe ordinale bleue pour
la couverture GRI et la carte de chaleur. Chaque marque a une infobulle, les
valeurs sont étiquetées et une vue tableau accompagne chaque graphique.
"""

import html
import json
import sys

from esg import facts, gri_index, sources
from esg.config import INSTITUTIONS, OUTPUTS

PILLARS = [("ENV", "Environnement"), ("SOC", "Social"), ("GOV", "Gouvernance"),
           ("CTX", "Enseignement, recherche, engagement")]
SHORT = {"berkeley": "Berkeley", "cork": "Cork", "tudublin": "TU Dublin"}
STATUS_ORDER = ["reported", "partial", "pending", "none"]
HEAT_BINS = [(0.0, "h0"), (0.2, "h1"), (0.4, "h2"), (0.6, "h3"), (0.8, "h4"), (0.999, "h5")]

CSS = """
.viz-root { color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --grid:#e1e0d9;
  --axis:#c3c2b7; --ring:rgba(11,11,11,.10);
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a;
  --o600:#184f95; --o400:#3987e5; --o250:#86b6ef; --none:#e1e0d9;
  --h0:#f0efec; --h1:#cde2fb; --h2:#9ec5f4; --h3:#5598e7; --h4:#256abf; --h5:#104281;
  --h3t:#ffffff; --h4t:#ffffff; --h5t:#ffffff; --t-reported:#ffffff; --t-partial:#ffffff; --t-pending:#0b0b0b; --t-none:#0b0b0b;
  --ok:#006300; --warn:#8a5a00; --bad:#b42a2a; }
@media (prefers-color-scheme: dark) { :root:where(:not([data-theme="light"])) .viz-root { color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781; --grid:#2c2c2a;
  --axis:#383835; --ring:rgba(255,255,255,.10);
  --s1:#3987e5; --s2:#d95926; --s3:#199e70;
  --o600:#6da7ec; --o400:#3987e5; --o250:#1c5cab; --none:#383835;
  --h0:#383835; --h1:#104281; --h2:#1c5cab; --h3:#2a78d6; --h4:#5598e7; --h5:#9ec5f4;
  --h3t:#ffffff; --h4t:#0b0b0b; --h5t:#0b0b0b; --t-reported:#0b0b0b; --t-partial:#ffffff; --t-pending:#ffffff; --t-none:#ffffff;
  --ok:#0ca30c; --warn:#fab219; --bad:#e66767; } }
:root[data-theme="dark"] .viz-root { color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781; --grid:#2c2c2a;
  --axis:#383835; --ring:rgba(255,255,255,.10);
  --s1:#3987e5; --s2:#d95926; --s3:#199e70;
  --o600:#6da7ec; --o400:#3987e5; --o250:#1c5cab; --none:#383835;
  --h0:#383835; --h1:#104281; --h2:#1c5cab; --h3:#2a78d6; --h4:#5598e7; --h5:#9ec5f4;
  --h3t:#ffffff; --h4t:#0b0b0b; --h5t:#0b0b0b; --t-reported:#0b0b0b; --t-partial:#ffffff; --t-pending:#ffffff; --t-none:#ffffff;
  --ok:#0ca30c; --warn:#fab219; --bad:#e66767; }
* { box-sizing: border-box; }
body { margin:0; }
.viz-root { background:var(--page); color:var(--ink); min-height:100vh;
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; padding: 24px 16px 48px; }
.wrap { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 4px; } h2 { font-size: 16px; margin: 0 0 4px; }
.sub { color: var(--ink2); margin: 0 0 20px; }
.card { background:var(--surface); border:1px solid var(--ring); border-radius: 10px; padding: 16px; margin-bottom: 16px; }
.note { color: var(--ink2); font-size: 12.5px; margin: 0 0 12px; }
.tiles { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 16px; }
.tile .who { color: var(--ink2); font-size: 13px; display:flex; align-items:center; gap:8px; }
.tile .hero { font-size: 34px; font-weight: 650; line-height: 1.1; margin: 6px 0 2px; }
.tile .meta { color: var(--ink2); font-size: 12.5px; }
.dot { width:10px; height:10px; border-radius:50%; display:inline-block; flex: none; }
.legend { display:flex; flex-wrap:wrap; gap: 6px 16px; font-size: 12.5px; color: var(--ink2); margin: 6px 0 10px; }
.legend span { display:inline-flex; align-items:center; gap:6px; }
.sw { width:12px; height:12px; border-radius:3px; display:inline-block; }
svg text { fill: var(--ink2); font-size: 12px; } svg .val { fill: var(--ink); font-size: 11.5px; font-variant-numeric: tabular-nums; }
svg .gridline { stroke: var(--grid); stroke-width: 1; } svg .base { stroke: var(--axis); stroke-width: 1; }
svg [data-tip] { cursor: default; } svg [data-tip]:hover { opacity: .85; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 12.5px; }
th, td { padding: 5px 8px; border-bottom: 1px solid var(--grid); text-align: left; white-space: nowrap; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
details { margin-top: 8px; } summary { cursor: pointer; color: var(--ink2); font-size: 12.5px; }
.heat td.cell { text-align:center; font-variant-numeric: tabular-nums; min-width: 92px; border: 2px solid var(--surface); }
.h0{background:var(--h0)} .h1{background:var(--h1)} .h2{background:var(--h2)} .h3{background:var(--h3);color:var(--h3t)}
.h4{background:var(--h4);color:var(--h4t)} .h5{background:var(--h5);color:var(--h5t)} .na{background:transparent;color:var(--muted)}
.dec { font-weight: 600; } .dec.ok { color: var(--ok); } .dec.part { color: var(--warn); } .dec.no { color: var(--bad); }
#tip { position: fixed; pointer-events: none; background: var(--surface); color: var(--ink); border: 1px solid var(--ring);
  box-shadow: 0 4px 14px rgba(0,0,0,.15); border-radius: 8px; padding: 6px 9px; font-size: 12.5px; max-width: 280px;
  opacity: 0; transition: opacity .08s; z-index: 10; }
@media (forced-colors: active) { .sw, .dot, rect { forced-color-adjust: none; } }
"""

JS = """
const tip = document.getElementById('tip');
document.querySelectorAll('[data-tip]').forEach(el => {
  el.addEventListener('mousemove', e => {
    tip.innerHTML = el.getAttribute('data-tip'); tip.style.opacity = 1;
    const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
    tip.style.left = x + 'px'; tip.style.top = (e.clientY + 14) + 'px';
  });
  el.addEventListener('mouseleave', () => tip.style.opacity = 0);
});
"""


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def tiles() -> str:
    out = []
    for i, key in enumerate(INSTITUTIONS, 1):
        f, head = facts.load(key), sources.header(key)
        out.append(f'<div class="card tile"><div class="who"><span class="dot" style="background:var(--s{i})"></span>'
                   f'{esc(INSTITUTIONS[key]["name"])}</div><div class="hero">{f["STARS_score"]["display"]}</div>'
                   f'<div class="meta">Score STARS global · note <b>{esc(head["rating"])}</b> · '
                   f'soumis le {f["STARS_date"]["display"]}</div></div>')
    return '<div class="tiles">' + "".join(out) + "</div>"


def legend_inst() -> str:
    return '<div class="legend">' + "".join(
        f'<span><i class="sw" style="background:var(--s{i})"></i>{SHORT[k]}</span>'
        for i, k in enumerate(INSTITUTIONS, 1)) + "</div>"


def pillar_chart() -> str:
    """Barres horizontales groupées : part des points obtenus par pilier (axe unique 0–100 %)."""
    keys = list(INSTITUTIONS)
    left, width, bar, gap_in, gap_grp = 240, 900, 14, 2, 18
    plot_w = width - left - 60
    grp_h = len(keys) * (bar + gap_in) - gap_in
    height = 24 + len(PILLARS) * (grp_h + gap_grp)
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
             f'aria-label="Part des points STARS obtenus par pilier et par université">']
    for t in range(0, 101, 25):
        x = left + plot_w * t / 100
        parts.append(f'<line class="gridline" x1="{x}" x2="{x}" y1="0" y2="{height - 20}"/>'
                     f'<text x="{x}" y="{height - 4}" text-anchor="middle">{t} %</text>')
    y = 4
    for pid, label in PILLARS:
        parts.append(f'<text x="0" y="{y + grp_h / 2 + 4}" style="fill:var(--ink)">{esc(label)}</text>')
        for i, key in enumerate(keys, 1):
            r = facts.load(key)[f"{pid}_pct"]
            pts, mx = facts.load(key)[f"{pid}_points"]["display"], facts.load(key)[f"{pid}_max"]["display"]
            w = plot_w * float(r["number"]) / 100
            tip = f"<b>{esc(SHORT[key])}</b> — {esc(label)}<br>{r['display']} des points ({pts} / {mx})"
            parts.append(f'<path data-tip="{esc(tip)}" fill="var(--s{i})" d="M{left},{y} h{w - 4:.1f} '
                         f'a4,4 0 0 1 4,4 v{bar - 8} a4,4 0 0 1 -4,4 h-{w - 4:.1f} z"/>'
                         f'<text class="val" x="{left + w + 6:.1f}" y="{y + bar - 3}">{r["display"]}</text>')
            y += bar + gap_in
        y += gap_grp - gap_in
    parts.append(f'<line class="base" x1="{left}" x2="{left}" y1="0" y2="{height - 20}"/></svg>')
    return "".join(parts)


def pillar_table() -> str:
    rows = "".join(f"<tr><td>{esc(label)}</td>" + "".join(
        f'<td class="num">{facts.load(k)[f"{pid}_points"]["display"]} / {facts.load(k)[f"{pid}_max"]["display"]}'
        f' · {facts.load(k)[f"{pid}_pct"]["display"]}</td>' for k in INSTITUTIONS) + "</tr>" for pid, label in PILLARS)
    head = "".join(f'<th class="num">{SHORT[k]}</th>' for k in INSTITUTIONS)
    return f"<details><summary>Voir les données en tableau</summary><div class='scroll'><table><tr><th>Pilier</th>{head}</tr>{rows}</table></div></details>"


def gri_chart() -> str:
    """Barres empilées à 100 % : statut des 78 publications GRI par université."""
    labels = gri_index.STATUS_LABELS
    color = {"reported": "var(--o600)", "partial": "var(--o400)", "pending": "var(--o250)", "none": "var(--none)"}
    left, width, bar = 120, 900, 26
    plot_w = width - left - 20
    height = len(INSTITUTIONS) * (bar + 14) + 6
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Statut des publications GRI">']
    y = 4
    for key in INSTITUTIONS:
        c = gri_index.counts(gri_index.index(key))
        total = sum(c.values())
        parts.append(f'<text x="0" y="{y + bar / 2 + 4}" style="fill:var(--ink)">{SHORT[key]}</text>')
        x = left
        for st in STATUS_ORDER:
            if not c[st]:
                continue
            w = plot_w * c[st] / total
            tip = f"<b>{SHORT[key]}</b> — {esc(labels[st])}<br>{c[st]} publication(s) sur {total}"
            parts.append(f'<rect data-tip="{esc(tip)}" x="{x:.1f}" y="{y}" width="{max(w - 2, 1):.1f}" height="{bar}" '
                         f'rx="3" fill="{color[st]}"/>')
            if w > 34:
                ink = f"var(--t-{st})"
                parts.append(f'<text x="{x + w / 2:.1f}" y="{y + bar / 2 + 4}" text-anchor="middle" '
                             f'style="fill:{ink};font-size:12px">{c[st]}</text>')
            x += w
        y += bar + 14
    parts.append("</svg>")
    leg = '<div class="legend">' + "".join(
        f'<span><i class="sw" style="background:{color[s]}"></i>{esc(labels[s])}</span>' for s in STATUS_ORDER) + "</div>"
    return leg + "".join(parts)


def heatmap() -> str:
    """Carte de chaleur : part des points obtenus par crédit noté (hors bonus IL)."""
    keys = list(INSTITUTIONS)
    rows_by_code = {}
    for key in keys:
        for fid, r in facts.load(key).items():
            if r["kind"] == "score" and not r["credit_code"].startswith("IL"):
                rows_by_code.setdefault(r["credit_code"], r["label"].split("— ", 1)[-1])
    order = {"OP": 0, "PA": 1, "AC": 2, "EN": 3}
    codes = sorted(rows_by_code, key=lambda c: (order.get(c[:2], 9), int(c.split("-")[1])))
    head = "".join(f'<th class="num">{SHORT[k]}</th>' for k in keys)
    body = []
    for code in codes:
        cells = []
        for key in keys:
            f, v = facts.load(key), facts.credit_var(code)
            if f"{v}_score" not in f:
                cells.append('<td class="cell na" data-tip="Non applicable ou non noté">n/a</td>')
                continue
            s, m = float(f[f"{v}_score"]["number"]), float(f[f"{v}_max"]["number"])
            ratio = s / m if m else 0
            cls = [c for lim, c in HEAT_BINS if ratio >= lim][-1]
            tip = (f"<b>{esc(code)}</b> {esc(rows_by_code[code])}<br>{SHORT[key]} : "
                   f"{f[f'{v}_score']['display']} / {f[f'{v}_max']['display']} points ({ratio:.0%})")
            cells.append(f'<td class="cell {cls}" data-tip="{esc(tip)}">{f[f"{v}_score"]["display"]} / '
                         f'{f[f"{v}_max"]["display"]}</td>')
        body.append(f"<tr><td><b>{esc(code)}</b> {esc(rows_by_code[code])}</td>{''.join(cells)}</tr>")
    leg = ('<div class="legend"><span>Part des points obtenus :</span>'
           + "".join(f'<span><i class="sw {c}"></i>{lab}</span>' for c, lab in
                     [("h0", "0–19 %"), ("h1", "20–39 %"), ("h2", "40–59 %"), ("h3", "60–79 %"),
                      ("h4", "80–99 %"), ("h5", "100 %")]) + "</div>")
    return leg + f'<div class="scroll"><table class="heat"><tr><th>Crédit STARS</th>{head}</tr>{"".join(body)}</table></div>'


def validation_table() -> str:
    cls = {"validée": "ok", "à relire": "part", "repli": "no"}
    icon = {"validée": "✓", "à relire": "!", "repli": "✕"}
    secs = [s for s in gri_index.load_map()["sections"]]
    head = "".join(f"<th>{SHORT[k]}</th>" for k in INSTITUTIONS)
    rows, done = [], 0
    for s in secs:
        cells = []
        for key in INSTITUTIONS:
            p = OUTPUTS / "cache" / key / f"{s['id']}.json"
            if not p.exists():
                cells.append('<td style="color:var(--muted)">en attente</td>')
                continue
            r = json.loads(p.read_text(encoding="utf-8"))
            done += 1
            detail = (f" · juge {r['judge_score']}/5 · fidélité {r['faithfulness']:.0%}"
                      if r.get("judge_score") else "")
            cells.append(f'<td><span class="dec {cls[r["decision"]]}">{icon[r["decision"]]} {r["decision"]}</span>'
                         f'<span style="color:var(--ink2)">{detail}</span></td>')
        rows.append(f"<tr><td>{esc(s['title'])}</td>{''.join(cells)}</tr>")
    total = len(secs) * len(INSTITUTIONS)
    return (f'<p class="note">{done} section(s) traitée(s) sur {total}. ✓ validée par le juge · '
            f'! à relire par un humain · ✕ texte de repli écrit par le code.</p>'
            f'<div class="scroll"><table><tr><th>Section</th>{head}</tr>{"".join(rows)}</table></div>')


def build() -> str:
    has_fields = any(r["kind"] == "field" for k in INSTITUTIONS for r in facts.load(k).values())
    scope = ("valeurs détaillées STARS extraites" if has_fields else
             "scores publics par crédit ; valeurs détaillées (MWh, tCO2e…) non extraites")
    body = f"""<div class="viz-root"><div class="wrap">
<h1>Tableau de bord ESG — universités STARS</h1>
<p class="sub">Données AASHE STARS 3.0 ({scope}) · correspondance GRI écrite à la main · chiffres insérés par le code.</p>
{tiles()}
<div class="card"><h2>Part des points STARS obtenus, par pilier</h2>
<p class="note">Regroupement des crédits notés en piliers propre au projet (pas une désignation STARS) ; bonus IL exclus.
Scores autodéclarés, notés par rapport à un groupe de pairs. Périmètres différents : Cork exclut ses filiales ;
TU Dublin n'a pas de crédits d'investissement (PA-4, PA-5 non applicables).</p>
{legend_inst()}{pillar_chart()}{pillar_table()}</div>
<div class="card"><h2>Couverture des 78 publications GRI</h2>
<p class="note">Statuts calculés par le code. « Non évalué » : un champ STARS existe mais sa valeur n'a pas été extraite
(accès AASHE authentifié requis).</p>{gri_chart()}</div>
<div class="card"><h2>Résultats par crédit STARS</h2>
<p class="note">Points obtenus / points possibles. Survolez une cellule pour le détail.</p>{heatmap()}</div>
<div class="card"><h2>Validation des sections rédigées par Ollama</h2>{validation_table()}</div>
</div><div id="tip" role="tooltip"></div></div>"""
    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>Tableau de bord ESG</title><style>{CSS}</style></head><body>{body}<script>{JS}</script></body></html>')


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    out = OUTPUTS / "tableau_de_bord.html"
    out.write_text(build(), encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
