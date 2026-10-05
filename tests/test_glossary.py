"""
Correction 5 : lexique des sigles et règle de matérialité (cas réels du rapport de Dublin).
"""

from esg import generate, gri_index, guard, judge, llm


def test_wrong_expansion_of_sec_is_refused_and_right_ones_pass():
    bad = ["Les activités sont menées avec les Services de l'État (SEC).",
           "L'université participe au Comité des services communs (SEC)."]
    good = ["L'université participe aux communautés énergétiques durables (SEC).",
            "Les Sustainable Energy Communities (SEC) regroupent des voisins du campus."]
    for t in bad:
        assert any("sigle SEC mal développé" in p for p in guard.check_draft(t, set()))
    for t in good:
        assert guard.check_draft(t, set()) == []


def test_materiality_claim_is_removed_by_repair():
    text = ("Le TU Dublin a identifié les thèmes matériels suivants dans son rapport STARS. "
            "Les domaines d'objectifs fixés par STARS couvrent les opérations du campus (GRI 3-2).")
    fixed, removed = guard.repair(text, set(), {})
    assert fixed == "Les domaines d'objectifs fixés par STARS couvrent les opérations du campus (GRI 3-2)."
    assert len(removed) == 1


def test_glossary_reaches_writer_and_judge(monkeypatch):
    lines = guard.glossary_lines("TU Dublin members participate in SECs sponsored by the SEAI.")
    assert any(l.startswith("- SEC = Sustainable Energy Community") for l in lines)
    assert any(l.startswith("- SEAI = ") for l in lines)
    sec = gri_index.section("strategie")
    entries = [gri_index.entry("tudublin", c) for c in sec["disclosures"]]
    prompt = generate.build_prompt("tudublin", sec, [{"credit": "PA-2", "text": "members of the SEC"}], [],
                                   generate.section_values("tudublin", sec, entries), entries, [])
    assert "SIGLES" in prompt and "SEC = Sustainable Energy Community" in prompt
    seen = {}

    def fake(messages, schema, **k):
        seen["user"] = messages[1]["content"]
        seen["system"] = messages[0]["content"]
        return {"json": {"claims": [], "rule_violations": [], "score": 5, "feedback": ""}, "seconds": 0}
    monkeypatch.setattr(llm, "chat_json", fake)
    judge.judge("Texte avec les Services de l'État (SEC).", [], [], [], ["[PA-2] members of the SEC"])
    assert "ACRONYMS:" in seen["user"] and "SEC = Sustainable Energy Community" in seen["user"]
    assert "material" in seen["system"] and "number of students" in seen["system"]
