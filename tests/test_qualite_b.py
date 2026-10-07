"""
Qualité du texte rédigé (étape B, 7 octobre) : 2 à 3 extraits par crédit, questions du formulaire
STARS retirées, consignes de contenu et de ton, liste de scores refusée, phrase creuse retirée.
Aucun appel à Ollama : l'index est remplacé par une petite doublure.
"""

import inspect

import numpy as np

from esg import generate, guard, judge, llm, rag


def test_form_questions_and_url_lines_are_not_evidence():
    assert not rag.useful("Number of marginalised racial, ethnic, and/or Indigenous groups in the region (required)")
    assert not rag.useful("URL References:Ref1: https://www.ucc.ie/en/hr/policies/leave/ Ref2: https://x.org/a")
    assert rag.useful("UCC's Centre for Adult and Continuing Education offers the Diploma in Environment.")


def fake_index(lines_per_credit: dict[str, int]) -> rag.Index:
    ix = rag.Index.__new__(rag.Index)
    ix.items, vecs = [], []
    for code, n in lines_per_credit.items():
        for i in range(n):
            ix.items.append({"corpus": "narrative", "inst": "cork", "credit": code, "line": i,
                             "text": f"{code} line {i}: " + "a concrete sentence about the programme " * 8})
            vecs.append([1.0 - i * 0.1, i * 0.1])               # la ligne 0 est toujours la plus proche
    ix.vectors = np.array(vecs, dtype=np.float32)
    ix._query = lambda text: np.array([1.0, 0.0], dtype=np.float32)
    return ix


def test_two_or_three_extracts_per_credit_and_budget_keeps_the_first():
    few = fake_index({"PA-1": 5, "PA-2": 5}).evidence_by_credit("cork", ["PA-1", "PA-2"], "governance")
    assert [p["credit"] for p in few] == ["PA-1"] * 3 + ["PA-2"] * 3          # 4 crédits ou moins : 3
    many_codes = [f"OP-{i}" for i in range(1, 7)]
    many = fake_index({c: 4 for c in many_codes}).evidence_by_credit("cork", many_codes, "environment")
    assert all(sum(p["credit"] == c for p in many) == 2 for c in many_codes)   # plus de 4 crédits : 2
    tight = fake_index({c: 4 for c in many_codes}).evidence_by_credit("cork", many_codes, "environment",
                                                                     max_chars=1500)
    assert {p["credit"] for p in tight} == set(many_codes)                     # jamais la 1re ligne retirée
    assert all(p["line"] == 0 for p in tight)


def test_a_list_of_scores_is_sent_back_for_rewriting():
    old_cork_teaching = "\n".join(
        ["### Enseignement, recherche et engagement", "",
         "L'Université College Cork (UCC) a démontré sa détermination à intégrer la durabilité. "
         "Les résultats des crédits STARS suivants reflètent cette approche :", ""]
        + [f"- L'université obtient {{{{ {c} }}}} au crédit {c[:2]}-{c[2:]}." for c in
           ("AC1", "AC2", "AC3", "AC6", "AC7", "EN1", "EN2", "EN3", "EN5", "EN7")])
    blocking, _, _ = judge.lint(guard.PLACEHOLDER.sub("X", old_cork_teaching) + " mot" * 90, [])
    assert any("liste de scores" in b for b in blocking)
    prose = ("### Enseignement\n\nLe Centre for Adult and Continuing Education propose le Diploma in Environment, "
             "Sustainability and Climate, ouvert aux professionnels qui veulent intégrer la durabilité dans leur "
             "organisation ; l'université obtient {{ EN7 }}. Le Sustainability Institute réunit des chercheurs "
             "de plusieurs disciplines autour de l'action climatique et de l'économie circulaire.")
    assert not judge.score_list(guard.PLACEHOLDER.sub("X", prose))


def test_hollow_sentence_is_removed_during_generation():
    fixed, removed = guard.repair("Le Forum des étudiants vise la transparence. L'engagement des parties prenantes "
                                  "est un aspect clé de la stratégie de l'université.", set(), {})
    assert fixed == "Le Forum des étudiants vise la transparence." and len(removed) == 1


def test_writer_and_judge_get_the_new_rules_and_a_larger_context():
    assert "PAS de liste de scores" in generate.WRITER_SYSTEM
    assert "Pour chaque crédit présent dans le CONTEXTE" in generate.WRITER_SYSTEM
    assert "grandiloquent" in judge.SYSTEM and "list\n     of scores" in judge.SYSTEM
    assert inspect.signature(llm.chat).parameters["num_ctx"].default == 6144
