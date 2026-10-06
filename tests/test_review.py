"""
Relecture humaine (relecture/<univ>.yaml) et nettoyages de forme du 6 octobre :
phrase qui annonce une liste absente, phrase presque identique répétée.
"""

import json

import pytest

from esg import guard, review
from esg.config import INSTITUTIONS, OUTPUTS


def cached(key: str, section: str) -> str:
    return json.loads((OUTPUTS / "cache" / key / f"{section}.json").read_text(encoding="utf-8"))["text"]


def corrected(key: str, section: str) -> str:
    text, _, _ = review.apply(key, section, cached(key, section))
    return guard.tidy(guard.drop_marker_echo(text))


@pytest.mark.parametrize("key", list(INSTITUTIONS))
def test_every_correction_matches_the_validated_text(key):
    for section, items in review.load(key).items():
        text = cached(key, section)
        for c in items:
            assert c["avant"] in text, f"{key}/{section} : « {c['avant'][:60]} » introuvable"
        assert review.apply(key, section, text)[2] == []


def test_corrections_never_type_a_number(tmp_path, monkeypatch):
    (tmp_path / "tudublin.yaml").write_text(
        'strategie:\n  - {avant: "x", apres: "neutre en 2050", raison: "r", source: "s"}\n', encoding="utf-8")
    monkeypatch.setattr(review, "FOLDER", tmp_path)
    review.load.cache_clear()
    try:
        with pytest.raises(review.ReviewError, match="chiffre tapé à la main"):
            review.load("tudublin")
    finally:
        review.load.cache_clear()


def test_numbers_of_the_review_come_from_facts():
    text, used, _ = review.apply("tudublin", "strategie", cached("tudublin", "strategie"))
    assert {"PA2_t0_7", "PA2_t0_8", "PA2_t0_9"} <= set(used)
    assert "neutralité climatique au plus tard en 2050" in text and "neutre en carbone d'ici 2030" not in text
    # Aucun nombre nouveau : chaque nombre du texte corrigé figure dans le texte validé ou dans un fait cité.
    from esg import facts
    f = facts.load("tudublin")
    allowed = set(guard.numbers_in(cached("tudublin", "strategie")))
    for fid in used:
        allowed |= set(guard.numbers_in(f[fid]["display"]))
    assert set(guard.numbers_in(text)) <= allowed


def test_dublin_errors_are_gone_from_the_corrected_report():
    wrong = {"materialite": "Plan de l'égalité des sexes", "environnement": "système de gestion environnementale",
             "enseignement": "véhicules électriques", "social": "(GRI 403-6)",
             "parties_prenantes": "n'a pas rendu publics", "organisation": "global de un score STARS"}
    for section, passage in wrong.items():
        assert passage in cached("tudublin", section)
        assert passage not in corrected("tudublin", section)
    gov = corrected("tudublin", "gouvernance")
    assert cached("tudublin", "gouvernance").count("Technological Universities Act") == 2
    assert gov.count("Technological Universities Act") == 1              # la phrase répétée est retirée
    assert "étaient :" not in gov


def test_orphan_colon_is_removed_but_a_real_list_is_kept():
    text = ("Le corps compte des membres non académiques. En février, les membres étaient :\n\n"
            "L'université a aussi des comités.\n\nLes initiatives sont, par exemple :\n\n* une formation ;")
    out = guard.drop_orphan_colons(text)
    assert "étaient" not in out and "Le corps compte des membres non académiques." in out
    assert "par exemple :" in out
    assert guard.tidy("Voici la section rédigée :\n\n**Énergie**\n\nLe campus achète de l'électricité.") == \
        "**Énergie**\n\nLe campus achète de l'électricité."


def test_near_repeat_is_removed_but_different_credits_are_kept():
    text = ("La gouvernance est assurée par le Technological Universities Act 2018, qui impose la représentation "
            "des étudiants dans les organes de gouvernance. Le Technological Universities Act 2018 impose "
            "également la représentation des étudiants dans les organes de gouvernance.")
    assert guard.drop_repeats(text).count("Act 2018") == 1
    credits = ("L'université obtient 3 points STARS sur 3 au crédit PA-11, niveau maximal. "
               "L'université obtient 3 points STARS sur 3 au crédit PA-6, niveau maximal.")
    assert guard.drop_repeats(credits) == credits
    years = "Le plan vise la neutralité d'ici 2030 pour le campus. Le plan vise la neutralité d'ici 2050 pour le campus."
    assert guard.drop_repeats(years) == years
