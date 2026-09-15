"""MCP server: expoe a busca do vault como ferramentas para o Claude.

Transporte stdio — e o que o Claude Desktop e o Claude Code esperam.
"""

from __future__ import annotations

import json
import os
import sys

# O SDK renomeou FastMCP para MCPServer na 2.x e mudou o modulo de lugar.
# Aceitar as duas evita prender o projeto numa versao so.
try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Servidor
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Servidor

from . import api
from .config import load_config

cfg = load_config()

def _instrucoes() -> str:
    """Descricao do vault para o modelo.

    Ordem: o que a pessoa escreveu no config vence; senao, o perfil e gerado
    lendo o proprio indice. Nenhuma estrutura de vault fica embutida no codigo
    - assim o projeto serve a qualquer vault sem carregar o conteudo de quem o
    escreveu.
    """
    if getattr(cfg, "instructions", ""):
        return cfg.instructions
    try:
        from .perfil import descrever
        from .store import Store

        store = Store(cfg.db_path, cfg.embed_dim)
        try:
            return descrever(store, cfg.vault.name)
        finally:
            store.close()
    except Exception:
        # Indice ausente ou ilegivel nao pode impedir o servidor de subir:
        # sem ferramentas o cliente MCP fica sem nada, com descricao generica
        # fica utilizavel.
        return (
            "Busca e escrita num vault de notas markdown. Rode 'vault-rag index' "
            "se a busca nao devolver nada."
        )


mcp = _Servidor("vault-rag", instructions=_instrucoes())


@mcp.tool()
def vault_search(
    query: str,
    top_k: int = 8,
    section: str = "",
    max_per_file: int = 3,
    expand: bool = True,
) -> str:
    """Busca trechos no vault combinando similaridade semantica e busca literal.

    Funciona bem tanto para perguntas conceituais ("como decidi o particionamento
    das VLANs") quanto para identificadores exatos (hostname, IP, codigo de erro),
    porque funde os dois rankings.

    Args:
        query: pergunta ou termos em linguagem natural.
        top_k: quantos trechos devolver (1 a 20). O default de 8 ja e
            calibrado para leitura por modelo, nao por pessoa.
        section: opcional, limita a uma pasta raiz do vault
            (ex.: "Trabalho", "Projetos").
        max_per_file: no maximo N trechos da mesma nota, para o resultado nao
            ficar dominado por um unico arquivo longo. 0 desliga o limite.
        expand: devolve a secao inteira em volta do trecho que casou, em vez
            do trecho isolado. Desligue para respostas mais curtas.
    """
    top_k = max(1, min(int(top_k), 20))
    hits = api.search(
        cfg,
        query,
        top_k=top_k,
        section=section or None,
        max_per_file=max_per_file,
        expand=expand,
    )
    return api.format_hits(hits)


@mcp.tool()
def vault_read(path: str, heading: str = "") -> str:
    """Le uma nota do vault inteira, ou apenas uma secao dela.

    Args:
        path: caminho relativo ao vault (ex.: "Projetos/00-MOC.md"). Aceita
            tambem o alvo de um wikilink, sem a extensao.
        heading: opcional, titulo exato de uma secao para recortar so ela.
    """
    result = api.read_note(cfg, path, heading or None)
    if "error" in result:
        return result["error"]
    header = f"# {result['path']}"
    if result["truncated"]:
        header += f"\n_(truncado em {result['chars']} caracteres)_"
    return f"{header}\n\n{result['content']}"


@mcp.tool()
def vault_list_sections() -> str:
    """Lista as secoes (pastas raiz) do vault com quantas notas cada uma tem."""
    rows = api.list_sections(cfg)
    if not rows:
        return "Indice vazio. Rode 'vault-rag index'."
    width = max(len(r["section"]) for r in rows)
    lines = [f"{r['section']:<{width}}  {r['files']:>4} notas  {r['chunks']:>5} chunks" for r in rows]
    return "\n".join(lines)


@mcp.tool()
def vault_edit(path: str, old_str: str, new_str: str, replace_all: bool = False) -> str:
    """Troca um trecho exato dentro de uma nota do vault.

    E a ferramenta preferida para alterar conteudo: mexe so no pedaco que
    precisa mudar e reindexa a nota na hora. A versao anterior vai para
    _historico/ antes da gravacao, entao da sempre para voltar atras.

    O old_str precisa aparecer UMA unica vez na nota — inclua as linhas em
    volta ate o alvo ficar unico. Leia a nota com vault_read antes, para
    copiar o trecho exato (espacos e acentos contam).

    Args:
        path: caminho relativo ao vault, ex.: "Projetos/00-MOC.md".
        old_str: trecho exato a substituir, como esta na nota.
        new_str: texto que entra no lugar (vazio apaga o trecho).
        replace_all: troca todas as ocorrencias em vez de exigir alvo unico.
    """
    from .writer import WriteError, edit_note

    try:
        r = edit_note(cfg, path, old_str, new_str, replace_all=replace_all)
    except WriteError as exc:
        return f"Nao gravei: {exc}"
    linhas = [f"{r['path']}: {r['acao']}", f"indice: {r['indice']}"]
    if r["historico"]:
        linhas.append(f"versao anterior: {r['historico']}")
    return "\n".join(linhas)


@mcp.tool()
def vault_append(path: str, content: str) -> str:
    """Acrescenta texto ao fim de uma nota, criando a nota se nao existir.

    Boa para diario, fila aberta, registro de decisao — qualquer coisa que
    cresce por acrescimo. Reindexa na hora e guarda a versao anterior.

    Respeite as convencoes do vault ao escolher o caminho: diario de infra em
    Trabalho/99-Diario/AAAA-MM-DD-assunto.md, pesquisa em
    Pesquisa/99-Daily/, e assim por diante. As instructions do servidor trazem
    as convencoes reais deste vault, detectadas do proprio indice.

    Args:
        path: caminho relativo ao vault.
        content: markdown a acrescentar (uma linha em branco e inserida antes).
    """
    from .writer import WriteError, append_note

    try:
        r = append_note(cfg, path, content)
    except WriteError as exc:
        return f"Nao gravei: {exc}"
    linhas = [f"{r['path']}: {r['acao']}", f"indice: {r['indice']}"]
    if r["historico"]:
        linhas.append(f"versao anterior: {r['historico']}")
    return "\n".join(linhas)


@mcp.tool()
def vault_write(path: str, content: str, overwrite: bool = False) -> str:
    """Cria uma nota nova no vault.

    Recusa sobrescrever nota existente a menos que overwrite seja true — para
    alterar conteudo, prefira vault_edit ou vault_append. Quando sobrescreve,
    a versao anterior vai para _historico/ primeiro.

    Args:
        path: caminho relativo ao vault, dentro da secao correta.
        content: markdown completo da nota, comecando por um heading '# '.
        overwrite: permite substituir uma nota que ja existe.
    """
    from .writer import WriteError, write_note

    try:
        r = write_note(cfg, path, content, overwrite=overwrite)
    except WriteError as exc:
        return f"Nao gravei: {exc}"
    linhas = [f"{r['path']}: {r['acao']}", f"indice: {r['indice']}"]
    if r["historico"]:
        linhas.append(f"versao anterior: {r['historico']}")
    return "\n".join(linhas)


@mcp.tool()
def vault_list(pasta: str = "") -> str:
    """Lista o que existe numa pasta do vault: subpastas e notas.

    Use para navegar quando nao souber o caminho exato, antes de vault_read
    ou vault_write. Sem argumento, lista a raiz.

    Args:
        pasta: caminho relativo, ex.: "Trabalho/99-Diario". Vazio = raiz.
    """
    from .writer import WriteError, list_dir

    try:
        r = list_dir(cfg, pasta)
    except (WriteError, ValueError) as exc:
        return f"Erro: {exc}"
    linhas = [f"{r['pasta']}:"]
    for d in r["subpastas"]:
        linhas.append(f"  [pasta] {d['nome']}/  ({d['notas']} notas)")
    for n in r["notas"]:
        linhas.append(f"  {n['nome']}  ({n['bytes'] // 1024} KB)")
    if not r["subpastas"] and not r["notas"]:
        linhas.append("  (vazia)")
    return "\n".join(linhas)


@mcp.tool()
def vault_move(origem: str, destino: str, atualizar_links: bool = True) -> str:
    """Move ou renomeia uma nota, corrigindo os wikilinks que apontavam para ela.

    Sem a correcao dos links, mover deixa referencia quebrada espalhada pelo
    vault. Cada nota alterada passa pelo historico, e o indice acompanha os
    dois caminhos.

    Args:
        origem: caminho atual da nota.
        destino: caminho novo, incluindo a pasta.
        atualizar_links: desligue so se souber que nao ha wikilinks apontando.
    """
    from .writer import WriteError, move_note

    try:
        r = move_note(cfg, origem, destino, atualizar_links=atualizar_links)
    except (WriteError, ValueError) as exc:
        return f"Nao movi: {exc}"
    return (
        f"{r['de']} -> {r['para']}\n"
        f"wikilinks atualizados em {r['links_atualizados']} nota(s)\n"
        f"indice: {r['indice']}"
    )


@mcp.tool()
def vault_delete(path: str) -> str:
    """Tira uma nota do vault, mandando para a lixeira do historico.

    Nao apaga de verdade: o arquivo vai para _historico/lixeira/ e sai do
    indice. Para apagar em definitivo, a pessoa faz pelo gerenciador de arquivos.

    Avisa quantas outras notas citam o nome dessa, porque apagar algo
    referenciado deixa link quebrado.

    Args:
        path: caminho relativo da nota.
    """
    from .writer import WriteError, delete_note

    try:
        r = delete_note(cfg, path)
    except (WriteError, ValueError) as exc:
        return f"Nao removi: {exc}"
    aviso = (
        f"\nATENCAO: {r['citada_por']} nota(s) ainda citam esse nome — "
        "verifique se ficaram links quebrados."
        if r["citada_por"]
        else ""
    )
    return f"{r['path']} removida do vault\nrecuperavel em: {r['lixeira']}{aviso}"


@mcp.tool()
def vault_reindex(force: bool = False) -> str:
    """Atualiza o indice com as notas que mudaram no disco.

    Incremental: so reprocessa o que mudou desde a ultima vez. Chame quando
    vault_index_status apontar notas pendentes, ou depois de escrever notas
    novas no vault.

    Args:
        force: reindexa o vault inteiro do zero (demora — use so se trocou o
            modelo de embedding ou desconfia do indice).
    """
    from .indexer import index_vault, stale_files

    if not force:
        pending = stale_files(cfg)
        if len(pending) > 150:
            return (
                f"{len(pending)} notas pendentes — muita coisa para reindexar "
                f"por aqui. Rode no terminal: vault-rag index"
            )
        if not pending:
            return "Indice ja esta em dia."
    report = index_vault(cfg, force=force, verbose=False)
    return report.as_text()


@mcp.tool()
def vault_index_status() -> str:
    """Estado do indice: quantas notas, quantos chunks e o que mudou desde a ultima indexacao."""
    info = api.index_status(cfg)
    return json.dumps(info, ensure_ascii=False, indent=2)


def token_do_projeto(criar: bool = False) -> str:
    """Token guardado ao lado do config, gerado na primeira vez.

    O bind em 127.0.0.1 ja impede acesso de fora da maquina; o token protege
    contra outro processo local qualquer conseguir ler o vault.
    """
    import secrets
    from pathlib import Path

    arquivo = Path(__file__).resolve().parent.parent / ".token"
    if arquivo.is_file():
        valor = arquivo.read_text(encoding="utf-8").strip()
        if valor:
            return valor
    if not criar:
        return ""
    valor = secrets.token_urlsafe(32)
    arquivo.write_text(valor, encoding="utf-8")
    return valor


def serve_http(host: str = "127.0.0.1", port: int = 8765, token: str = "") -> None:
    """Sobe o servidor em HTTP local, para um processo servir todos os clientes."""
    import uvicorn
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    # Cinto de seguranca: sob pythonw.exe stdout/stderr sao None e o logging
    # do uvicorn estoura antes de abrir a porta. Quem entra por main_servico()
    # ja chega aqui com um arquivo de log no lugar; esta guarda cobre o resto.
    if sys.stdout is None or sys.stderr is None:
        vazio = open(os.devnull, "w", encoding="utf-8")
        if sys.stdout is None:
            sys.stdout = vazio
        if sys.stderr is None:
            sys.stderr = vazio

    # Nao mexe em mcp.settings: na 2.x host/port sairam do objeto. Quem
    # decide onde escutar e o uvicorn logo abaixo, e isso vale nas duas.
    app = mcp.streamable_http_app()

    if token:
        class ExigeToken(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                if request.url.path == "/saude":
                    return JSONResponse({"ok": True})
                if request.headers.get("authorization") != f"Bearer {token}":
                    return JSONResponse({"error": "token invalido ou ausente"}, 401)
                return await call_next(request)

        app.add_middleware(ExigeToken)

    print(f"vault-rag HTTP em http://{host}:{port}/mcp/", file=sys.stderr)
    print(f"token: {'exigido' if token else 'DESLIGADO (qualquer processo local acessa)'}",
          file=sys.stderr)
    uvicorn.run(app, host=host, port=port, log_level="warning")


def main() -> None:
    try:
        mcp.run()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
