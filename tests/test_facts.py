"""
Les faits sont recalculés ici directement depuis les fichiers bruts, sans
passer par esg.facts : si le code de production se trompe, ces tests le voient.
"""

import csv

import pytest

from esg import facts
from esg.config import INSTITUTIONS, RAW

RAW_ROWS = list(csv.DictReader(open(RAW / "scores" / "combined_esg_dataset.csv", encoding="utf-8")))


def parse_fr(display: str) -> float:
    return float(display.replace(" ", "").replace(" %", "").replace(" ", "").replace(",", "."))


@pytest.mark.parametrize("key", list(INSTITUTIONS))
def test_every_credit_score_matches_raw_csv(key):
    f = facts.load(key)
    rows = [r for r in RAW_ROWS if r["institution"] == INSTITUTIONS[key]["name"] and r["score"].strip()]
    assert rows
    for r in rows:
        v = r["credit_code"].replace("-", "")
        assert parse_fr(f[f"{v}_score"]["display"]) == pytest.approx(float(r["score"]))
        assert parse_fr(f[f"{v}_max"]["display"]) == pytest.approx(float(r["max"]))


@pytest.mark.parametrize("key", list(INSTITUTIONS))
def test_pillar_totals_rederived_independently(key):
    f = facts.load(key)
    rows = [r for r in RAW_ROWS if r["institution"] == INSTITUTIONS[key]["name"] and r["score"].strip()]

    def pillar(code):
        if code.startswith("OP-"):
            return "ENV"
        if code.startswith("PA-"):
            return "GOV" if int(code[3:]) <= 5 else "SOC"
        if code[:3] in ("AC-", "EN-"):
            return "CTX"
        return None

    for pid in ("ENV", "SOC", "GOV", "CTX"):
        sel = [r for r in rows if pillar(r["credit_code"]) == pid]
        pts, mx = sum(float(r["score"]) for r in sel), sum(float(r["max"]) for r in sel)
        assert float(f[f"{pid}_points"]["number"]) == pytest.approx(pts, abs=0.01)
        assert float(f[f"{pid}_max"]["number"]) == pytest.approx(mx, abs=0.01)
        assert parse_fr(f[f"{pid}_pct"]["display"]) == pytest.approx(round(100 * pts / mx, 1))


def test_tudublin_investment_credits_are_not_scored():
    f = facts.load("tudublin")
    assert "PA4_score" not in f and "PA5_score" not in f


def test_overall_scores():
    expected = {"berkeley": 86.76, "cork": 85.99, "tudublin": 83.35}
    for key, score in expected.items():
        assert float(facts.load(key)["STARS_score"]["number"]) == score


def test_bands():
    assert facts.band(16, 16).startswith("maximal")
    assert facts.band(0, 2).startswith("nul")
    assert facts.band(1, 4) == "faible"
    assert facts.band(3, 4) == "élevé"
