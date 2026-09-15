"""Funcoes de alto nivel compartilhadas pelo CLI e pelo MCP server."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .embed import EmbeddingError, OllamaEmbedder
from .indexer import stale_files
from .store import SearchHit, Store

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def _safe_path(cfg: Config, rel: str) -> Path:
    """Resolve um caminho relativo garantindo que fica dentro do vault."""
    candidate = (cfg.vault / rel.replace("\\", "/")).resolve()
    vault = cfg.vault.resolve()
    if not str(candidate).startswith(str(vault)):
        raise ValueError(f"caminho fora do vault: {rel}")
    return candidate


def cobertura_literal(query: str, texto: str) -> float:
    """Fracao dos termos da pergunta que aparecem mesmo no trecho devolvido.

    Existe para separar duas coisas que a raridade sozinha confunde, porque
    ambas casam em pouquissimos trechos:

      - termo ESPECIFICO do dominio ("PMTiles"): aparece inteiro no trecho,
        cobertura 1.0 - o casamento literal e evidencia de verdade;
      - termo AUSENTE do dominio ("podar roseiras no inverno"): so um termo
        marginal casou por acaso, cobertura ~0.33 - nao e evidencia nenhuma.

    Medido em 15/09: sem isto, "podar roseiras no inverno" (similaridade
    0.414) subia para faixa alta e saia sem ressalva alguma.
    """
    from .store import termos_uteis

    termos = termos_uteis(query)
    if not termos:
        return 0.0
    alvo = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return sum(1 for t in termos if t in alvo) / len(termos)


def faixa_de_confianca(
    melhor_sim: float, termo_raro: bool, confiavel: float = 0.60, duvidoso: float = 0.43
) -> str:
    """Classifica o quanto o resultado merece credito: alta, media ou baixa.

    Medido em 15/09 neste vault: ruido ocupa 0.387-0.527 e pergunta legitima
    escrita com vocabulario diferente do das notas ocupa 0.435-0.607. As duas
    populacoes se SOBREPOEM, entao nenhum corte binario separa - qualquer
    limiar unico ou deixa passar lixo ou nega resposta boa. A saida entao
    gradua e passa a incerteza adiante, em vez de decidir sozinha.

    Termo raro casando no literal sobe direto para alta: uma palavra isolada
    contra um paragrafo tem cosseno baixo por construcao, e isso e busca por
    identificador funcionando, nao duvida.
    """
    if termo_raro or melhor_sim >= confiavel:
        return "alta"
    if melhor_sim >= duvidoso:
        return "media"
    return "baixa"


def termo_e_raro(total_fts: int | None, total_chunks: int, fracao: float = 0.005) -> bool:
    """O termo casou em pouca coisa do corpus, entao e identificador, nao palavra.

    Raridade e FRACAO, nunca contagem: casar em 3 trechos de 4.000 e um
    hostname; casar em 3 de 7 e uma palavra comum daquele vault.

    Serve para nao marcar como duvidosa uma busca por identificador exato
    (MAC, hostname, "PMTiles"), que tem cosseno baixo por construcao - uma
    palavra isolada comparada com um paragrafo inteiro - mas cujo casamento
    literal e evidencia forte por si so.
    """
    if total_fts is None or total_chunks <= 0:
        return False
    return (total_fts / total_chunks) <= fracao


def search(
    cfg: Config,
    query: str,
    *,
    top_k: int = 6,
    section: str | None = None,
    lexical_only: bool = False,
    max_per_file: int = 2,
    expand: bool = True,
) -> list[SearchHit]:
    store = Store(cfg.db_path, cfg.embed_dim)
    try:
        query_vec = None
        if not lexical_only:
            embedder = OllamaEmbedder(
                cfg.ollama_url, cfg.model, cfg.request_timeout, cfg.batch_size
            )
            try:
                query_vec = embedder.embed_one(query)
            except EmbeddingError:
                query_vec = None  # cai para busca puramente lexica
        hits = store.search(
            query,
            query_vec,
            top_k=top_k,
            candidates=cfg.candidates,
            rrf_k=cfg.rrf_k,
            section=section,
            max_per_file=max_per_file,
            min_score=cfg.min_score,
        )
        # Piso calibrado corta o lado vetorial, mas o FTS continua passando.
        # Casamento literal SEM o vetorial concordar e o modo de falha - PORQUE
        # a palavra e generica e existe no vault com outro sentido ("receita").
        # Quando o termo e RARO no corpus ("PMTiles", um MAC, um hostname), o
        # casamento literal e evidencia forte por si so, e o cosseno baixo e
        # apenas o efeito de comparar uma palavra com um paragrafo inteiro.
        # Avisar nesse caso seria falso negativo - foi o que aconteceu no
        # primeiro teste de controle, em 15/09.
        if query_vec is not None and hits:
            melhor = max(
                (h.vec_score for h in hits if h.vec_score is not None),
                default=None,
            )
            if melhor is None:
                melhor = store.similaridade_maxima(query_vec)
            melhor = round(melhor, 4)

            # Termo raro que casa no literal e evidencia por si so: uma palavra
            # isolada contra um paragrafo tem cosseno baixo por construcao, e
            # marcar isso como duvidoso seria negar busca por identificador.
            # Raridade so vale como evidencia junto com cobertura: casar em
            # poucos trechos porque o termo e preciso e o oposto de casar em
            # poucos porque o termo nao existe no vault.
            evidencia_literal = termo_e_raro(
                hits[0].fts_total, store.contar_chunks()
            ) and cobertura_literal(query, hits[0].text) >= 0.6
            faixa = faixa_de_confianca(
                melhor, evidencia_literal, cfg.sim_confiavel, cfg.sim_duvidoso
            )
            for hit in hits:
                hit.confianca = faixa
                hit.top_sim_global = melhor if faixa != "alta" else None
        if expand:
            for hit in hits:
                hit.context_text = store.expand(hit, cfg.expand_chars)
        return hits
    finally:
        store.close()


def resolve_note(cfg: Config, ref: str) -> str | None:
    """Aceita caminho completo, caminho sem .md ou nome de wikilink."""
    store = Store(cfg.db_path, cfg.embed_dim)
    try:
        ref = ref.replace("\\", "/").strip().strip("[]")
        candidates = [ref, f"{ref}.md"]
        for candidate in candidates:
            row = store.conn.execute(
                "SELECT path FROM files WHERE path = ?", (candidate,)
            ).fetchone()
            if row:
                return row["path"]
        stem = ref.rsplit("/", 1)[-1]
        if not stem.endswith(".md"):
            stem += ".md"
        rows = store.conn.execute(
            "SELECT path FROM files WHERE path LIKE ? ORDER BY length(path) LIMIT 5",
            (f"%{stem}",),
        ).fetchall()
        return rows[0]["path"] if rows else None
    finally:
        store.close()


def read_note(cfg: Config, ref: str, heading: str | None = None, max_chars: int = 40000) -> dict:
    resolved = resolve_note(cfg, ref) or ref
    path = _safe_path(cfg, resolved)
    if not path.is_file():
        return {"error": f"nota nao encontrada: {ref}", "resolved": resolved}

    text = path.read_text(encoding="utf-8", errors="replace")

    if heading:
        wanted = heading.strip().lower()
        lines = text.split("\n")
        start = end = None
        level = 0
        for i, line in enumerate(lines):
            match = HEADING_RE.match(line)
            if not match:
                continue
            if start is None and match.group(2).strip().lower() == wanted:
                start, level = i, len(match.group(1))
            elif start is not None and len(match.group(1)) <= level:
                end = i
                break
        if start is None:
            return {
                "error": f"secao '{heading}' nao encontrada em {resolved}",
                "path": resolved,
            }
        text = "\n".join(lines[start : end or len(lines)])

    truncated = len(text) > max_chars
    return {
        "path": resolved,
        "heading": heading,
        "chars": len(text),
        "truncated": truncated,
        "content": text[:max_chars],
    }


def list_sections(cfg: Config) -> list[dict]:
    store = Store(cfg.db_path, cfg.embed_dim)
    try:
        rows = store.conn.execute(
            "SELECT section, COUNT(*) files, SUM(n_chunks) chunks"
            " FROM files GROUP BY section ORDER BY files DESC"
        ).fetchall()
        return [
            {
                "section": r["section"] or "(raiz)",
                "files": r["files"],
                "chunks": r["chunks"] or 0,
            }
            for r in rows
        ]
    finally:
        store.close()


def index_status(cfg: Config) -> dict:
    store = Store(cfg.db_path, cfg.embed_dim)
    try:
        info = store.stats()
    finally:
        store.close()
    pending = stale_files(cfg)
    info["vault"] = str(cfg.vault)
    info["pending"] = len(pending)
    info["pending_sample"] = pending[:10]
    return info


def format_hits(hits: list[SearchHit], *, snippet_chars: int = 900) -> str:
    """Saida legivel usada tanto no terminal quanto na resposta do MCP."""
    if not hits:
        return (
            "Nenhum resultado. O vault nao tem trecho relacionado a esta "
            "pergunta - diga isso, em vez de responder por conhecimento geral."
        )
    aviso = ""
    faixa = hits[0].confianca
    sim = hits[0].top_sim_global
    if faixa == "baixa" and sim is not None:
        aviso = (
            f"> CONFIANCA BAIXA (similaridade {sim:.3f}). Nenhum trecho do vault "
            "tem relacao semantica com esta pergunta.\n> O que segue casou "
            "sobretudo por palavra literal, o que quase sempre significa que a "
            "palavra existe no vault com OUTRO sentido.\n> Trate como \"o vault "
            "nao responde isso\", a menos que o texto abaixo responda de forma "
            "inequivoca.\n\n---\n\n"
        )
    elif faixa == "media" and sim is not None:
        aviso = (
            f"> CONFIANCA MEDIA (similaridade {sim:.3f}). Esta faixa contem tanto "
            "pergunta legitima escrita com vocabulario diferente do das notas "
            "quanto pergunta que o vault nao responde - as duas populacoes se "
            "sobrepoem aqui e nenhum numero as separa.\n> Leia o trecho e decida "
            "se ele responde, em vez de assumir que sim por ter vindo no topo.\n\n"
            "---\n\n"
        )
    blocks = []
    for i, hit in enumerate(hits, 1):
        text = hit.context_text or hit.text
        if len(text) > snippet_chars:
            cut = text[:snippet_chars]
            # Corta em fim de linha, mas so se isso nao comer o trecho todo
            # (tabelas tem linhas longas: o fim de linha pode estar la atras).
            nl = cut.rfind("\n")
            if nl < snippet_chars * 0.6:
                nl = cut.rfind(" ")
            text = (cut[:nl] if nl > 0 else cut).rstrip() + "\n[...]"
        origem = []
        if hit.note_ts:
            # Data na cara do resultado: o vault tem nota antiga que ainda
            # aparece como relevante, e saber de quando e muda a leitura.
            data = datetime.fromtimestamp(hit.note_ts, timezone.utc)
            idade = (datetime.now(timezone.utc) - data).days
            marca = f"{data:%Y-%m-%d}"
            if idade > 365:
                marca += f" (ha {idade // 365} ano{'s' if idade >= 730 else ''})"
            elif idade > 60:
                marca += f" (ha {idade // 30} meses)"
            origem.append(marca)
        if hit.note_kind and hit.note_kind != "nota":
            origem.append(hit.note_kind)
        if hit.vec_rank is not None:
            # A similaridade crua vai junto: o score do RRF diz so que os dois
            # rankers concordaram, e eles concordam com forca quando uma palavra
            # da pergunta existe no vault com OUTRO sentido. Este numero e o
            # unico que responde "isso tem a ver com a pergunta".
            if hit.vec_score is not None:
                origem.append(f"semantico #{hit.vec_rank + 1} (sim {hit.vec_score:.3f})")
            else:
                origem.append(f"semantico #{hit.vec_rank + 1}")
        if hit.fts_rank is not None:
            origem.append(f"literal #{hit.fts_rank + 1}")
        blocks.append(
            f"## {i}. {hit.path}"
            + (f"  (L{hit.start_line})" if hit.start_line else "")
            + f"\n**{hit.heading_path or hit.title}**"
            + f"\n_score {hit.score:.4f} · {' + '.join(origem) or 'n/a'}_\n\n{text}"
        )
    return aviso + "\n\n---\n\n".join(blocks)
