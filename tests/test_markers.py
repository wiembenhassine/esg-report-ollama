"""
Marqueurs détournés : les 5 cas réels trouvés dans le rapport de Dublin (test du 4 octobre 2026),
réécrits avec les marqueurs complets. Chacun doit être rejeté par le garde-fou, et la réparation
doit retirer la phrase fautive sans toucher aux phrases correctes.
"""

import pytest
from jinja2 import Environment, StrictUndefined

from esg import generate, gri_index, guard

KEY = "tudublin"


def markers_of(sec_id: str) -> dict:
    sec = gri_index.section(sec_id)
    return generate.section_values(KEY, sec, [gri_index.entry(KEY, c) for c in sec["disclosures"]])


CASES = [  # (section, texte écrit par le modèle, motif attendu dans le rejet)
    ("parties_prenantes",
     "Dans l'année universitaire précédente, environ {{ EN5 }} étudiants ont participé à des activités communautaires.",
     "après « environ »"),
    ("strategie",
     "Le plan vise à réduire les émissions de l'ordre de {{ PA2 }} % d'ici {{ PA2 }}.",
     "d'ici"),
    ("social",
     "Les étudiants aidés doivent provenir de ménages dont le revenu combiné est inférieur à {{ PA9 }}.",
     "après « à »"),
    ("enseignement",
     "Parmi les projets listés sur cette page, {{ AC1 }} sont axés sur la durabilité.",
     "sans verbe de score"),
    ("gouvernance",
     "La part des points obtenus dans le pilier Gouvernance est évaluée à {{ GOV }} %.",
     "suivi de « %."),
]


@pytest.mark.parametrize("sec_id,text,why", CASES, ids=[c[0] for c in CASES])
def test_real_misused_markers_are_rejected(sec_id, text, why):
    mk = markers_of(sec_id)
    problems = guard.check_draft(text, set(mk), mk)
    assert problems, f"non détecté : {text}"
    assert any(why in p for p in problems), problems


@pytest.mark.parametrize("sec_id,text,why", CASES, ids=[c[0] for c in CASES])
def test_repair_removes_only_the_misused_sentence(sec_id, text, why):
    mk = markers_of(sec_id)
    good_marker = next(n for n, m in mk.items() if m["kind"] in ("credit", "pillar"))
    good = f"L'université obtient {{{{ {good_marker} }}}}."
    fixed, removed = guard.repair(f"{good} {text}", set(mk), mk)
    assert fixed == good and removed == [text]


def test_wrong_level_next_to_a_marker_is_rejected():
    mk = markers_of("gouvernance")                      # GOV de TU Dublin : 97,0 %, niveau élevé
    text = "Le pilier Gouvernance obtient {{ GOV }}, ce qui représente un niveau maximal."
    assert any("niveau « maximal » faux" in p for p in guard.check_draft(text, set(mk), mk))
    assert not guard.check_draft("Le pilier Gouvernance obtient {{ GOV }}, un niveau élevé.", set(mk), mk)


def test_code_like_identifier_is_rejected():
    mk = markers_of("gouvernance")
    assert any("identifiant technique" in p for p in guard.check_draft("(GOVPct)", set(mk), mk))


def test_complete_marker_renders_a_self_describing_sentence():
    mk = markers_of("parties_prenantes")
    draft = "Pour l'engagement civique, TU Dublin obtient {{ EN5 }}."
    assert guard.check_draft(draft, set(mk), mk) == []
    text = Environment(undefined=StrictUndefined).from_string(draft).render(EN5=mk["EN5"]["display"])
    assert text == ("Pour l'engagement civique, TU Dublin obtient 4,5 points STARS sur 8 au crédit EN-5, "
                    "niveau intermédiaire.")
    assert mk["EN5"]["fact_ids"] == ["EN5_score", "EN5_max"]


def test_repeated_full_marker_is_cleaned_in_the_rendered_text():
    """Cas réels du 5 octobre (27 phrases dans les 3 rapports) : le modèle répète le marqueur complet."""
    berkeley = ("L'université a également obtenu 2,5 points STARS sur 3 au crédit PA-12, niveau élevé points STARS "
                "sur 2,5 points STARS sur 3 au crédit PA-12, niveau élevé au crédit PA-12.")
    assert guard.drop_marker_echo(berkeley) == \
        "L'université a également obtenu 2,5 points STARS sur 3 au crédit PA-12, niveau élevé."
    cork = ("* Score STARS : 1 point STARS sur 1 au crédit IL-24, niveau maximal points STARS sur 1 point STARS "
            "sur 1 au crédit IL-24, niveau maximal au crédit IL-24, niveau maximal")
    assert guard.drop_marker_echo(cork) == "* Score STARS : 1 point STARS sur 1 au crédit IL-24, niveau maximal"
    dublin = ("comme le montre son score STARS de 4 points STARS sur 4 au crédit PA-3, niveau maximal points sur "
              "4 points STARS sur 4 au crédit PA-3, niveau maximal au crédit PA-3, niveau maximal. Ensuite.")
    assert guard.drop_marker_echo(dublin) == \
        "comme le montre son score STARS de 4 points STARS sur 4 au crédit PA-3, niveau maximal. Ensuite."
    overall = "Le rapport a obtenu un score STARS global de un score STARS global de 83,35."
    assert guard.drop_marker_echo(overall) == "Le rapport a obtenu un score STARS global de 83,35."
    # Deux crédits différents côte à côte : rien n'est retiré.
    two = ("obtient 4 points STARS sur 4 au crédit PA-3, niveau maximal et 3 points STARS sur 3 au crédit "
           "PA-6, niveau maximal.")
    assert guard.drop_marker_echo(two) == two


def test_empty_reference_lists_are_removed():
    assert guard.tidy("Les sociétés étudiantes (Ref, Ref) et le programme (Refs 2, 3) existent (Ref ).") == \
        "Les sociétés étudiantes et le programme existent."
