"""
Demande de rapport dans l'assistant : « génère le rapport de Cork », « rapport TU Dublin »…
Par défaut, rendu du rapport validé depuis le cache (sans LLM) ; vraie génération seulement après « oui ».
Aucun test n'écrit dans outputs/ ni n'appelle Ollama : le rendu et le lancement sont remplacés par des doublures.
"""

import pytest

from esg import chat, llm, render
from esg.config import INSTITUTIONS


@pytest.mark.parametrize("question, keys, regen", [
    ("génère le rapport de Cork", ["cork"], False),
    ("Fais-moi le rapport de Berkeley", ["berkeley"], False),
    ("rapport TU Dublin", ["tudublin"], False),
    ("génère les rapports des trois universités", ["berkeley", "cork", "tudublin"], False),
    ("Régénère le rapport de Cork avec Ollama", ["cork"], True),
    ("rapport UCC avec le LLM", ["cork"], True),
])
def test_report_requests_are_recognised(question, keys, regen):
    req = chat.report_request(question)
    assert req == {"keys": keys, "regenerate": regen}


@pytest.mark.parametrize("question", [
    "Que dit le rapport STARS de Cork sur l'eau ?",
    "Montre-moi le rapport de Cork sur l'eau",
    "Comment Cork gère-t-il ses déchets ?",
    "Compare Cork et TU Dublin sur les déchets",
    "Quel est le score biodiversité de Cork ?",
    "Combien de tonnes de CO2 Berkeley a-t-il émis ?",
])
def test_normal_questions_are_unchanged(question):
    assert chat.report_request(question) is None


def test_unknown_university_lists_the_available_ones():
    req = chat.report_request("génère le rapport de Harvard")
    assert req == {"keys": [], "regenerate": False}
    said = []
    assert chat.report_command(req, log=said.append) is None
    assert "Rapports disponibles" in said[0] and "TU Dublin" in said[0] and "trois universités" in said[0]


def test_default_renders_the_validated_report_from_cache_without_llm(monkeypatch, tmp_path):
    def no_llm(*a, **k):
        raise AssertionError("le LLM ne doit pas être appelé")
    monkeypatch.setattr(llm, "chat", no_llm)
    written, opened = [], []

    def fake_write(name, md_text, title, prov=None):
        written.append((name, md_text, title))
        return {"md": tmp_path / "r.md", "html": tmp_path / "r.html", "docx": tmp_path / "r.docx",
                "pdf": tmp_path / "r.pdf"}
    monkeypatch.setattr(render, "write", fake_write)
    said = []
    chat.report_command(chat.report_request("génère le rapport de Cork"), opener=opened.append, log=said.append)
    assert [w[0] for w in written] == ["cork"]
    name, md_text, title = written[0]
    assert title == "Rapport de durabilité — University College Cork"
    assert "10,63 points STARS sur 16 au crédit OP-6" in md_text          # texte validé, chiffres du code
    assert "Relecture hors pipeline" in md_text                            # relecture appliquée
    assert opened == [tmp_path / "r.pdf"]
    assert any("8 sections" in s for s in said) and any("Word" in s for s in said)


def test_regeneration_asks_first_and_does_nothing_on_no():
    runs, said = [], []
    req = chat.report_request("régénère le rapport de Cork")
    out = chat.report_command(req, ask=lambda prompt: "non", run=lambda *a, **k: runs.append(a), log=said.append)
    assert out is None and runs == []
    text = "\n".join(said)
    assert "1 h 30" in text and "PAS été relu" in text and "veille" in text
    assert said[-1].startswith("Génération annulée")


def test_regeneration_runs_the_pipeline_with_ollama_after_yes(tmp_path):
    calls = []

    class Done:
        returncode = 0

    def fake_run(args, cwd=None):
        calls.append(args)
        return Done()
    req = chat.report_request("régénère le rapport de Cork avec Ollama")
    code = chat.report_command(req, ask=lambda prompt: "oui", run=fake_run, opener=lambda p: None, log=lambda s: None)
    assert code == 0
    assert len(calls) == 2                                              # passe 1, puis passe 2 (replis)
    assert calls[0][1:7] == ["-u", "-m", "esg.pipeline", "cork", "--no-comparison", "--no-cache"]
    assert "--no-cache" not in calls[1] and calls[0][-2] == calls[1][-2] == "--log"
    assert "outputs" in calls[0][-1] and calls[0][-1].endswith("passe1.log") and calls[1][-1].endswith("passe2.log")
    every = []
    chat.report_command(chat.report_request("régénère les rapports des trois universités"), ask=lambda p: "oui",
                        run=lambda a, cwd=None: every.append(a) or Done(), opener=lambda p: None, log=lambda s: None)
    assert set(INSTITUTIONS) <= set(every[0]) and "--no-comparison" in every[0]       # les 3, sans la synthèse


def test_handle_routes_report_requests_and_normal_questions(monkeypatch):
    seen = []
    monkeypatch.setattr(chat, "show", lambda q: seen.append(("question", q)))
    monkeypatch.setattr(chat, "report_command", lambda req, **k: seen.append(("rapport", req["keys"])))
    chat.handle("Comment Cork gère-t-il ses déchets ?")
    chat.handle("génère le rapport de Cork")
    assert seen == [("question", "Comment Cork gère-t-il ses déchets ?"), ("rapport", ["cork"])]
