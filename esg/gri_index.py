"""
Index de contenu GRI : statut de chaque publication, calculé par le code
à partir de mapping/gri_map.yaml, des faits extraits et des récits STARS.
Le LLM n'intervient pas ici.
"""

from dataclasses import dataclass
from functools import lru_cache

import yaml

from esg import facts, sources
from esg.config import MAPPING

STATUS_LABELS = {
    "reported": "Rapporté",
    "partial": "Partiellement rapporté",
    "none": "Non rapporté",
    "pending": "Non évalué",
}


@lru_cache(maxsize=None)
def load_map() -> dict:
    with open(MAPPING / "gri_map.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def standard_of(code: str) -> str:
    return "GRI " + code.split("-")[0]


@dataclass
class Entry:
    code: str
    title: str
    standard: str
    status: str            # reported | partial | none | pending
    reason: str
    note: str
    fact_ids: list
    credits: list

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]


def matching_facts(key: str, spec: dict) -> list[str]:
    """Faits « field » dont le libellé commence par l'un des libellés attendus."""
    wanted = [w.lower() for w in spec.get("fields", [])]
    credits = set(spec.get("credits", []))
    out = []
    for fid, r in facts.load(key).items():
        if r["kind"] != "field" or r["credit_code"] not in credits:
            continue
        label = r["label"].lower()
        if any(label.startswith(w) or w in label for w in wanted):
            out.append(fid)
    return out


def has_narrative(key: str, credits: list[str]) -> list[str]:
    cr = sources.credits(key)
    return [c for c in credits if cr.get(c, {}).get("lines")]


def entry(key: str, code: str) -> Entry:
    spec = load_map()["disclosures"][code]
    credits = spec.get("credits", [])
    coverage = spec.get("coverage", "none")
    note = spec.get("note", "")
    base = dict(code=code, title=spec["title"], standard=standard_of(code), note=note, credits=credits)

    if coverage == "none":
        return Entry(status="none", reason="Aucune donnée STARS ne correspond à cette publication.",
                     fact_ids=[], **base)

    fids = matching_facts(key, spec)
    if fids:
        return Entry(status=coverage, reason=f"{len(fids)} valeur(s) STARS extraite(s) ({', '.join(credits)}).",
                     fact_ids=fids, **base)

    narr = has_narrative(key, credits) if spec.get("qualitative") else []
    if narr:
        return Entry(status="partial",
                     reason=f"Couvert par le récit de l'établissement ({', '.join(narr)}) ; "
                            "les champs structurés n'ont pas été extraits.",
                     fact_ids=[], **base)

    return Entry(status="pending",
                 reason=f"Champ STARS identifié ({', '.join(credits)}) mais valeur non extraite : "
                        "nécessite les pages STARS authentifiées.",
                 fact_ids=[], **base)


def index(key: str) -> list[Entry]:
    return [entry(key, code) for code in load_map()["disclosures"]]


def counts(entries: list[Entry]) -> dict[str, int]:
    out = {s: 0 for s in STATUS_LABELS}
    for e in entries:
        out[e.status] += 1
    return out


def section(sec_id: str) -> dict:
    for s in load_map()["sections"]:
        if s["id"] == sec_id:
            return s
    raise KeyError(sec_id)


def cautions(key: str, sec_id: str) -> list[str]:
    has_fields = any(r["kind"] == "field" for r in facts.load(key).values())
    return [c["text"] for c in load_map().get("cautions", {}).get(key, [])
            if c["section"] == sec_id and (has_fields or not c.get("requires_fields"))]
