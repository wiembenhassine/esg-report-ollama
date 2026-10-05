"""
Correction 2 : années et pourcentages cités dans les textes STARS.

Le code les extrait comme faits (avec leur source), les remplace par des marqueurs dans le
contexte du modèle, et refuse les phrases restées vides (« d'ici . », « de MWh »).
Cas réel : la ligne du plan stratégique de TU Dublin (PA-2) qui donnait « d'ici et … d'ici. ».
"""

from jinja2 import Environment, StrictUndefined

from esg import facts, guard, markers, sources

LINE_IDX = next(i for i, l in enumerate(sources.credits("tudublin")["PA-2"]["lines"]) if "2028" in l)
LINE = sources.credits("tudublin")["PA-2"]["lines"][LINE_IDX]


def fid(k: int) -> str:
    return sources.text_fact_id("PA-2", LINE_IDX, k)


def test_years_and_percentages_become_facts_with_their_source():
    f = facts.load("tudublin")
    nums = sources.text_numbers(LINE)
    assert [n["raw"] for n in nums[:5]] == ["2024", "2028", "46.5%", "2028", "45%"]
    assert f[fid(1)]["display"] == "2028" and f[fid(2)]["display"] == "46,5 %"
    assert f[fid(1)]["kind"] == "text"
    assert f"texte STARS du crédit PA-2, ligne {LINE_IDX + 1}" in f[fid(1)]["source"]
    assert not any(ch.isdigit() for ch in f[fid(1)]["label"].split("(PA-2)")[1])   # le modèle ne voit aucun chiffre


def test_context_line_has_markers_and_no_other_number():
    items, judge_lines, text_markers = markers.evidence_markers(
        "tudublin", [{"inst": "tudublin", "credit": "PA-2", "line": LINE_IDX}], max_chars=2000)
    marked = items[0]["text"]
    assert f"{{{{ {fid(3)} }}}}" in marked and "(Ref" not in marked
    assert not any(ch.isdigit() for ch in guard.PLACEHOLDER.sub(" ", marked))
    assert fid(3) in text_markers and "2028" in judge_lines[0]        # le juge lit les vrais nombres


def test_year_marker_must_be_used_as_a_date():
    mk = {fid(3): markers.text("tudublin", fid(3)), fid(2): markers.text("tudublin", fid(2))}
    ok = f"Le plan vise une réduction de {{{{ {fid(2)} }}}} des émissions d'ici {{{{ {fid(3)} }}}}."
    assert guard.check_draft(ok, set(mk), mk) == []
    bad_year = f"TU Dublin obtient {{{{ {fid(3)} }}}} points."
    assert any("ANNÉE" in p for p in guard.check_draft(bad_year, set(mk), mk))
    bad_pct = f"Une réduction de {{{{ {fid(2)} }}}} %."
    assert any("signe %" in p for p in guard.check_draft(bad_pct, set(mk), mk))
    text = Environment(undefined=StrictUndefined).from_string(ok).render(
        **{n: m["display"] for n, m in mk.items()})
    assert text == "Le plan vise une réduction de 46,5 % des émissions d'ici 2028."
    assert guard.check_rendered(text, {n: m["display"] for n, m in mk.items()}) == []


def test_emptied_sentences_are_removed():
    text = ("Le plan vise la neutralité climatique d'ici et une baisse des émissions d'ici. "
            "Les panneaux produisent de MWh par an. "
            "Le campus récupère l'eau de pluie (GRI 303-1).")
    fixed, removed = guard.repair(text, set(), {})
    assert fixed == "Le campus récupère l'eau de pluie (GRI 303-1)."
    assert len(removed) == 2


def test_tidy_removes_empty_reference_marks():
    assert guard.tidy("Les projets financés (Ref ) comprennent SATLE (Refs 2, 3).") == \
        "Les projets financés comprennent SATLE."


def test_four_digit_numbers_are_not_split():
    assert guard.numbers_in("d'ici 2028, soit 46,5 % ; 78 414,00 MWh") == ["2028", "46,5", "78 414,00"]
