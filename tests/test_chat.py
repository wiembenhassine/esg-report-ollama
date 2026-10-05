"""
Correction 3 : l'assistant de questions-réponses.

Le modèle est simulé : on vérifie ce que fait le CODE autour de lui (choix des universités et des
crédits, chiffres insérés, phrases retirées, données absentes dites par le code).
Questions tirées du test du 4 octobre 2026.
"""

import pytest

from esg import chat, guard

TRICKY = {  # mot qui déclenchait un faux sujet -> crédits attendus
    "Quel est le score biodiversité de Cork ?": ["IL-24", "OP-4"],
    "Combien d'arbres a planté Berkeley ?": [],
    "Quel est l'impact de Cork sur la planète ?": [],
    "Le parcours des étudiants à Cork": [],
    "Un rachat de matériel à Cork": [],
    "Une équipe énergique à Cork": [],
    "Les emissions de Berkeley ?": ["OP-6"],               # sans accent
    "Le plan stratégique de TU Dublin": ["PA-2"],
}


class NoIndex:
    def evidence(self, *a, **k):
        return []


@pytest.fixture
def model(monkeypatch):
    """Remplace Ollama par une réponse fixée ; renvoie une fonction pour la choisir."""
    monkeypatch.setattr(chat.rag, "get_index", lambda: NoIndex())
    state = {}
    monkeypatch.setattr(chat.llm, "chat", lambda *a, **k: {"text": state["reply"], "seconds": 0})
    return lambda reply: state.__setitem__("reply", reply)


@pytest.mark.parametrize("question,expected", TRICKY.items())
def test_whole_words_without_accents(question, expected):
    assert chat.credits_for(question) == expected


def test_students_no_longer_select_tu_dublin():
    assert chat.institutions("Combien d'étudiants à Cork participent ?") == ["cork"]


def test_biodiversity_cork_gives_il24_and_op4(model):
    model("Pour la biodiversité, Cork obtient {{ cork_IL24 }} ainsi que {{ cork_OP4 }}.")
    r = chat.answer("Quel est le score biodiversité de Cork ?")
    assert "1 point STARS sur 1 au crédit IL-24, niveau maximal" in r["text"]
    assert "4,06 points STARS sur 5 au crédit OP-4, niveau élevé" in r["text"]
    assert chat.NOT_AVAILABLE not in r["text"]


def test_biodiversity_tu_dublin_gives_op4_and_says_il24_is_missing(model):
    model("Pour la biodiversité, TU Dublin obtient {{ tudublin_OP4 }}.")
    r = chat.answer("Quel est le score biodiversité de TU Dublin ?")
    assert "0,69 point STARS sur 5 au crédit OP-4, niveau faible" in r["text"]
    assert "aucun résultat IL-24 (Évaluation de la biodiversité" in r["text"] and "pour TU Dublin" in r["text"]
    assert "marqué « Non applicable » dans son rapport STARS (raison non fournie" in r["text"]
    assert set(guard.numbers_in(r["text"])) <= {"0,69", "5"}         # rien d'inventé


def test_model_cannot_invent_the_missing_il24(model):
    model("TU Dublin obtient {{ tudublin_IL24 }} pour la biodiversité. TU Dublin obtient {{ tudublin_OP4 }}.")
    r = chat.answer("Quel est le score biodiversité de TU Dublin ?")
    assert "IL-24, niveau" not in r["text"] and "0,69" in r["text"]


def test_energy_comparison_drops_the_rating_mixup(model):
    model("Cork obtient {{ cork_OP5 }}, ce qui correspond à la note Platinum. "
          "TU Dublin obtient {{ tudublin_OP5 }}.")
    r = chat.answer("Compare Cork et Dublin sur l'énergie")
    assert r["keys"] == ["cork", "tudublin"] and r["credits"] == ["OP-5"]
    assert "Platinum" not in r["text"] and "6,34 points STARS sur 10 au crédit OP-5" in r["text"]
    assert any("Platinum" in s for s in r["removed"])


def test_trees_answered_by_code_without_the_model(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("le modèle ne doit pas être appelé")
    monkeypatch.setattr(chat.llm, "chat", boom)
    r = chat.answer("Combien d'arbres a planté Berkeley ?")
    assert r["text"].startswith(chat.NOT_AVAILABLE) and r["source"] == "code"
