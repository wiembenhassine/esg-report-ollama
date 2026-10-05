"""Cohérence de la table de correspondance STARS -> GRI écrite à la main."""

import csv

from esg import gri_index
from esg.config import INSTITUTIONS, RAW

MAP = gri_index.load_map()
KNOWN_CREDITS = {r["credit_code"] for r in csv.DictReader(open(RAW / "scores" / "combined_esg_dataset.csv",
                                                                encoding="utf-8"))}


def test_86_disclosures_in_14_standards():
    """78 publications du rapport de référence + 8 de GRI 101: Biodiversité 2024."""
    codes = list(MAP["disclosures"])
    assert len(codes) == 86
    assert {gri_index.standard_of(c) for c in codes} == set(MAP["standards"])
    assert len(MAP["standards"]) == 14 and "GRI 101" in MAP["standards"] and "GRI 304" not in MAP["standards"]


def test_each_disclosure_in_exactly_one_section():
    placed = [d for s in MAP["sections"] for d in s["disclosures"]]
    assert sorted(placed) == sorted(MAP["disclosures"])


def test_credits_exist_in_stars_data():
    for code, spec in MAP["disclosures"].items():
        for c in spec.get("credits", []):
            assert c in KNOWN_CREDITS, f"{code} cite un crédit inconnu {c}"
    for s in MAP["sections"]:
        for c in s["credits"]:
            assert c in KNOWN_CREDITS, f"section {s['id']} cite un crédit inconnu {c}"


def test_coverage_values():
    for code, spec in MAP["disclosures"].items():
        assert spec.get("coverage", "none") in {"reported", "partial", "none"}, code
        if spec.get("coverage", "none") != "none":
            assert spec.get("credits"), f"{code} couvert sans crédit"


def test_status_never_reported_without_extracted_values():
    """Sans valeur extraite, une publication ne peut pas être « Rapporté »."""
    for key in INSTITUTIONS:
        for e in gri_index.index(key):
            if e.status == "reported":
                assert e.fact_ids, f"{key} {e.code} rapporté sans valeur"


def test_materiality_note_does_not_blame_institution():
    note = MAP["disclosures"]["3-1"]["note"]
    assert "ne peut pas établir" in note


def test_lint_blocks_style_but_only_notes_missing_citations():
    from esg.judge import lint
    text = "Le périmètre couvre le campus principal et les sites rattachés. " * 25
    blocking, notes, coverage = lint(text, ["2-1", "2-2"])
    assert blocking == [] and coverage == 0 and notes
    blocking, _, _ = lint("The campus is in the city and it has the buildings. " * 25, ["2-1"])
    assert blocking
    blocking, _, _ = lint("Ce rapport est conforme aux normes GRI pour la gouvernance. " * 20, ["2-1"])
    assert blocking


def test_judge_false_compliance_violation_is_discarded(monkeypatch):
    from esg import judge, llm
    fake = {"claims": [{"claim": "Le périmètre couvre le campus", "supported": True}],
            "rule_violations": ["The report claims compliance with GRI"], "score": 2, "feedback": "x"}
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"json": dict(fake), "seconds": 0})
    v = judge.judge("Le périmètre couvre le campus principal (GRI 2-2).", [], [], [], [])
    assert v["accepted"] and v["discarded_violations"] and not v["rule_violations"]
    v = judge.judge("Ce rapport est conforme aux normes GRI (GRI 2-2).", [], [], [], [])
    assert not v["accepted"]


def test_cautions_are_rendered_by_code():
    from esg import render
    result = {"section": "gouvernance", "title": "Gouvernance", "decision": "validée", "text": "Texte.",
              "used_facts": [], "judge_score": 4, "faithfulness": 1.0, "gri_coverage": 1.0,
              "unsupported_claims": [], "attempts": 1, "guard_rejections": 0, "seconds": 1.0}
    md = render.report_md("tudublin", [result])
    assert "Point de vigilance" in md and "PA-4" in md


def test_required_wording_mention_alone_does_not_discard_a_violation(monkeypatch):
    from esg import judge, llm
    fake = {"claims": [{"claim": "TU Dublin a déclaré une vérification externe", "supported": False}],
            "rule_violations": ["L'université a déclaré une vérification externe, mais ce rapport ne peut pas "
                                "établir les détails de cette vérification."], "score": 2, "feedback": "x"}
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"json": dict(fake), "seconds": 0})
    v = judge.judge("L'université a déclaré une vérification externe (GRI 2-5).", [], [], [], [])
    assert v["rule_violations"] and not v["discarded_violations"] and not v["accepted"]


def test_sections_without_disclosures_must_not_cite_gri():
    from esg.judge import lint
    text = "Les écarts entre établissements reflètent aussi des périmètres différents. " * 15
    assert lint(text, [])[0] == []
    assert lint(text + " Voir (GRI 305-1).", [])[0]



def test_biodiversity_gri_101_and_esrs_e4():
    from esg import frameworks
    disc = MAP["disclosures"]
    assert disc["101-4"]["credits"] == ["IL-24"] and disc["101-5"]["credits"] == ["IL-24"]
    assert disc["101-2"]["credits"] == ["OP-4"]
    rows = {r["credit_code"]: r for r in frameworks.table()}
    assert rows["IL-24"]["gri"] == "GRI 101-4, GRI 101-5" and rows["IL-24"]["esrs"] == "E4"
    assert "GRI 101-2" in rows["OP-4"]["gri"] and "E4" in rows["OP-4"]["esrs"]


def test_il24_status_depends_on_the_university():
    cork = gri_index.entry("cork", "101-4")
    dublin = gri_index.entry("tudublin", "101-4")
    assert cork.status == "partial" and "IL-24" in cork.reason
    assert dublin.status == "none" and "Non applicable" in dublin.reason
