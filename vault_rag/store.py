"""Armazenamento e busca hibrida.

SQLite puro da stdlib guarda os chunks, o indice FTS5 e os embeddings como
BLOB. A busca vetorial roda em numpy sobre a matriz carregada na memoria.

Por que nao sqlite-vec: neste vault a matriz inteira ocupa poucos MB, o
produto escalar leva menos de um milissegundo e o desenho deixa de depender
de extensao nativa compilada (o ponto que mais quebra em Python no Windows).
Acima de ~200 mil chunks vale trocar a busca vetorial por um indice ANN;
ate la, forca bruta ganha em simplicidade sem perder nada em latencia.
"""

from __future__ import annotations

import math
import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .meta import query_flags

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS files (
    path       TEXT PRIMARY KEY,
    mtime      REAL NOT NULL,
    size       INTEGER NOT NULL,
    hash       TEXT NOT NULL,
    title      TEXT,
    section    TEXT,
    tags       TEXT,
    links      TEXT,
    n_chunks   INTEGER DEFAULT 0,
    indexed_at REAL,
    note_kind  TEXT,
    note_ts    REAL,
    backlinks  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chunks (
    id           INTEGER PRIMARY KEY,
    path         TEXT NOT NULL,
    ord          INTEGER NOT NULL,
    heading_path TEXT,
    text         TEXT NOT NULL,
    start_line   INTEGER,
    embedding    BLOB,
    embed_hash   TEXT
);

CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    heading_path,
    section,
    path,
    tokenize = "unicode61 remove_diacritics 2"
);
"""

_STOPWORDS = {
    "a", "à", "ao", "aos", "as", "às", "com", "como", "da", "das", "de", "do",
    "dos", "e", "em", "essa", "esse", "esta", "este", "eu", "foi", "há", "isso",
    "já", "mais", "mas", "me", "meu", "minha", "na", "nas", "no", "nos", "num",
    "o", "os", "ou", "para", "pela", "pelo", "por", "qual", "quando", "que",
    "quem", "se", "sem", "ser", "seu", "sua", "são", "só", "tem", "um", "uma",
    "the", "of", "to", "and", "is", "in", "for", "on",
}

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass
class SearchHit:
    chunk_id: int
    path: str
    heading_path: str
    text: str
    start_line: int
    score: float
    vec_rank: int | None
    fts_rank: int | None
    title: str = ""
    section: str = ""
    note_kind: str = "nota"
    note_ts: float | None = None
    backlinks: int = 0
    boost: float = 1.0
    # O boost decomposto: (motivo, multiplicador). O produto e o boost acima.
    fatores: list[tuple[str, float]] = field(default_factory=list)
    mtime: float | None = None
    # Similaridade de cosseno bruta do lado vetorial. E a UNICA medida de
    # relevancia absoluta que existe no pipeline: o RRF so conhece posicao, e
    # posicao num corpus sem resposta ainda produz um primeiro lugar.
    vec_score: float | None = None
    # Preenchido SO quando nenhum candidato passou do piso semantico: guarda a
    # melhor similaridade do vault inteiro para esta pergunta. Presenca deste
    # campo significa "o que segue casou apenas por palavra literal".
    top_sim_global: float | None = None
    # Faixa de confianca: 'alta', 'media' ou 'baixa'. Substitui o corte binario,
    # que nao funciona porque ruido (0.387-0.527) e pergunta legitima com outro
    # vocabulario (0.435-0.607) ocupam a mesma faixa de similaridade. Corte
    # unico ou passa lixo ou nega resposta boa; faixa passa a incerteza adiante.
    confianca: str | None = None
    # Quantos trechos do corpus INTEIRO casaram no lado literal. E o sinal de
    # raridade do termo: 'receita' casa em dezenas e e palavra generica que
    # existe com outro sentido; 'PMTiles' casa em poucos e e identificador.
    fts_total: int | None = None
    # Nota de 0 a 10 dada pelo juiz local quando a faixa saiu media. None
    # significa que o reranker nao rodou: desligado, indisponivel, fora da
    # faixa media, ou alem do rerank_top. E a unica medida do pipeline que
    # leu pergunta e trecho JUNTOS.
    rerank: int | None = None
    context_text: str = ""


def termos_uteis(text: str) -> list[str]:
    """Termos da pergunta que valem busca, sem acento e em minuscula.

    Mesma regra do fts_query: stopword sai, sigla em caixa alta fica.
    Exposto separado para medir COBERTURA - quantos dos termos da pergunta
    aparecem mesmo no trecho devolvido.
    """
    out: list[str] = []
    for raw in _TOKEN_RE.findall(text):
        tok = raw.lower()
        sigla = raw.isupper() and 2 <= len(raw) <= 6
        if len(tok) < 2 or (tok in _STOPWORDS and not sigla):
            continue
        base = unicodedata.normalize("NFKD", tok).encode("ascii", "ignore").decode() or tok
        out.append(base)
    return list(dict.fromkeys(out))


def fts_query(text: str) -> str:
    """Converte linguagem natural em query FTS5 segura.

    Tokens viram OR com prefixo, porque em portugues a flexao muda a cauda da
    palavra (configuracao/configuracoes) e o bm25 ja cuida de ranquear quem
    casa com mais termos.
    """
    tokens = []
    for raw in _TOKEN_RE.findall(text):
        tok = raw.lower()
        # Sigla em caixa alta nao e stopword: neste vault "NAS", "AP", "SE" e
        # "DVR" sao equipamento e protocolo, nao preposicao.
        sigla = raw.isupper() and 2 <= len(raw) <= 6
        if len(tok) < 2 or (tok in _STOPWORDS and not sigla):
            continue
        base = unicodedata.normalize("NFKD", tok).encode("ascii", "ignore").decode() or tok
        if len(base) >= 8:
            # Trunca o prefixo: a flexao portuguesa muda a cauda longe da raiz
            # ("desmontar" x "desmontagem", "configuracao" x "configuracoes"),
            # entao o termo inteiro + '*' nao alcanca a variante.
            tokens.append(f"{base[:7]}*")
        elif len(base) >= 5:
            tokens.append(f"{base}*")
        else:
            tokens.append(base)
    return " OR ".join(dict.fromkeys(tokens))


def fatores_de_boost(row, *, temporal: bool, navegacao: bool, now: float) -> list[tuple[str, float]]:
    """Multiplicadores aplicados ao score do RRF a partir dos metadados da nota.

    Fatores modestos de proposito: o objetivo e desempatar e corrigir vies
    obvio, nao reescrever o ranking por cima da relevancia textual.

    Cada fator vai com o nome do motivo, e nao so o produto, para a
    interface mostrar por que um resultado subiu ou desceu. Fator neutro
    (1.0) nao entra na lista.
    """
    fatores: list[tuple[str, float]] = []
    kind = (row["note_kind"] or "nota") if "note_kind" in row.keys() else "nota"

    # Nota-indice e lista de links: otima para navegar, ruim como resposta.
    if kind == "indice":
        fatores.append(
            ("índice · pergunta de navegação", 1.30) if navegacao
            else ("índice · pergunta factual", 0.65)
        )

    # Data no nome e a data do evento; mtime e so a ultima edicao. Uma spec
    # editada ontem nao e resposta para "o que aconteceu recentemente", entao
    # o mtime entra com um terco do peso.
    ts = row["note_ts"] if "note_ts" in row.keys() else None
    confianca = 1.0
    if not ts and "mtime" in row.keys():
        ts = row["mtime"]
        confianca = 0.33
    if ts:
        # 1.0 para hoje, caindo linearmente ate 0 em dois anos.
        frescor = max(0.0, 1.0 - (now - float(ts)) / (730 * 86400))
        if temporal:
            origem = "data do nome" if confianca == 1.0 else "mtime, peso 1/3"
            fatores.append((f"frescor · {origem}", 1.0 + 0.45 * frescor * confianca))
        elif kind == "diario":
            # Diario e inerentemente datado: o de ontem vale mais que o de
            # um ano atras mesmo sem a pergunta pedir isso.
            fatores.append(("diário · frescor", 1.0 + 0.15 * frescor))

    if "backlinks" in row.keys() and row["backlinks"]:
        # Centralidade: nota citada por muitas outras costuma ser a canonica.
        n = int(row["backlinks"])
        fatores.append((f"backlinks {n}", 1.0 + min(n, 10) * 0.012))

    return [(nome, x) for nome, x in fatores if x != 1.0]


def path_tokens(rel_path: str) -> str:
    """Transforma o caminho em palavras buscaveis.

    "Trabalho/25-NAS-Backup-Arquitetura.md" vira
    "Trabalho 25 NAS Backup Arquitetura". Os nomes de arquivo de um
    vault sao descritivos, entao ignorar o caminho jogava sinal fora.
    """
    base = rel_path[:-3] if rel_path.lower().endswith(".md") else rel_path
    return re.sub(r"[/\\_\-.]+", " ", base).strip()


def to_blob(vec: np.ndarray) -> bytes:
    arr = np.asarray(vec, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm > 0:
        arr = arr / norm
    return arr.tobytes()


class Store:
    def __init__(self, db_path: Path, embed_dim: int = 1024):
        self.db_path = Path(db_path)
        self.embed_dim = embed_dim
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()
        self._matrix: np.ndarray | None = None
        self._ids: np.ndarray | None = None

    def _migrate(self) -> None:
        """Acrescenta colunas novas a um indice criado por versao anterior."""
        existentes = {r["name"] for r in self.conn.execute("PRAGMA table_info(files)")}
        for coluna, ddl in (
            ("note_kind", "TEXT"),
            ("note_ts", "REAL"),
            ("backlinks", "INTEGER DEFAULT 0"),
        ):
            if coluna not in existentes:
                self.conn.execute(f"ALTER TABLE files ADD COLUMN {coluna} {ddl}")

        # A coluna 'path' no FTS chegou depois. Recriar o indice textual e
        # barato (nao mexe nos vetores), entao migra sem pedir reindexacao.
        existentes_chunks = {
            r["name"] for r in self.conn.execute("PRAGMA table_info(chunks)")
        }
        if "embed_hash" not in existentes_chunks:
            self.conn.execute("ALTER TABLE chunks ADD COLUMN embed_hash TEXT")

        colunas_fts = {
            r["name"] for r in self.conn.execute("PRAGMA table_info(chunks_fts)")
        }
        if colunas_fts and "path" not in colunas_fts:
            self.conn.execute("DROP TABLE chunks_fts")
            self.conn.executescript(SCHEMA)
            self.conn.execute(
                "INSERT INTO chunks_fts(rowid, text, heading_path, section, path)"
                " SELECT c.id, c.text, c.heading_path,"
                "        COALESCE(f.section, ''), c.path"
                " FROM chunks c LEFT JOIN files f ON f.path = c.path"
            )
            self.conn.executemany(
                "UPDATE chunks_fts SET path = ? WHERE rowid = ?",
                [
                    (path_tokens(r["path"]), r["id"])
                    for r in self.conn.execute("SELECT id, path FROM chunks")
                ],
            )

    # ------------------------------------------------------------------ meta
    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    # ----------------------------------------------------------------- files
    def file_state(self) -> dict[str, tuple[float, int, str]]:
        rows = self.conn.execute("SELECT path, mtime, size, hash FROM files").fetchall()
        return {r["path"]: (r["mtime"], r["size"], r["hash"]) for r in rows}

    def delete_file(self, path: str) -> None:
        ids = [r["id"] for r in self.conn.execute("SELECT id FROM chunks WHERE path=?", (path,))]
        if ids:
            self.conn.executemany("DELETE FROM chunks_fts WHERE rowid=?", [(i,) for i in ids])
        self.conn.execute("DELETE FROM chunks WHERE path=?", (path,))
        self.conn.execute("DELETE FROM files WHERE path=?", (path,))
        self._matrix = None

    def upsert_file(
        self,
        *,
        path: str,
        mtime: float,
        size: int,
        file_hash: str,
        title: str,
        section: str,
        tags: list[str],
        links: list[str],
        chunks: list[tuple[int, str, str, int]],
        embeddings: list[np.ndarray],
        indexed_at: float,
        embed_hashes: list[str] | None = None,
        note_kind: str = "nota",
        note_ts: float | None = None,
    ) -> None:
        """Regrava a nota inteira: apaga o que havia e insere os chunks novos."""
        self.delete_file(path)
        self.conn.execute(
            "INSERT INTO files(path,mtime,size,hash,title,section,tags,links,"
            "n_chunks,indexed_at,note_kind,note_ts)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (path, mtime, size, file_hash, title, section,
             " ".join(tags), "\n".join(links), len(chunks), indexed_at,
             note_kind, note_ts),
        )
        hashes = embed_hashes or [None] * len(chunks)
        for (ordinal, heading_path, text, start_line), vec, h in zip(
            chunks, embeddings, hashes
        ):
            cur = self.conn.execute(
                "INSERT INTO chunks(path,ord,heading_path,text,start_line,embedding,embed_hash)"
                " VALUES(?,?,?,?,?,?,?)",
                (path, ordinal, heading_path, text, start_line, to_blob(vec), h),
            )
            self.conn.execute(
                "INSERT INTO chunks_fts(rowid,text,heading_path,section,path)"
                " VALUES(?,?,?,?,?)",
                (cur.lastrowid, text, heading_path, section, path_tokens(path)),
            )
        self._matrix = None

    def commit(self) -> None:
        self.conn.commit()

    # ---------------------------------------------------------------- vetores
    def _load_matrix(self) -> tuple[np.ndarray, np.ndarray]:
        if self._matrix is not None and self._ids is not None:
            return self._matrix, self._ids
        rows = self.conn.execute(
            "SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL ORDER BY id"
        ).fetchall()
        if not rows:
            self._ids = np.zeros(0, dtype=np.int64)
            self._matrix = np.zeros((0, self.embed_dim), dtype=np.float32)
            return self._matrix, self._ids
        self._ids = np.array([r["id"] for r in rows], dtype=np.int64)
        self._matrix = np.vstack(
            [np.frombuffer(r["embedding"], dtype=np.float32) for r in rows]
        )
        return self._matrix, self._ids

    # ----------------------------------------------------------------- busca
    def contar_chunks(self) -> int:
        """Total de trechos no indice. Serve para medir raridade de termo."""
        row = self.conn.execute("SELECT COUNT(*) c FROM chunks").fetchone()
        return int(row["c"]) if row else 0

    def similaridade_maxima(self, query_vec) -> float:
        """Maior cosseno entre a pergunta e qualquer trecho do indice.

        Serve para calibrar o piso: e este numero, e nao a posicao no ranking,
        que distingue "o vault responde isso" de "o vault nao tem nada disso".
        """
        matrix, ids = self._load_matrix()
        if matrix.size == 0 or query_vec is None:
            return 0.0
        q = np.asarray(query_vec, dtype=np.float32)
        norm = float(np.linalg.norm(q))
        if norm > 0:
            q = q / norm
        scores = matrix @ q
        return float(np.max(scores)) if scores.size else 0.0

    def search(
        self,
        query: str,
        query_vec: np.ndarray | None = None,
        *,
        top_k: int = 6,
        candidates: int = 40,
        rrf_k: int = 60,
        section: str | None = None,
        path_prefix: str | None = None,
        max_per_file: int = 2,
        min_score: float = 0.3,
        use_metadata: bool = True,
    ) -> list[SearchHit]:
        # Query sem nenhum termo util (vazia, ou so preposicao e artigo) nao e
        # uma busca: sem isso, o lado vetorial ainda devolveria "os menos
        # distantes", que e ruido puro.
        match = fts_query(query or "")
        if not match:
            return []

        vec_ranked: list[int] = []
        vec_sim: dict[int, float] = {}
        fts_total: int | None = None
        fts_ranked: list[int] = []

        allowed: set[int] | None = None
        if section or path_prefix:
            prefix = path_prefix or section
            rows = self.conn.execute(
                "SELECT id FROM chunks WHERE path LIKE ?", (f"{prefix}%",)
            ).fetchall()
            allowed = {r["id"] for r in rows}
            if not allowed:
                return []

        if query_vec is not None:
            matrix, ids = self._load_matrix()
            if len(ids):
                q = np.asarray(query_vec, dtype=np.float32).ravel()
                norm = float(np.linalg.norm(q))
                if norm > 0:
                    q = q / norm
                scores = matrix @ q
                if allowed is not None:
                    mask = np.isin(ids, np.fromiter(allowed, dtype=np.int64))
                    scores = np.where(mask, scores, -np.inf)
                take = min(candidates, len(ids))
                idx = np.argpartition(-scores, take - 1)[:take]
                idx = idx[np.argsort(-scores[idx])]
                # Piso de similaridade: sem ele, uma consulta sem nada a ver
                # com o vault ainda devolve os "menos distantes", que e ruido.
                vec_ranked = [
                    int(ids[i])
                    for i in idx
                    if np.isfinite(scores[i]) and scores[i] >= min_score
                ]
                # Guardar o valor, nao so a ordem: e o que permite dizer
                # "nao achei nada" em vez de devolver o menos distante.
                vec_sim = {
                    int(ids[i]): float(scores[i])
                    for i in idx
                    if np.isfinite(scores[i])
                }

        if match:
            try:
                rows = self.conn.execute(
                    "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? "
                    "ORDER BY bm25(chunks_fts, 1.0, 2.0, 0.5, 1.5) LIMIT ?",
                    (match, candidates * 3 if allowed else candidates),
                ).fetchall()
                fts_ranked = [r["rowid"] for r in rows]
                try:
                    fts_total = int(
                        self.conn.execute(
                            "SELECT COUNT(*) c FROM chunks_fts WHERE chunks_fts MATCH ?",
                            (match,),
                        ).fetchone()["c"]
                    )
                except sqlite3.OperationalError:
                    fts_total = None
                if allowed is not None:
                    fts_ranked = [i for i in fts_ranked if i in allowed][:candidates]
            except sqlite3.OperationalError:
                fts_ranked = []

        fused: dict[int, float] = {}
        vec_pos = {cid: i for i, cid in enumerate(vec_ranked)}
        fts_pos = {cid: i for i, cid in enumerate(fts_ranked)}
        for cid, pos in vec_pos.items():
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (rrf_k + pos + 1)
        for cid, pos in fts_pos.items():
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (rrf_k + pos + 1)

        if not fused:
            return []

        placeholders = ",".join("?" * len(fused))
        rows = self.conn.execute(
            f"SELECT c.id, c.path, c.ord, c.heading_path, c.text, c.start_line,"
            f" f.title, f.section, f.note_kind, f.note_ts, f.backlinks, f.mtime"
            f" FROM chunks c LEFT JOIN files f ON f.path=c.path"
            f" WHERE c.id IN ({placeholders})",
            list(fused),
        ).fetchall()
        by_id = {r["id"]: r for r in rows}

        # Reordena aplicando os metadados por cima do score textual.
        boosts: dict[int, float] = {}
        fatores: dict[int, list[tuple[str, float]]] = {}
        if use_metadata:
            temporal, navegacao = query_flags(query)
            now = time.time()
            for cid in list(fused):
                row = by_id.get(cid)
                if row is None:
                    continue
                fatores[cid] = fatores_de_boost(
                    row, temporal=temporal, navegacao=navegacao, now=now
                )
                peso = math.prod(x for _, x in fatores[cid])
                boosts[cid] = peso
                fused[cid] *= peso

        ranked = sorted(fused.items(), key=lambda kv: -kv[1])

        # Diversidade: uma nota longa e relevante domina o topo e esconde as
        # outras. Limita chunks por arquivo e so afrouxa se faltar resultado.
        best: list[tuple[int, float]] = []
        overflow: list[tuple[int, float]] = []
        per_file: dict[str, int] = {}
        for cid, score in ranked:
            row = by_id.get(cid)
            if row is None:
                continue
            path = row["path"]
            if max_per_file and per_file.get(path, 0) >= max_per_file:
                overflow.append((cid, score))
                continue
            per_file[path] = per_file.get(path, 0) + 1
            best.append((cid, score))
            if len(best) >= top_k:
                break
        if len(best) < top_k:
            best += overflow[: top_k - len(best)]

        hits = []
        for cid, score in best:
            row = by_id.get(cid)
            if row is None:
                continue
            hits.append(
                SearchHit(
                    chunk_id=cid,
                    path=row["path"],
                    heading_path=row["heading_path"] or "",
                    text=row["text"],
                    start_line=row["start_line"] or 1,
                    score=round(score, 6),
                    vec_rank=vec_pos.get(cid),
                    fts_rank=fts_pos.get(cid),
                    title=row["title"] or "",
                    section=row["section"] or "",
                    note_kind=row["note_kind"] or "nota",
                    note_ts=row["note_ts"],
                    backlinks=row["backlinks"] or 0,
                    boost=round(boosts.get(cid, 1.0), 3),
                    fatores=[(nome, round(x, 3)) for nome, x in fatores.get(cid, [])],
                    mtime=row["mtime"],
                    vec_score=(
                        round(vec_sim[cid], 4) if cid in vec_sim else None
                    ),
                    fts_total=fts_total,
                )
            )
        return hits

    def vetores_existentes(self, path: str) -> dict[str, np.ndarray]:
        """Vetores ja calculados para esta nota, indexados pelo hash do texto
        que foi embeddado.

        Editar uma linha muda um ou dois chunks, nao a nota inteira. Sem isso,
        uma correcao de typo em nota grande custaria minutos de Ollama.
        """
        rows = self.conn.execute(
            "SELECT embed_hash, embedding FROM chunks"
            " WHERE path=? AND embed_hash IS NOT NULL AND embedding IS NOT NULL",
            (path,),
        ).fetchall()
        return {
            r["embed_hash"]: np.frombuffer(r["embedding"], dtype=np.float32)
            for r in rows
        }

    # ----------------------------------------------- small-to-big / backlinks
    def expand(self, hit: SearchHit, max_chars: int = 4000) -> str:
        """Devolve a secao inteira em volta do chunk que casou.

        Busca e resposta querem tamanhos opostos: a busca acerta mais com
        trecho curto e especifico, a resposta precisa de contexto. Entao o
        vetor continua sendo o do chunk pequeno, mas o que volta e a secao
        completa - os chunks vizinhos que compartilham a mesma trilha de
        headings, em ordem.
        """
        raiz = hit.heading_path or ""
        if raiz:
            rows = self.conn.execute(
                "SELECT ord, text FROM chunks WHERE path=?"
                " AND (heading_path = ? OR heading_path LIKE ?)"
                " ORDER BY ord",
                (hit.path, raiz, raiz + " > %"),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT ord, text FROM chunks WHERE path=? ORDER BY ord LIMIT 3",
                (hit.path,),
            ).fetchall()

        if not rows:
            return hit.text

        partes: list[str] = []
        total = 0
        # O chunk que casou entra sempre; os vizinhos entram enquanto couber.
        ordens = [r["ord"] for r in rows]
        textos = {r["ord"]: r["text"] for r in rows}
        try:
            centro = ordens.index(
                next(o for o in ordens if textos[o] == hit.text)
            )
        except StopIteration:
            centro = 0

        escolhidos = [ordens[centro]]
        total = len(textos[ordens[centro]])
        esquerda, direita = centro - 1, centro + 1
        while esquerda >= 0 or direita < len(ordens):
            avancou = False
            if direita < len(ordens):
                t = textos[ordens[direita]]
                if total + len(t) <= max_chars:
                    escolhidos.append(ordens[direita])
                    total += len(t)
                    direita += 1
                    avancou = True
            if esquerda >= 0:
                t = textos[ordens[esquerda]]
                if total + len(t) <= max_chars:
                    escolhidos.insert(0, ordens[esquerda])
                    total += len(t)
                    esquerda -= 1
                    avancou = True
            if not avancou:
                break

        for o in sorted(escolhidos):
            partes.append(textos[o])
        return "\n\n".join(partes)

    def compute_backlinks(self, resolve) -> int:
        """Conta quantas notas apontam para cada nota.

        Roda depois da indexacao, quando todos os caminhos ja sao conhecidos -
        um link para nota que ainda nao foi indexada nao resolveria antes.
        """
        rows = self.conn.execute("SELECT path, links FROM files").fetchall()
        by_path, by_stem = self._mapas_de_link(rows)

        contagem: dict[str, int] = {}
        for r in rows:
            if not r["links"]:
                continue
            vistos = set()
            for alvo in r["links"].split("\n"):
                destino = resolve(alvo, by_path, by_stem)
                # Autolink e link repetido na mesma nota contam uma vez so.
                if destino and destino != r["path"] and destino not in vistos:
                    vistos.add(destino)
                    contagem[destino] = contagem.get(destino, 0) + 1

        self.conn.execute("UPDATE files SET backlinks = 0")
        self.conn.executemany(
            "UPDATE files SET backlinks = ? WHERE path = ?",
            [(n, p) for p, n in contagem.items()],
        )
        self.conn.commit()
        return len(contagem)

    @staticmethod
    def _mapas_de_link(rows) -> tuple[dict[str, str], dict[str, list[str]]]:
        """Caminho e nome curto de cada nota, para resolver wikilinks."""
        by_path = {r["path"]: r["path"] for r in rows}
        by_path.update({r["path"][:-3]: r["path"] for r in rows if r["path"].endswith(".md")})
        by_stem: dict[str, list[str]] = {}
        for r in rows:
            stem = r["path"].rsplit("/", 1)[-1].lower()
            by_stem.setdefault(stem[:-3] if stem.endswith(".md") else stem, []).append(r["path"])
        return by_path, by_stem

    def quem_cita(self, path: str, resolve) -> list[str]:
        """Notas com wikilink que resolve para esta. Mesma regra dos backlinks."""
        rows = self.conn.execute("SELECT path, links FROM files").fetchall()
        by_path, by_stem = self._mapas_de_link(rows)
        return sorted(
            r["path"]
            for r in rows
            if r["path"] != path
            and r["links"]
            and any(resolve(alvo, by_path, by_stem) == path for alvo in r["links"].split("\n"))
        )

    def trechos(self, path: str) -> list[dict]:
        """Os trechos indexados de uma nota, na ordem em que aparecem."""
        rows = self.conn.execute(
            "SELECT id, ord, heading_path, start_line, length(text) chars, embed_hash"
            " FROM chunks WHERE path = ? ORDER BY ord",
            (path,),
        ).fetchall()
        return [dict(r) for r in rows]

    def arquivo(self, path: str) -> dict | None:
        row = self.conn.execute(
            "SELECT path, title, section, note_kind, note_ts, mtime, size, backlinks,"
            " n_chunks, indexed_at FROM files WHERE path = ?",
            (path,),
        ).fetchone()
        return dict(row) if row else None

    def notas(self, *, secao: str | None = None, limite: int = 50) -> list[dict]:
        """Notas indexadas, da editada mais recentemente para a mais antiga."""
        sql = ("SELECT path, title, section, note_kind, note_ts, mtime, n_chunks, backlinks"
               " FROM files")
        args: list = []
        if secao:
            sql += " WHERE section = ?"
            args.append(secao)
        sql += " ORDER BY mtime DESC LIMIT ?"
        args.append(limite)
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    # ----------------------------------------------------------------- stats
    def stats(self) -> dict:
        n_files = self.conn.execute("SELECT COUNT(*) c FROM files").fetchone()["c"]
        n_chunks = self.conn.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
        sections = self.conn.execute(
            "SELECT section, COUNT(*) c FROM files GROUP BY section ORDER BY c DESC"
        ).fetchall()
        size = self.db_path.stat().st_size if self.db_path.exists() else 0
        return {
            "files": n_files,
            "chunks": n_chunks,
            "db_mb": round(size / 1e6, 2),
            "model": self.get_meta("model"),
            "embed_dim": self.get_meta("embed_dim"),
            "last_index": self.get_meta("last_index"),
            "sections": [{"section": r["section"], "files": r["c"]} for r in sections],
        }

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()
