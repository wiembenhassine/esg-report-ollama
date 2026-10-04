"""
Démonstrations pour la soutenance.

    python -m esg.demo          # garde-fou : instantané, sans LLM
    python -m esg.demo --juge   # + test du juge Ollama sur un texte volontairement faux (quelques minutes)

Garde-fou, sur de vraies valeurs de Berkeley :
  1. un texte où le « LLM » écrit un chiffre lui-même -> rejeté ;
  2. la réparation : le code retire seulement les phrases fautives ;
  3. un texte correct à marqueurs -> le CODE insère les vraies valeurs ;
  4. le contrôle final : chaque nombre du texte vient de facts.csv ;
  5. un marqueur qui n'appartient pas au pilier en cours -> rejeté.
Juge (--juge), sur la section environnement de Cork :
  6. un texte avec un score inventé -> rejeté par le garde-fou avant même le juge ;
  7. un texte sans chiffre mais avec un niveau faux et des affirmations inventées -> rejeté par le juge.
"""

import sys

from jinja2 import Environment, StrictUndefined

from esg import facts, generate, gri_index, guard, judge, rag


def section_allowed(key: str, sec_id: str) -> dict:
    sec = gri_index.section(sec_id)
    entries = [gri_index.entry(key, c) for c in sec["disclosures"]]
    return generate.section_values(key, sec, entries)


def guard_demo() -> None:
    f = facts.load("berkeley")
    allowed = {"OP6_score", "OP6_max", "ENV_pct"}

    print("=" * 70)
    print("1. Le modèle écrit lui-même un chiffre")
    bad = ("Berkeley a obtenu 12 points sur 16 pour ses émissions (GRI 305-1). "
           "Le campus compte trois centrales.")
    print("   Texte   :", bad)
    for p in guard.check_draft(bad, allowed):
        print("   REJET   :", p)

    print("\n2. Réparation par le code (suppression uniquement)")
    mixed = ("Le crédit OP-6 couvre les émissions de GES (GRI 305-1). "
             "Berkeley a émis 134 957 tonnes en 2023. "
             "Le niveau obtenu est intermédiaire.")
    fixed, removed = guard.repair(mixed, allowed)
    print("   Avant   :", mixed)
    print("   Retiré  :", removed)
    print("   Après   :", fixed)

    print("\n3. Texte correct : le modèle écrit des marqueurs")
    good = ("Pour le crédit OP-6, Berkeley obtient {{ OP6_score }} points sur {{ OP6_max }} (GRI 305-1). "
            "Le pilier Environnement atteint {{ ENV_pct }} des points possibles.")
    print("   Écrit par le modèle :", good)
    print("   Garde-fou           :", guard.check_draft(good, allowed) or "aucun problème")
    used = {n: f[n]["display"] for n in guard.PLACEHOLDER.findall(good)}
    final = Environment(undefined=StrictUndefined).from_string(good).render(**used)
    print("   Inséré par le code  :", final)

    print("\n4. Contrôle final de traçabilité")
    print("   Nombres trouvés     :", guard.numbers_in(final))
    print("   Non traçables       :", guard.check_rendered(final, used) or "aucun")
    for n in used:
        print(f"   {n:<10} = {f[n]['display']:<10} source : {f[n]['source']}")

    print("\n5. Marqueur d'un autre pilier, dans la section Environnement")
    env = section_allowed("berkeley", "environnement")
    wrong = "Le salaire décent atteint {{ PA13_score }} (GRI 202-1)."
    print("   Marqueurs autorisés :", ", ".join(sorted(env)))
    print("   Texte               :", wrong)
    for p in guard.check_draft(wrong, set(env)):
        print("   REJET               :", p)
    print("=" * 70)


def judge_demo() -> None:
    key, sec_id = "cork", "environnement"
    sec = gri_index.section(sec_id)
    entries = [gri_index.entry(key, c) for c in sec["disclosures"]]
    values = generate.section_values(key, sec, entries)
    f = facts.load(key)
    print("\n" + "=" * 70)
    print(f"6. Score inventé (vrai score OP-6 de Cork : {f['OP6_score']['display']} / {f['OP6_max']['display']})")
    invented = "Cork obtient 15 points sur 16 pour ses émissions de gaz à effet de serre (GRI 305-1)."
    print("   Texte   :", invented)
    for p in guard.check_draft(invented, set(values)):
        print("   REJET   :", p)

    print("\n7. Texte sans chiffre mais faux, soumis au juge Ollama")
    false_text = (
        "### Performance environnementale\n\n"
        "Cork obtient {{ OP6_score }} points sur {{ OP6_max }} pour ses émissions, soit le niveau maximal "
        "(GRI 305-1). L'université a déjà atteint la neutralité carbone et toute son électricité provient de "
        "panneaux solaires installés sur le campus (GRI 302-1). Elle a aussi supprimé tous ses déchets mis en "
        "décharge grâce à un programme zéro déchet certifié par l'AASHE (GRI 306-5).")
    used = {n: values[n]["display"] for n in guard.PLACEHOLDER.findall(false_text)}
    rendered = Environment(undefined=StrictUndefined).from_string(false_text).render(**used)
    print("   Garde-fou :", guard.check_draft(false_text, set(values)) or "aucun chiffre écrit par le modèle")
    print("   Texte soumis au juge :\n     " + rendered.replace("\n", "\n     "))
    evidence = rag.get_index().evidence(key, sec["credits"], sec["topic"])
    print("   … le juge Ollama relit (une à trois minutes sur CPU)")
    v = judge.judge(rendered,
                    [f"{r['label']}: {r['display']}{generate.judge_level(r)}" for r in values.values()],
                    [f"GRI {e.code}: {e.status_label}" for e in entries],
                    gri_index.cautions(key, sec_id),
                    [f"[{p['credit']}] {p['text']}" for p in evidence])
    print(f"   Note du juge : {v['score']}/5 | fidélité : {v['faithfulness']:.0%} | "
          f"décision : {'ACCEPTÉ' if v['accepted'] else 'REJETÉ'} ({v['seconds']:.0f} s)")
    for c in v.get("claims", []):
        print(f"     [{'supportée' if c['supported'] else 'NON supportée'}] {c['claim']}")
    for x in v.get("rule_violations", []):
        print("     violation :", x)
    if v.get("feedback"):
        print("   Consigne de correction :", v["feedback"])
    print("=" * 70)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    guard_demo()
    if "--juge" in sys.argv:
        judge_demo()


if __name__ == "__main__":
    main()
