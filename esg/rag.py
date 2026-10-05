"""
RAG local : embeddings nomic-embed-text (via Ollama) + similarité cosinus numpy.

Pourquoi pas ChromaDB : le corpus est petit (~1 700 passages) et ChromaDB
s'installe mal sur Python 3.14. Un index numpy sauvegardé sur disque suffit
et reste transparent.

Deux corpus :
  - récits des établissements (une ligne STARS = un passage), filtrés par
    crédit : la correspondance GRI dit QUELS crédits lire, l'embedding dit
    QUELLES lignes de ces crédits sont les plus pertinentes ;
  - corpus de connaissances ESG (data/raw/knowledge), découpé en blocs, pour
    le vocabulaire du reporting.

Tous les passages sont masqués (`mask_numbers`) AVANT d'être indexés : le
LLM rédacteur ne reçoit jamais de chiffre par le contexte.
"""

import hashlib
import json

import numpy as np

from esg import llm, sources
from esg.config import INSTITUTIONS, PROCESSED, RAW

INDEX_FILE = PROCESSED / "embeddings.npz"
MAX_PASSAGE = 700
DOC_PREFIX, QUERY_PREFIX = "search_document: ", "search_query: "   # préfixes requis par nomic


def _knowledge_chunks(words_per_chunk: int = 120) -> list[dict]:
    out = []
    for path in sorted((RAW / "knowledge").glob("*.txt")):
        words = path.read_text(encoding="utf-8").split()
        for i in range(0, len(words), words_per_chunk):
            text = sources.mask_numbers(" ".join(words[i:i + words_per_chunk]))
            if len(text) > 200:
                out.append({"corpus": "knowledge", "inst": "", "credit": "", "source": path.stem, "text": text})
    return out


def passages() -> list[dict]:
    from esg.gri_index import load_map
    wanted = {c for s in load_map()["sections"] for c in s["credits"]}     # crédits utilisés par le rapport
    out = []
    for key in INSTITUTIONS:
        for code, c in sources.credits(key).items():
            if code not in wanted:
                continue
            for i, line in enumerate(c["lines"]):
                text = sources.mask_numbers(line)[:MAX_PASSAGE]
                out.append({"corpus": "narrative", "inst": key, "credit": code, "line": i,
                            "source": c["url"], "text": text})
    return out + _knowledge_chunks()


def _fingerprint(items: list[dict]) -> str:
    h = hashlib.sha256()
    for p in items:
        h.update(p["text"].encode("utf-8"))
    return h.hexdigest()[:16]


class Index:
    def __init__(self):
        self.items = passages()
        fp = _fingerprint(self.items)
        if INDEX_FILE.exists():
            z = np.load(INDEX_FILE, allow_pickle=False)
            if str(z["fingerprint"]) == fp:
                self.vectors = z["vectors"]
                return
        print(f"[rag] calcul des embeddings de {len(self.items)} passages (une seule fois)…", flush=True)
        vecs = []
        for i in range(0, len(self.items), 64):
            vecs += llm.embed([DOC_PREFIX + p["text"][:500] for p in self.items[i:i + 64]])
            print(f"[rag]   {min(i + 64, len(self.items))}/{len(self.items)}", flush=True)
        vecs = np.array(vecs, dtype=np.float32)
        self.vectors = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        PROCESSED.mkdir(parents=True, exist_ok=True)
        np.savez(INDEX_FILE, vectors=self.vectors, fingerprint=fp)

    def _query(self, text: str) -> np.ndarray:
        q = np.array(llm.embed([QUERY_PREFIX + text])[0], dtype=np.float32)
        return q / np.linalg.norm(q)

    def evidence(self, key: str, credits: list[str], topic: str, k: int = 10,
                 max_chars: int = 2600) -> list[dict]:
        """Lignes de l'établissement pour ces crédits : la meilleure de chaque crédit,
        puis les plus proches du thème, dans une limite de taille (CPU)."""
        idx = [i for i, p in enumerate(self.items)
               if p["corpus"] == "narrative" and p["inst"] == key and p["credit"] in credits]
        if not idx:
            return []
        sims = self.vectors[idx] @ self._query(topic)
        ranked = [idx[j] for j in np.argsort(-sims)]
        chosen, seen_credit = [], set()
        for i in ranked:                                  # 1) diversité : une ligne par crédit
            if self.items[i]["credit"] not in seen_credit:
                chosen.append(i)
                seen_credit.add(self.items[i]["credit"])
        for i in ranked:                                  # 2) complément par pertinence
            if i not in chosen:
                chosen.append(i)
        out, size = [], 0
        for i in chosen[:k * 2]:
            p = self.items[i]
            if size + len(p["text"]) > max_chars or len(out) >= k:
                continue
            out.append(p)
            size += len(p["text"])
        order = {c: n for n, c in enumerate(credits)}
        return sorted(out, key=lambda p: order.get(p["credit"], 99))

    def knowledge(self, topic: str, k: int = 1) -> list[dict]:
        idx = [i for i, p in enumerate(self.items) if p["corpus"] == "knowledge"]
        sims = self.vectors[idx] @ self._query(topic)
        return [self.items[idx[j]] for j in np.argsort(-sims)[:k]]


_INDEX = None


def get_index() -> Index:
    global _INDEX
    if _INDEX is None:
        _INDEX = Index()
    return _INDEX


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    ix = get_index()
    print(json.dumps(ix.evidence("cork", ["PA-3", "EN-6"], "consultation of students and local community", k=5),
                     ensure_ascii=False, indent=1)[:2500])
