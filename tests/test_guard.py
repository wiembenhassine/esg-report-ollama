"""Le garde-fou doit rejeter tout nombre écrit par le LLM et laisser passer les références."""

from esg.guard import check_draft, check_rendered

ALLOWED = {"OP6_score", "OP6_max"}


def test_placeholders_and_references_pass():
    text = ("Selon GRI 305-1 et la publication 2-7, le crédit OP-6 obtient {{ OP6_score }} sur "
            "{{OP6_max}} points (champs d'application 1 et 2, Scope 3, tCO2e, STARS 3.0).")
    assert check_draft(text, ALLOWED) == []


def test_digits_are_rejected():
    assert check_draft("Les émissions étaient de 134 957 tCO2e.", ALLOWED)
    assert check_draft("Année de référence : 2019.", ALLOWED)
    assert check_draft("Une baisse de 9,83 %.", ALLOWED)


def test_number_words_are_rejected():
    assert check_draft("Trois membres siègent au conseil.", ALLOWED)
    assert check_draft("Près de la moitié du personnel.", ALLOWED)
    assert check_draft("Over two thousand students.", ALLOWED)


def test_third_party_is_not_a_number():
    assert check_draft("Aucune vérification par un tiers n'a été réalisée.", ALLOWED) == []


def test_unknown_placeholder_and_expressions_are_rejected():
    assert check_draft("Score {{ OP7_score }}.", ALLOWED)
    assert check_draft("Score {{ OP6_score * 2 }}.", ALLOWED)
    assert check_draft("Score {{ OP6_score | round }}.", ALLOWED)
    assert check_draft("Score {% if x %}élevé{% endif %}.", ALLOWED)


def test_malformed_placeholder_is_reported():
    problems = check_draft("Score {OP6_score} sur OP6_max.", ALLOWED)
    assert any("mal écrit" in p for p in problems)


def test_rendered_numbers_must_come_from_facts():
    assert check_rendered("obtient 8,01 sur 16", {"OP6_score": "8,01", "OP6_max": "16"}) == []
    assert check_rendered("obtient 8,01 sur 16 et 12 de plus", {"OP6_score": "8,01", "OP6_max": "16"})
    assert check_rendered("total 78 414,00 MWh (GRI 302-1)", {"x": "78 414,00 MWh"}) == []


def test_masked_number_marker_is_rejected():
    assert check_draft("Le campus couvre [n] acres.", ALLOWED)


def test_repair_only_removes_offending_sentences():
    from esg.guard import repair
    text = ("### Périmètre\n\nLe campus couvre [n] acres. Il comprend le site de Richmond (GRI 2-2). "
            "Trois membres siègent au conseil.\n\n### Limites et omissions\n\nCe rapport ne peut pas établir "
            "le siège (GRI 2-1). Le score est de {{ OP6_score }}.")
    fixed, removed = repair(text, ALLOWED)
    assert check_draft(fixed, ALLOWED) == []
    assert "Richmond" in fixed and "{{ OP6_score }}" in fixed and "ne peut pas établir" in fixed
    assert len(removed) == 2
    for word in fixed.split():                 # le code n'ajoute aucun mot
        assert word in text.split()
