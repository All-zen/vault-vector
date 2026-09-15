"""Cliente de embeddings do Ollama, sem dependencia externa.

Usa /api/embed (aceita lote) e cai para /api/embeddings (um por vez) em
versoes antigas do Ollama.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import numpy as np


class EmbeddingError(RuntimeError):
    pass


class OllamaEmbedder:
    def __init__(
        self,
        url: str = "http://127.0.0.1:11434",
        model: str = "bge-m3",
        timeout: float = 120.0,
        batch_size: int = 16,
        retries: int = 2,
        num_thread: int = 0,
    ):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.batch_size = batch_size
        self.retries = retries
        # 0 = deixa o llama.cpp decidir (nucleos fisicos). Subir so ajuda se
        # houver nucleo ocioso de verdade; hyperthread rende pouco aqui.
        self.num_thread = num_thread
        self._batch_supported = True

    # ------------------------------------------------------------------ http
    def _post(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")[:300]
                if exc.code == 404:
                    raise EmbeddingError(f"404 em {path}: {body}") from exc
                last = EmbeddingError(f"HTTP {exc.code} em {path}: {body}")
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = EmbeddingError(
                    f"Nao consegui falar com o Ollama em {self.url}: {exc}. "
                    "O servico esta rodando? (ollama serve)"
                )
            if attempt < self.retries - 1:
                time.sleep(1.5 * (attempt + 1))
        raise last or EmbeddingError("falha desconhecida ao gerar embeddings")

    # ------------------------------------------------------------------- api
    def check(self) -> dict:
        """Confirma que o servico responde e que o modelo esta baixado."""
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=10) as resp:
                tags = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise EmbeddingError(
                f"Ollama inacessivel em {self.url}: {exc}. Rode 'ollama serve'."
            ) from exc
        names = [m.get("name", "") for m in tags.get("models", [])]
        base = {n.split(":")[0] for n in names}
        if self.model not in names and self.model.split(":")[0] not in base:
            raise EmbeddingError(
                f"Modelo '{self.model}' nao encontrado no Ollama. "
                f"Rode: ollama pull {self.model}\nDisponiveis: {', '.join(names) or 'nenhum'}"
            )
        return {"url": self.url, "model": self.model, "available": names}

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        if not texts:
            return []
        out: list[np.ndarray] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            out += self._embed_resiliente(batch)
        return out

    def _embed_resiliente(self, batch: list[str]) -> list[np.ndarray]:
        """Em timeout, parte o lote ao meio em vez de insistir no mesmo.

        Timeout aqui quase sempre significa lote grande demais para a CPU
        disponivel no momento. Repetir a mesma chamada tres vezes so gasta o
        triplo do tempo para falhar igual; metade do lote costuma passar.
        """
        try:
            return self._embed_batch(batch)
        except EmbeddingError as exc:
            if len(batch) <= 1 or "timed out" not in str(exc).lower():
                raise
            meio = len(batch) // 2
            return self._embed_resiliente(batch[:meio]) + self._embed_resiliente(
                batch[meio:]
            )

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]

    def _embed_batch(self, batch: list[str]) -> list[np.ndarray]:
        opcoes = {"num_thread": self.num_thread} if self.num_thread else None

        if self._batch_supported:
            try:
                corpo = {"model": self.model, "input": batch}
                if opcoes:
                    corpo["options"] = opcoes
                data = self._post("/api/embed", corpo)
                vectors = data.get("embeddings")
                if vectors:
                    return [np.asarray(v, dtype=np.float32) for v in vectors]
            except EmbeddingError as exc:
                if "404" not in str(exc):
                    raise
                self._batch_supported = False

        out = []
        for text in batch:
            corpo = {"model": self.model, "prompt": text}
            if opcoes:
                corpo["options"] = opcoes
            data = self._post("/api/embeddings", corpo)
            vector = data.get("embedding")
            if not vector:
                raise EmbeddingError(f"resposta sem embedding: {str(data)[:200]}")
            out.append(np.asarray(vector, dtype=np.float32))
        return out
