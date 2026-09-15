"""Varredura e indexacao incremental do vault."""

from __future__ import annotations

import fnmatch
import hashlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .chunker import chunk_markdown
from .config import Config
from .embed import OllamaEmbedder
from .meta import note_date, note_kind, resolve_link
from .store import Store


@dataclass
class IndexReport:
    scanned: int = 0
    indexed: int = 0
    skipped: int = 0
    removed: int = 0
    chunks: int = 0
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0

    def as_text(self) -> str:
        line = (
            f"{self.indexed} nota(s) indexada(s), {self.skipped} sem mudanca, "
            f"{self.removed} removida(s), {self.chunks} chunk(s) gravado(s) "
            f"em {self.seconds:.1f}s"
        )
        if self.errors:
            line += f"\n{len(self.errors)} erro(s):\n  " + "\n  ".join(self.errors[:10])
        return line


def _is_ignored(rel: Path, cfg: Config) -> bool:
    parts = rel.parts
    for part in parts[:-1]:
        if part in cfg.ignore_dirs or part.startswith("."):
            return True
    name = parts[-1]
    for pattern in cfg.ignore_globs:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def iter_notes(cfg: Config):
    for path in sorted(cfg.vault.rglob("*.md")):
        if not path.is_file():
            continue
        rel = path.relative_to(cfg.vault)
        if _is_ignored(rel, cfg):
            continue
        yield path, rel.as_posix()


def _section_of(rel_posix: str) -> str:
    head, _, tail = rel_posix.partition("/")
    return head if tail else ""


def _embed_text(
    rel_posix: str, heading_path: str, text: str, title: str = "", lead: str = ""
) -> str:
    """Monta o texto que vai para o modelo.

    O trecho sozinho nao diz de onde veio. Caminho, titulo, trilha de headings
    e o lead da nota dao esse contexto sem custo nenhum de inferencia.
    """
    linhas = [rel_posix]
    if title:
        linhas.append(title)
    if heading_path:
        linhas.append(heading_path)
    # O lead so entra se ainda nao estiver no proprio trecho (primeiro chunk).
    if lead and lead[:60] not in text:
        linhas.append(lead)
    return "\n".join(linhas) + f"\n\n{text}"


def embed_hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8", "replace")).hexdigest()[:32]


def _prepare(path, rel: str, stat, cfg: Config, embedder: OllamaEmbedder, cache=None):
    """Le, corta e embedda uma nota. Roda em thread: a parte cara e esperar
    o Ollama responder, e isso libera o GIL."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        digest = hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()
        note = chunk_markdown(
            raw,
            target_chars=cfg.target_chars,
            hard_max_chars=cfg.hard_max_chars,
            min_chars=cfg.min_chars,
        )
        if not note.chunks:
            return rel, stat, digest, note, [], [], None

        payload = [
            _embed_text(rel, c.heading_path, c.text, note.title, note.lead)
            for c in note.chunks
        ]
        hashes = [embed_hash(t) for t in payload]

        # Reaproveita o vetor dos chunks cujo texto nao mudou. Numa edicao de
        # uma linha, so um ou dois chunks precisam ir ao Ollama.
        cache = cache or {}
        faltando = [i for i, h in enumerate(hashes) if h not in cache]
        novos = embedder.embed([payload[i] for i in faltando]) if faltando else []
        vetores: list = [cache.get(h) for h in hashes]
        for i, vec in zip(faltando, novos):
            vetores[i] = vec

        return rel, stat, digest, note, vetores, hashes, None
    except Exception as exc:
        # Erro e dado de retorno, nao excecao: uma nota que falha nao pode
        # levar junto as outras do mesmo lote, que ja custaram embedding.
        return rel, stat, None, None, None, None, str(exc)


def index_vault(
    cfg: Config,
    *,
    force: bool = False,
    verbose: bool = True,
    progress=None,
) -> IndexReport:
    started = time.time()
    report = IndexReport()
    store = Store(cfg.db_path, cfg.embed_dim)
    embedder = OllamaEmbedder(
        cfg.ollama_url, cfg.model, cfg.request_timeout, cfg.batch_size,
        num_thread=cfg.num_thread,
    )
    embedder.check()

    stored_model = store.get_meta("model")
    if stored_model and stored_model != cfg.model:
        if verbose:
            print(
                f"Modelo mudou ({stored_model} -> {cfg.model}): reindexando tudo.",
                file=sys.stderr,
            )
        force = True

    known = store.file_state()
    seen: set[str] = set()

    try:
        # Passo 1 (barato, sem rede): decide o que precisa reprocessar.
        pendentes: list = []
        for path, rel in iter_notes(cfg):
            report.scanned += 1
            seen.add(rel)
            try:
                stat = path.stat()
            except OSError as exc:
                report.errors.append(f"{rel}: {exc}")
                continue

            previous = known.get(rel)
            if not force and previous and previous[0] == stat.st_mtime and previous[1] == stat.st_size:
                report.skipped += 1
                continue
            pendentes.append((path, rel, stat))

        total = len(pendentes)
        if verbose and total:
            print(
                f"{total} nota(s) para processar"
                + (f" (com {cfg.parallel} em paralelo)" if cfg.parallel > 1 else ""),
                file=sys.stderr,
            )

        # Passo 2 (caro): ler/cortar/embeddar em paralelo, gravar em serie.
        # O SQLite fica com uma conexao so, no thread principal; as threads
        # apenas esperam o Ollama, que e onde o tempo vai.
        caches: dict = {}

        def resultados_em_ordem(itens):
            if cfg.parallel <= 1:
                for path, rel, stat in itens:
                    yield _prepare(path, rel, stat, cfg, embedder, caches.get(rel))
                return
            with ThreadPoolExecutor(max_workers=cfg.parallel) as pool:
                yield from pool.map(
                    lambda it: _prepare(
                        it[0], it[1], it[2], cfg, embedder, caches.get(it[1])
                    ),
                    itens,
                )

        # Bloco grande so como teto de memoria; o que importa e que a gravacao
        # acontece assim que cada nota fica pronta - da progresso visivel e
        # nada se perde se o processo for interrompido no meio.
        bloco = 256
        for inicio in range(0, total, bloco):
            fatia = pendentes[inicio : inicio + bloco]
            caches = {
                rel: store.vetores_existentes(rel) for _, rel, _ in fatia
            } if not force else {}

            for (rel, stat, digest, note, vectors, hashes, erro), (path, _, _) in zip(
                resultados_em_ordem(fatia), fatia
            ):
                if erro:
                    report.errors.append(f"{rel}: {erro}")
                    continue
                previous = known.get(rel)
                if not force and previous and previous[2] == digest:
                    store.conn.execute(
                        "UPDATE files SET mtime=?, size=? WHERE path=?",
                        (stat.st_mtime, stat.st_size, rel),
                    )
                    report.skipped += 1
                    continue
                if not note.chunks:
                    # Nota vazia, ou so com frontmatter, nao rende trecho algum.
                    # Ainda assim precisa ficar registrada: sem registro em
                    # files, stale_files a devolve como pendente em TODA
                    # passagem seguinte, e essa pendencia eterna acaba
                    # escondendo as pendencias de verdade.
                    store.upsert_file(
                        path=rel,
                        note_kind=note_kind(rel),
                        note_ts=note_date(rel),
                        mtime=stat.st_mtime,
                        size=stat.st_size,
                        file_hash=digest,
                        title=note.title or path.stem,
                        section=_section_of(rel),
                        tags=note.tags,
                        links=note.links,
                        chunks=[],
                        embeddings=[],
                        embed_hashes=[],
                        indexed_at=time.time(),
                    )
                    store.commit()
                    report.skipped += 1
                    continue

                store.upsert_file(
                    path=rel,
                    note_kind=note_kind(rel),
                    note_ts=note_date(rel),
                    mtime=stat.st_mtime,
                    size=stat.st_size,
                    file_hash=digest,
                    title=note.title or path.stem,
                    section=_section_of(rel),
                    tags=note.tags,
                    links=note.links,
                    chunks=[(c.ord, c.heading_path, c.text, c.start_line) for c in note.chunks],
                    embeddings=vectors,
                    embed_hashes=hashes,
                    indexed_at=time.time(),
                )
                store.commit()
                report.indexed += 1
                report.chunks += len(note.chunks)

                if progress:
                    progress(rel, report)
                elif verbose:
                    print(
                        f"  [{report.indexed}/{total}] {rel} ({len(note.chunks)} chunks)",
                        file=sys.stderr,
                    )

        for rel in set(known) - seen:
            store.delete_file(rel)
            report.removed += 1

        if vectors_dim := store.conn.execute(
            "SELECT length(embedding)/4 d FROM chunks LIMIT 1"
        ).fetchone():
            if vectors_dim["d"]:
                store.set_meta("embed_dim", str(vectors_dim["d"]))
        alvos = store.compute_backlinks(resolve_link)
        if verbose and alvos:
            print(f"  backlinks: {alvos} nota(s) referenciada(s)", file=sys.stderr)
        store.set_meta("model", cfg.model)
        store.set_meta("vault", str(cfg.vault))
        store.set_meta("last_index", time.strftime("%Y-%m-%d %H:%M:%S"))
        store.commit()
    finally:
        store.close()

    report.seconds = time.time() - started
    return report


def reindex_one(cfg: Config, rel: str) -> int:
    """Reindexa uma unica nota. Usado logo apos escrever nela.

    Reaproveita os vetores dos trechos que nao mudaram, entao uma edicao
    pequena custa uma chamada ao Ollama, nao a nota inteira.
    """
    caminho = cfg.vault / rel
    store = Store(cfg.db_path, cfg.embed_dim)
    try:
        if not caminho.is_file():
            store.delete_file(rel)
            store.commit()
            return 0

        embedder = OllamaEmbedder(
            cfg.ollama_url, cfg.model, cfg.request_timeout, cfg.batch_size,
            num_thread=cfg.num_thread,
        )
        cache = store.vetores_existentes(rel)
        stat = caminho.stat()
        _, _, digest, note, vetores, hashes, erro = _prepare(
            caminho, rel, stat, cfg, embedder, cache
        )
        if erro:
            raise RuntimeError(erro)
        if not note or not note.chunks:
            store.delete_file(rel)
            store.commit()
            return 0

        store.upsert_file(
            path=rel,
            note_kind=note_kind(rel),
            note_ts=note_date(rel),
            mtime=stat.st_mtime,
            size=stat.st_size,
            file_hash=digest,
            title=note.title or caminho.stem,
            section=_section_of(rel),
            tags=note.tags,
            links=note.links,
            chunks=[(c.ord, c.heading_path, c.text, c.start_line) for c in note.chunks],
            embeddings=vetores,
            embed_hashes=hashes,
            indexed_at=time.time(),
        )
        store.commit()
        return len(note.chunks)
    finally:
        store.close()


def stale_files(cfg: Config) -> list[str]:
    """Notas que mudaram no disco desde a ultima indexacao."""
    store = Store(cfg.db_path, cfg.embed_dim)
    try:
        known = store.file_state()
        out = []
        seen = set()
        for path, rel in iter_notes(cfg):
            seen.add(rel)
            previous = known.get(rel)
            try:
                stat = path.stat()
            except OSError:
                continue
            if not previous or previous[0] != stat.st_mtime or previous[1] != stat.st_size:
                out.append(rel)
        out += sorted(set(known) - seen)
        return out
    finally:
        store.close()
