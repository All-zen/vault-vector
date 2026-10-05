"""Funcoes de alto nivel compartilhadas pelo CLI e pelo MCP server."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .embed import EmbeddingError, OllamaEmbedder
from .indexer import stale_files
from .rerank import OllamaJudge
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


def aplicar_rerank(cfg: Config, query: str, hits: list[SearchHit]) -> str:
    """Julga os primeiros trechos com o modelo local e reordena por nota.

    So e chamada na faixa media, que e onde o cosseno nao decide: ruido e
    pergunta legitima com outro vocabulario ocupam a mesma faixa de
    similaridade. O juiz le pergunta e trecho juntos, que e a informacao que
    a similaridade de vetor nao carrega.

    Decide pela MEDIA das notas, nao pelo maximo. Medido em 15/09 com 8
    perguntas legitimas contra 8 de ruido, 5 trechos julgados em cada:

      estatistica   legitimas          ruidos            separa?
      maximo        7 de 8 tiram >=6   7 de 8 tiram >=6  NAO
      media         1,4 a 6,4          1,0 a 3,2         SIM, em 3,3

    O maximo nao separa porque mede o trecho mais sortudo: com cinco
    tentativas e um juiz generoso, ate pergunta fora do dominio acha um
    trecho que tira 6. A media mede se o CONJUNTO devolvido tem a ver com a
    pergunta, que e a coisa que estava sendo perguntada desde o inicio.

    E o mesmo erro do RRF, uma camada acima: la o score media concordancia
    entre rankers e nao distingue os dois acertando dos dois errando junto;
    aqui o maximo media um trecho isolado e nao distingue nada.

    Margem medida: maior ruido 3,2 contra menor legitima aprovada 3,4. E
    fina, e com 8 contra 8 nao da para tratar como definitiva.

    Devolve a faixa nova. Juiz indisponivel devolve a faixa como estava.
    """
    juiz = OllamaJudge(
        cfg.ollama_url,
        cfg.rerank_model,
        cfg.rerank_timeout,
        cfg.rerank_chars,
        cfg.num_thread,
    )
    julgados = hits[: cfg.rerank_top]
    for hit in julgados:
        hit.rerank = juiz.nota(query, hit.context_text or hit.text)

    notas = [h.rerank for h in julgados if h.rerank is not None]
    if not notas:
        return "media"  # juiz mudo: nada mudou, a ressalva antiga continua

    # Reordena so o que foi julgado. Empate mantem a ordem do RRF, que ja
    # embute recencia e backlinks; o juiz desempata relevancia, nao o resto.
    ordenados = sorted(
        range(len(julgados)),
        key=lambda i: (-(julgados[i].rerank or -1), i),
    )
    hits[: len(julgados)] = [julgados[i] for i in ordenados]

    media = sum(notas) / len(notas)
    if media >= cfg.rerank_promove:
        return "alta"
    if media <= cfg.rerank_rebaixa:
        return "baixa"
    return "media"


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

        # O reranker entra DEPOIS do expand porque julga o texto que o leitor
        # vai receber, nao o chunk cru embeddado. Julgar coisa diferente da
        # que sai seria medir outra pergunta.
        if hits and cfg.rerank_model and hits[0].confianca == "media":
            nova = aplicar_rerank(cfg, query, hits)
            for hit in hits:
                hit.confianca = nova
                if nova == "alta":
                    hit.top_sim_global = None
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


def procurar_vaults() -> list[Path]:
    """Vaults do Obsidian nos lugares de costume: pasta do usuario e Documentos.

    Um nivel so de profundidade. Varrer o disco inteiro atras de .obsidian
    demora e acha copia de backup antes de achar o vault de verdade.
    """
    achados = []
    for base in (Path.home(), Path.home() / "Documents", Path.home() / "Documentos"):
        if not base.is_dir():
            continue
        try:
            for d in base.iterdir():
                if d.is_dir() and (d / ".obsidian").is_dir() and d not in achados:
                    achados.append(d)
        except OSError:
            continue
    return achados


def nota_completa(cfg: Config, ref: str) -> dict:
    """Tudo que a tela de nota mostra: texto, metadados, trechos, citacoes.

    O mtime vai junto para a gravacao poder recusar se a nota mudou no
    disco entre a leitura e o salvar - o Obsidian aberto ao lado, por exemplo.
    """
    from .meta import resolve_link
    from .writer import versoes

    resolvido = resolve_note(cfg, ref) or ref
    caminho = _safe_path(cfg, resolvido)
    if not caminho.is_file():
        raise FileNotFoundError(f"nota nao encontrada: {ref}")
    rel = caminho.relative_to(cfg.vault.resolve()).as_posix()
    stat = caminho.stat()

    store = Store(cfg.db_path, cfg.embed_dim)
    try:
        arquivo = store.arquivo(rel) or {}
        trechos = store.trechos(rel)
        citada_por = store.quem_cita(rel, resolve_link)
    finally:
        store.close()

    return {
        "path": rel,
        "titulo": arquivo.get("title") or caminho.stem,
        "conteudo": caminho.read_text(encoding="utf-8", errors="replace"),
        "mtime": stat.st_mtime,
        "bytes": stat.st_size,
        "secao": arquivo.get("section", rel.split("/")[0] if "/" in rel else ""),
        "tipo": arquivo.get("note_kind") or "nota",
        "data": arquivo.get("note_ts"),
        "indexada": bool(arquivo),
        # O indice pode estar atras do disco: nota editada fora do app e
        # ainda nao reindexada. A tela avisa em vez de mostrar trecho velho.
        "desatualizada": bool(arquivo) and abs(arquivo.get("mtime", 0) - stat.st_mtime) > 1.0,
        "trechos": trechos,
        "citada_por": citada_por,
        "versoes": versoes(cfg, rel),
    }


def mapa_do_indice(cfg: Config) -> dict:
    """Posicao de cada nota pendente na lista do vault, para desenhar o mapa.

    'pendentes' sao indices na ordem alfabetica dos caminhos - a mesma ordem
    em que a indexacao percorre o vault. Nota apagada do disco nao tem
    posicao e conta a parte, em 'removidas'.
    """
    from .indexer import iter_notes

    caminhos = [rel for _, rel in iter_notes(cfg)]
    pendentes = set(stale_files(cfg))
    no_disco = set(caminhos)
    return {
        "total": len(caminhos),
        "pendentes": [i for i, rel in enumerate(caminhos) if rel in pendentes],
        "amostra": [rel for rel in caminhos if rel in pendentes][:10],
        "removidas": len(pendentes - no_disco),
    }


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
    # Quando o juiz local rodou, a ressalva muda de dono: quem classificou nao
    # foi mais o cosseno sozinho, foi um modelo que leu pergunta e trecho
    # juntos. Dizer "nenhum numero separa" depois disso seria mentira.
    julgou = any(h.rerank is not None for h in hits)
    notas = [h.rerank for h in hits if h.rerank is not None]
    media_juiz = sum(notas) / len(notas) if notas else None
    if julgou and faixa == "baixa":
        aviso = (
            "> CONFIANCA BAIXA. O juiz local leu a pergunta junto com os "
            f"trechos devolvidos e a aderencia media ficou em {media_juiz:.1f}/10."
            "\n> Trate como \"o vault nao responde isso\". Similaridade de vetor "
            f"era {sim:.3f}, dentro da faixa em que ela nao decide sozinha."
            "\n\n---\n\n"
        )
    elif julgou and faixa == "media":
        aviso = (
            "> CONFIANCA MEDIA. Nem a similaridade nem o juiz local decidiram: "
            f"a aderencia media ficou em {media_juiz:.1f}/10, no meio da escala."
            "\n> Leia o trecho e decida se ele responde.\n\n---\n\n"
        )
    elif faixa == "baixa" and sim is not None:
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
        if hit.rerank is not None:
            # Vai junto com os outros sinais de proposito: o leitor precisa
            # ver que esta nota veio de um julgamento, nao de distancia.
            origem.append(f"juiz {hit.rerank}/10")
        blocks.append(
            f"## {i}. {hit.path}"
            + (f"  (L{hit.start_line})" if hit.start_line else "")
            + f"\n**{hit.heading_path or hit.title}**"
            + f"\n_score {hit.score:.4f} · {' + '.join(origem) or 'n/a'}_\n\n{text}"
        )
    return aviso + "\n\n---\n\n".join(blocks)
