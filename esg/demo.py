"""
Démonstration du garde-fou (instantanée, sans LLM) — pour la soutenance.

    python -m esg.demo

Montre, sur de vraies valeurs de Berkeley :
  1. un texte où le « LLM » écrit un chiffre lui-même -> rejeté ;
  2. la réparation : le code retire seulement les phrases fautives ;
  3. un texte correct à placeholders -> le CODE insère les vraies valeurs ;
  4. le contrôle final : chaque nombre du texte vient de facts.csv.
"""

import sys

from jinja2 import Environment, StrictUndefined

from esg import facts, guard


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
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

    print("\n3. Texte correct : le modèle écrit des placeholders")
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
    print("=" * 70)


if __name__ == "__main__":
    main()
