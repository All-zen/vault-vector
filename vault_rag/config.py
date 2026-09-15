"""Configuracao do vault-rag.

A config vive num TOML ao lado do pacote (ou apontado por VAULT_RAG_CONFIG).
Tudo tem default razoavel: sem arquivo, o programa ainda roda.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # Python 3.9/3.10, via a dependencia 'tomli'
from pathlib import Path

DEFAULT_IGNORE_DIRS = [
    ".obsidian",
    ".git",
    ".trash",
    "node_modules",
    "__pycache__",
    "_to_delete",
    "_arquivo",
    "_historico",
    "_assets",
    "Backups",
    "_tools",
]

DEFAULT_IGNORE_GLOBS = [
    "*.bak-*",
    "*.tmp.md",
    "_backup-*",
    "*.excalidraw.md",
]


@dataclass
class Config:
    vault: Path
    db_path: Path
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "bge-m3"
    embed_dim: int = 1024
    batch_size: int = 16
    parallel: int = 2
    num_thread: int = 0
    request_timeout: float = 300.0

    # chunking
    target_chars: int = 2400
    hard_max_chars: int = 6000
    min_chars: int = 600

    # busca
    rrf_k: int = 60
    candidates: int = 40
    max_per_file: int = 2
    min_score: float = 0.3
    sim_confiavel: float = 0.60
    sim_duvidoso: float = 0.43

    # Reranker. Vazio = desligado, e a busca se comporta como antes.
    # So atua na faixa media: a alta ja e confiavel e a baixa ja diz nao.
    rerank_model: str = ""
    # Corte do trecho enviado ao juiz. 350 rebaixou uma resposta certa de 6
    # para 3 na medicao de 15/09; 600 manteve a nota sem custo perceptivel.
    rerank_chars: int = 600
    # Quantos trechos julgar. Em CPU pura cada um custa 0,3 a 1,7 s.
    rerank_top: int = 5
    rerank_timeout: float = 30.0
    # MEDIA das notas que promove a faixa media para alta, e media que a
    # rebaixa para baixa. Medido em 15/09, 8 legitimas contra 8 de ruido:
    # media de legitima vai de 1,4 a 6,4 e media de ruido vai de 1,0 a 3,2.
    # O maximo NAO separa (7 de 8 de cada lado tiram >= 6), por isso e media.
    rerank_promove: float = 3.4
    rerank_rebaixa: float = 1.2
    # Descricao do vault para o modelo. Vazio = gerada lendo o indice.
    instructions: str = ""
    expand_chars: int = 4000

    ignore_dirs: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE_DIRS))
    ignore_globs: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE_GLOBS))

    @property
    def package_dir(self) -> Path:
        return Path(__file__).resolve().parent


def _config_path() -> Path:
    env = os.environ.get("VAULT_RAG_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent.parent / "config.toml"


def load_config(overrides: dict | None = None) -> Config:
    path = _config_path()
    raw: dict = {}
    if path.is_file():
        with path.open("rb") as fh:
            raw = tomllib.load(fh)

    vault = raw.get("vault") or os.environ.get("VAULT_RAG_VAULT")
    if not vault:
        raise SystemExit(
            f"Vault nao configurado. Crie {path} com a linha:\n"
            '  vault = "C:/Memorias"\n'
            "ou defina a variavel de ambiente VAULT_RAG_VAULT."
        )

    db = raw.get("db_path") or os.environ.get("VAULT_RAG_DB")
    db_path = Path(db).expanduser() if db else path.parent / "index.db"

    cfg = Config(vault=Path(vault).expanduser(), db_path=db_path)

    for key in (
        "ollama_url",
        "model",
        "embed_dim",
        "batch_size",
        "parallel",
        "num_thread",
        "request_timeout",
        "target_chars",
        "hard_max_chars",
        "min_chars",
        "rrf_k",
        "candidates",
        "max_per_file",
        "min_score",
        "sim_confiavel",
        "sim_duvidoso",
        "rerank_model",
        "rerank_chars",
        "rerank_top",
        "rerank_timeout",
        "rerank_promove",
        "rerank_rebaixa",
        "instructions",
        "expand_chars",
    ):
        if key in raw:
            setattr(cfg, key, raw[key])

    if "ignore_dirs" in raw:
        cfg.ignore_dirs = list(raw["ignore_dirs"])
    if "extra_ignore_dirs" in raw:
        cfg.ignore_dirs += list(raw["extra_ignore_dirs"])
    if "ignore_globs" in raw:
        cfg.ignore_globs = list(raw["ignore_globs"])

    env_url = os.environ.get("OLLAMA_HOST")
    if env_url and "ollama_url" not in raw:
        cfg.ollama_url = env_url if env_url.startswith("http") else f"http://{env_url}"

    for key, value in (overrides or {}).items():
        if value is not None:
            setattr(cfg, key, value)

    if not cfg.vault.is_dir():
        raise SystemExit(f"Vault nao encontrado: {cfg.vault}")

    return cfg
