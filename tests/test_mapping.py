"""Cohérence de la table de correspondance STARS -> GRI écrite à la main."""

import csv

from esg import gri_index
from esg.config import INSTITUTIONS, RAW

MAP = gri_index.load_map()
KNOWN_CREDITS = {r["credit_code"] for r in csv.DictReader(open(RAW / "scores" / "combined_esg_dataset.csv",
                                                                encoding="utf-8"))}


def test_78_disclosures_in_13_standards():
    codes = list(MAP["disclosures"])
    assert len(codes) == 78
    assert {gri_index.standard_of(c) for c in codes} == set(MAP["standards"])
    assert len(MAP["standards"]) == 13


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
