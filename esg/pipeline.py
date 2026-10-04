"""
Pipeline complet.

    python -m esg.pipeline                       # 3 universités + synthèse comparative
    python -m esg.pipeline cork                  # une université
    python -m esg.pipeline cork --sections gouvernance social
    python -m esg.pipeline --no-cache            # tout régénérer
    python -m esg.pipeline --render-only         # re-rendre depuis le cache, sans LLM

Étapes : faits -> index RAG -> sections (rédaction + validation) -> rendu MD/HTML/PDF.
Les sections validées sont mises en cache (outputs/cache) : une relance ne
recalcule que ce qui a changé. Sur CPU, compter quelques minutes par section.
"""

import argparse
import json
import sys
import time

from esg import dashboard, facts, generate, gri_index, rag, render
from esg.config import INSTITUTIONS, OUTPUTS


def section_ids() -> list[str]:
    return [s["id"] for s in gri_index.load_map()["sections"]]


def cached(key: str, sec_id: str) -> dict | None:
    p = OUTPUTS / "cache" / key / f"{sec_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("institutions", nargs="*", default=[], help=f"parmi {list(INSTITUTIONS)}")
    ap.add_argument("--sections", nargs="*", default=None)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--no-comparison", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="sans LLM : textes de repli, pour tester le rendu")
    args = ap.parse_args()
    unknown = [k for k in args.institutions if k not in INSTITUTIONS]
    if unknown:
        ap.error(f"université inconnue {unknown} ; choix : {list(INSTITUTIONS)}")
    keys = args.institutions or list(INSTITUTIONS)
    secs = args.sections or section_ids()

    facts.main()
    if not (args.render_only or args.dry_run):
        rag.get_index()

    t0 = time.time()
    for key in keys:
        print(f"\n== {INSTITUTIONS[key]['name']}")
        results = []
        for sec_id in section_ids():
            if args.dry_run:
                r = generate.dry_section(key, sec_id)
            elif args.render_only or sec_id not in secs:
                r = cached(key, sec_id)
                if r is None:
                    print(f"   [{key}/{sec_id}] absent du cache — section ignorée")
                    continue
            else:
                try:
                    r = generate.run_section(key, sec_id, use_cache=not args.no_cache)
                except Exception as e:                 # une section en échec n'arrête pas le rapport
                    print(f"   [{key}/{sec_id}] ERREUR {type(e).__name__}: {e} — texte de repli utilisé")
                    r = generate.dry_section(key, sec_id)
            results.append(r)
        # --dry-run écrit à part : il ne doit jamais écraser les vrais rapports.
        out = render.write(f"essai_sans_llm/{key}" if args.dry_run else key, render.report_md(key, results),
                           f"Rapport de durabilité — {INSTITUTIONS[key]['name']}",
                           render.provenance(key, results))
        print(f"   -> {out['md'].name}, {out['html'].name}, {out['pdf'].name if out['pdf'] else 'PDF non généré'}")

    if not args.no_comparison and not args.dry_run and len(keys) == len(INSTITUTIONS):
        print("\n== Synthèse comparative")
        comp_cache = OUTPUTS / "cache" / "comparatif.json"
        try:
            comp = (json.loads(comp_cache.read_text(encoding="utf-8"))
                    if args.render_only and comp_cache.exists()
                    else generate.run_comparison(use_cache=not args.no_cache))
        except Exception as e:
            print(f"   [comparatif] ERREUR {type(e).__name__}: {e} — texte de repli utilisé")
            comp = {"institution": "comparatif", "section": "comparatif", "title": "Synthèse comparative",
                    "decision": "repli", "text": "*Section de repli : voir le tableau comparatif ci-dessus.*",
                    "used_facts": [], "judge_score": None, "faithfulness": None, "gri_coverage": None,
                    "unsupported_claims": [], "attempts": 0, "guard_rejections": 0, "seconds": 0.0}
        out = render.write("comparatif", render.comparison_md(comp), "Synthèse comparative ESG")
        print(f"   -> {out['md'].name}, {out['pdf'].name if out['pdf'] else 'PDF non généré'}")

    dashboard.main()
    print(f"\nTerminé en {(time.time() - t0) / 60:.1f} min. Rapports dans {OUTPUTS}")


if __name__ == "__main__":
    main()
