"""
Qualité du rapport, au rendu et sans LLM (7 octobre, demandes de Wiem) :
C — « Points forts et points à améliorer » écrit par le code depuis la table des faits ;
D — annexe : nombre d'essais calculé, colonnes GRI compréhensibles ;
style — « l'Université » en nom commun, phrases creuses retirées.
"""

import json

from esg import facts, generate, guard, render, style
from esg.config import OUTPUTS


def test_thresholds_follow_the_agreed_rule():
    assert render.classify(1.0) == render.classify(0.75) == "fort"
    assert render.classify(0.7499) == render.classify(0.40) == "partiel"
    assert render.classify(0.3999) == render.classify(0.0) == "faible"


def test_cork_environment_strengths_and_weaknesses_come_from_the_fact_table():
    md = render.strengths_md("cork", "environnement")
    forts, partiels, faibles = [l for l in md.splitlines() if l.startswith("- **")]
    for code in ("OP-3", "OP-12", "OP-11", "OP-1", "OP-14", "OP-4", "IL-24"):
        assert code in forts
    for code in ("OP-5", "OP-6", "OP-2"):
        assert code in partiels
    for code in ("OP-15", "OP-13", "OP-10", "OP-9"):
        assert code in faibles
    assert "OP-15 Voyages en avion (0 sur 2)" in faibles and "OP-13 Flotte de véhicules (0,67 sur 2)" in faibles
    # Chaque nombre des listes est une valeur de la table des faits (aucun nombre inventé).
    f = facts.load("cork")
    allowed = {n for r in f.values() for n in guard.numbers_in(r["display"])}
    listed = "\n".join(l for l in md.splitlines() if l.startswith("- **"))
    assert set(guard.numbers_in(listed)) <= allowed


def test_every_section_of_every_report_gets_the_paragraph():
    for key in ("berkeley", "cork", "tudublin"):
        for sec in ("organisation", "materialite", "gouvernance", "strategie", "parties_prenantes",
                    "environnement", "social", "enseignement"):
            assert render.strengths_md(key, sec).startswith("#### Points forts et points à améliorer")


def test_annex_states_the_real_number_of_attempts_and_explains_gri_columns():
    results = [json.loads((OUTPUTS / "cache" / "cork" / f"{s}.json").read_text(encoding="utf-8"))
               for s in ("environnement", "enseignement")]
    md = render.validation_md(results, "cork")
    assert generate.MAX_ATTEMPTS == 2 and "deux essais au plus" in md and "trois tentatives" not in md
    assert "Codes GRI cités dans le texte" in md and "Publications GRI avec données (index)" in md
    assert "| 6 sur 35 |" in md                                   # environnement de Cork, d'après l'index
    assert "c'est une mesure de citation, pas de couverture des données" in md


def test_style_fixes_case_and_drops_hollow_sentences_only():
    text = ("Les fonds de l'Université sont gérés par Cantor Fitzgerald. L'Université européenne de technologie "
            "réunit plusieurs écoles. Le conseil des régents de l'Université de Californie gouverne le système.")
    out = style.clean(text)
    assert "fonds de l'université sont gérés" in out
    assert "L'Université européenne de technologie" in out and "l'Université de Californie" in out
    hollow = ("La création du Forum des étudiants vise à renforcer la transparence. Cette approche permet à "
              "l'université de cultiver des citoyens qui contribuent au bien commun et au mieux-être de l'humanité "
              "et de la planète. L'engagement des parties prenantes est un aspect clé de la stratégie de l'UCC.")
    assert style.clean(hollow) == "La création du Forum des étudiants vise à renforcer la transparence."
