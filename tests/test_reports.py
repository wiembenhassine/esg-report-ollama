"""
Contrôles sur les rapports générés (ignorés tant que le pipeline n'a pas tourné).

Chaque nombre d'une section narrative doit être la valeur affichée d'un fait,
et chaque fait cité doit exister dans facts.csv : la chaîne
« LLM -> placeholder -> code » n'a laissé passer aucun chiffre inventé.
"""

import json

import pytest

from esg import facts
from esg.config import OUTPUTS
from esg.guard import check_rendered, numbers_in, PLACEHOLDER

CACHES = sorted((OUTPUTS / "cache").glob("*/*.json")) if (OUTPUTS / "cache").exists() else []


@pytest.mark.skipif(not CACHES, reason="aucune section générée (lancer python -m esg.pipeline)")
@pytest.mark.parametrize("path", CACHES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_section_numbers_trace_to_facts(path):
    r = json.loads(path.read_text(encoding="utf-8"))
    if r["decision"] == "repli":
        return
    f = facts.load(r["institution"])
    for fid in r["used_facts"]:
        assert fid in f, f"fait inconnu {fid}"
    displays = {fid: f[fid]["display"] for fid in r["used_facts"]}
    assert check_rendered(r["text"], displays) == []
    assert not PLACEHOLDER.search(r["text"]), "placeholder non substitué"


@pytest.mark.skipif(not CACHES, reason="aucune section générée")
@pytest.mark.parametrize("path", CACHES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_accepted_sections_passed_the_guard(path):
    r = json.loads(path.read_text(encoding="utf-8"))
    if r["decision"] == "repli":
        return
    final = [a for a in r["history"] if a.get("rendered") == r["text"]]
    assert final and not final[0]["guard_problems"] and not final[0]["lint_problems"]


def test_numbers_in_ignores_references():
    assert numbers_in("GRI 305-1, OP-6, Scope 2") == []
