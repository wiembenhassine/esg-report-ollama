"""Client Ollama minimal (API HTTP locale, aucune clé, aucun coût)."""

import json
import time

import requests

from esg.config import EMBED_MODEL, GEN_MODEL, OLLAMA_URL

KEEP_ALIVE = "30m"      # garde le modèle en mémoire entre deux sections (CPU : chargement lent)


class OllamaError(RuntimeError):
    pass


def chat(messages: list[dict], *, model: str = GEN_MODEL, temperature: float = 0.3,
         num_predict: int = 520, num_ctx: int = 4096, schema: dict | None = None,
         seed: int = 42, timeout: int = 1800) -> dict:
    """Renvoie {"text", "seconds", "prompt_tokens", "output_tokens"}.

    `schema` active la sortie structurée JSON d'Ollama (utilisée par le juge).
    Le message système doit rester identique d'un appel à l'autre : Ollama
    réutilise alors le préfixe déjà calculé, ce qui compte beaucoup sur CPU.
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": temperature, "num_predict": num_predict,
                    "num_ctx": num_ctx, "seed": seed},
    }
    if schema:
        payload["format"] = schema
    t0 = time.time()
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as e:
        raise OllamaError(f"Ollama injoignable ou en erreur ({e}). Lance `ollama serve`.") from e
    d = r.json()
    return {"text": d["message"]["content"], "seconds": round(time.time() - t0, 1),
            "prompt_tokens": d.get("prompt_eval_count", 0), "output_tokens": d.get("eval_count", 0)}


def chat_json(messages: list[dict], schema: dict, **kw) -> dict:
    out = chat(messages, schema=schema, temperature=0.0, **kw)
    try:
        out["json"] = json.loads(out["text"])
    except json.JSONDecodeError as e:
        raise OllamaError(f"réponse JSON invalide du modèle : {out['text'][:200]}") from e
    return out


def embed(texts: list[str], *, batch: int = 32, timeout: int = 600) -> list[list[float]]:
    vectors = []
    for i in range(0, len(texts), batch):
        try:
            r = requests.post(f"{OLLAMA_URL}/api/embed",
                              json={"model": EMBED_MODEL, "input": texts[i:i + batch],
                                    "keep_alive": KEEP_ALIVE},
                              timeout=timeout)
            r.raise_for_status()
        except requests.RequestException as e:
            raise OllamaError(f"embeddings Ollama en erreur ({e})") from e
        vectors.extend(r.json()["embeddings"])
    return vectors
