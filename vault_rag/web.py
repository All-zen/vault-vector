"""API local da interface: JSON sobre HTTP, no mesmo processo do MCP.

A interface e um app React servido daqui mesmo, de vault_rag/static/. Ela
nao tem logica de dominio: busca, escrita, diagnostico e medicao vem dos
mesmos modulos que o CLI e as ferramentas MCP usam.

Seguranca. O servidor escuta so em 127.0.0.1, mas isso nao basta: qualquer
pagina aberta no navegador consegue mandar requisicao para localhost. Tres
travas, cada uma fechando um caminho diferente:

  1. Host. Um site malicioso pode apontar o proprio dominio para 127.0.0.1
     (DNS rebinding) e passar a ser "mesma origem" que o app. O navegador
     manda o Host com o dominio dele, entao Host fora da lista = 403.
  2. Token. Toda rota /api e /mcp exige 'Authorization: Bearer <token>'.
     Pagina de outra origem nao consegue ler o token (a politica de mesma
     origem bloqueia a leitura do index.html), e nao consegue mandar header
     customizado sem um preflight de CORS que este servidor nunca aprova.
  3. Origin. Em escrita, um Origin presente e diferente do app e recusado.
     Redundante com o token de proposito: se um dia o token for desligado
     (--sem-token), a escrita continua fechada para outros sites.

O token vai embutido no index.html na hora de servir. Outro processo local
consegue le-lo, mas tambem consegue ler o arquivo .token do disco: a
fronteira de confianca aqui e o usuario do sistema, nao o processo.
"""

from __future__ import annotations

import html
import json
import sys
import time
import traceback
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any, Callable

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import __version__, api, contexto, ollama
from .config import GRAVAVEIS, Config, config_path, salvar
from .tarefas import Tarefas

PASTA_UI = Path(__file__).resolve().parent / "static"

# Mudar qualquer um destes refaz os trechos: o indice velho foi cortado de
# outro jeito. Trocar o modelo de embedding tambem, e o index_vault ja
# detecta isso sozinho.
REINDEXAM = {"target_chars", "hard_max_chars", "min_chars", "model"}

tarefas = Tarefas()


class Recusa(Exception):
    def __init__(self, status: int, mensagem: str, codigo: str = ""):
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo


class Dados:
    """Parametros de uma requisicao, da query e do corpo JSON juntos."""

    def __init__(self, valores: dict):
        self._v = valores

    def texto(self, chave: str, padrao: str | None = None, *, obrigatorio: bool = False) -> str | None:
        valor = self._v.get(chave, padrao)
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            if obrigatorio:
                raise Recusa(400, f"falta o campo '{chave}'")
            return padrao
        return str(valor)

    def inteiro(self, chave: str, padrao: int) -> int:
        try:
            return int(self._v.get(chave, padrao))
        except (TypeError, ValueError):
            raise Recusa(400, f"'{chave}' precisa ser um numero inteiro") from None

    def real(self, chave: str, padrao: float | None = None) -> float | None:
        valor = self._v.get(chave, padrao)
        if valor is None:
            return None
        try:
            return float(valor)
        except (TypeError, ValueError):
            raise Recusa(400, f"'{chave}' precisa ser um numero") from None

    def booleano(self, chave: str, padrao: bool = False) -> bool:
        valor = self._v.get(chave, padrao)
        if isinstance(valor, str):
            return valor.lower() in ("1", "true", "sim", "s")
        return bool(valor)

    def bruto(self, chave: str, padrao: Any = None) -> Any:
        return self._v.get(chave, padrao)


ROTAS: list[tuple[str, str, Callable[[Dados], Any]]] = []


def rota(metodo: str, caminho: str):
    def registrar(fn: Callable[[Dados], Any]):
        ROTAS.append((metodo, caminho, fn))
        return fn

    return registrar


def _resposta_de_erro(exc: Exception) -> JSONResponse:
    from .writer import ConflitoDeEdicao, WriteError

    if isinstance(exc, Recusa):
        return JSONResponse({"erro": str(exc), "codigo": exc.codigo}, exc.status)
    if isinstance(exc, contexto.NaoConfigurado):
        return JSONResponse({"erro": str(exc), "codigo": "nao_configurado"}, 409)
    if isinstance(exc, ConflitoDeEdicao):
        return JSONResponse({"erro": str(exc), "codigo": "conflito"}, 409)
    if isinstance(exc, (WriteError, ValueError)):
        return JSONResponse({"erro": str(exc), "codigo": "recusado"}, 400)
    if isinstance(exc, FileNotFoundError):
        return JSONResponse({"erro": str(exc), "codigo": "nao_encontrado"}, 404)
    traceback.print_exc()
    return JSONResponse({"erro": str(exc) or type(exc).__name__, "codigo": "interno"}, 500)


def _endpoint(fn: Callable[[Dados], Any]):
    async def endpoint(request: Request) -> Response:
        valores: dict = dict(request.query_params)
        valores.update(request.path_params)
        if request.method != "GET":
            corpo = await request.body()
            if corpo:
                try:
                    dados = json.loads(corpo)
                except ValueError:
                    return JSONResponse({"erro": "corpo nao e JSON", "codigo": "recusado"}, 400)
                if isinstance(dados, dict):
                    valores.update(dados)
        try:
            # Tudo aqui bloqueia (SQLite, Ollama, disco): fora do event loop,
            # senao uma busca lenta trava o MCP do mesmo processo.
            resultado = await run_in_threadpool(fn, Dados(valores))
        except Exception as exc:
            return _resposta_de_erro(exc)
        return JSONResponse(resultado)

    return endpoint


# ---------------------------------------------------------------- estado
@rota("GET", "/api/estado")
def estado(d: Dados) -> dict:
    base = {"versao": __version__, "desktop": ganchos.desktop}
    cfg = contexto.tentar()
    if cfg is None:
        return {**base, "configurado": False, "motivo": contexto.motivo()}

    from .store import Store

    store = Store(cfg.db_path, cfg.embed_dim)
    try:
        info = store.stats()
    finally:
        store.close()
    servico = ollama.estado(cfg.ollama_url, timeout=1.5)
    return {
        **base,
        "configurado": True,
        "vault": str(cfg.vault),
        "vault_nome": cfg.vault.name,
        "modelo": cfg.model,
        "juiz": cfg.rerank_model,
        "notas": info["files"],
        "trechos": info["chunks"],
        "indice_mb": info["db_mb"],
        "indice_modelo": info["model"],
        "ultima_indexacao": info["last_index"],
        "secoes": [
            {"nome": s["section"], "notas": s["files"]}
            for s in info["sections"]
            if s["section"]
        ],
        "ollama": {"ok": servico["ok"], "ms": servico["ms"]},
    }


# ----------------------------------------------------------------- busca
def _hit(h) -> dict:
    return {
        "chunk_id": h.chunk_id,
        "path": h.path,
        "titulo": h.title,
        "heading": h.heading_path or h.title,
        "linha": h.start_line,
        "trecho": h.text,
        "score": h.score,
        "vec_rank": h.vec_rank,
        "fts_rank": h.fts_rank,
        "vec_score": h.vec_score,
        "rerank": h.rerank,
        "tipo": h.note_kind,
        "data": h.note_ts,
        "mtime": h.mtime,
        "secao": h.section,
        "backlinks": h.backlinks,
        "boost": h.boost,
        "fatores": h.fatores,
    }


@rota("GET", "/api/buscar")
def buscar(d: Dados) -> dict:
    cfg = contexto.config()
    consulta = d.texto("q", obrigatorio=True)
    inicio = time.perf_counter()
    hits = api.search(
        cfg,
        consulta,
        top_k=max(1, min(d.inteiro("k", 8), 20)),
        section=d.texto("secao"),
        max_per_file=cfg.max_per_file,
        # expand=True mesmo sem mostrar a secao inteira: o juiz da faixa
        # media julga o texto expandido, e julgar outro texto mudaria a nota.
        expand=True,
    )
    segundos = time.perf_counter() - inicio

    sims = [h.vec_score for h in hits if h.vec_score is not None]
    notas = [h.rerank for h in hits if h.rerank is not None]
    return {
        "consulta": consulta,
        "faixa": hits[0].confianca if hits else None,
        "sim": max(sims) if sims else (hits[0].top_sim_global if hits else None),
        "juiz": round(sum(notas) / len(notas), 2) if notas else None,
        "julgados": len(notas),
        "segundos": round(segundos, 3),
        "semantico": any(h.vec_rank is not None for h in hits),
        "fts_total": hits[0].fts_total if hits else 0,
        "candidatos": cfg.candidates,
        "rrf_k": cfg.rrf_k,
        "modelo": cfg.model,
        "limiares": {"confiavel": cfg.sim_confiavel, "duvidoso": cfg.sim_duvidoso},
        "hits": [_hit(h) for h in hits],
    }


@rota("GET", "/api/notas")
def notas(d: Dados) -> list[dict]:
    from .store import Store

    cfg = contexto.config()
    store = Store(cfg.db_path, cfg.embed_dim)
    try:
        return store.notas(secao=d.texto("secao"), limite=max(1, min(d.inteiro("limite", 30), 200)))
    finally:
        store.close()


# ------------------------------------------------------------------ nota
@rota("GET", "/api/nota")
def nota(d: Dados) -> dict:
    return api.nota_completa(contexto.config(), d.texto("caminho", obrigatorio=True))


@rota("POST", "/api/nota")
def gravar_nota(d: Dados) -> dict:
    from .writer import write_note

    cfg = contexto.config()
    nova = d.booleano("nova")
    r = write_note(
        cfg,
        d.texto("caminho", obrigatorio=True),
        d.texto("conteudo", obrigatorio=True),
        overwrite=not nova,
        # Sem mtime numa nota existente, a trava de edicao concorrente nao
        # tem com o que comparar. A interface sempre manda o que leu.
        expected_mtime=None if nova else d.real("mtime"),
    )
    return {**r, "nota": api.nota_completa(cfg, r["path"])}


@rota("POST", "/api/nota/mover")
def mover_nota(d: Dados) -> dict:
    from .writer import move_note

    return move_note(
        contexto.config(),
        d.texto("de", obrigatorio=True),
        d.texto("para", obrigatorio=True),
        atualizar_links=d.booleano("links", True),
    )


@rota("POST", "/api/nota/apagar")
def apagar_nota(d: Dados) -> dict:
    from .writer import delete_note

    return delete_note(contexto.config(), d.texto("caminho", obrigatorio=True))


@rota("POST", "/api/nota/restaurar")
def restaurar_nota(d: Dados) -> dict:
    from .writer import restaurar

    cfg = contexto.config()
    r = restaurar(
        cfg,
        d.texto("caminho", obrigatorio=True),
        d.texto("versao", obrigatorio=True),
        expected_mtime=d.real("mtime"),
    )
    return {**r, "nota": api.nota_completa(cfg, r["path"])}


# --------------------------------------------------------- saude e indice
@rota("GET", "/api/saude")
def saude(d: Dados) -> dict:
    from .diagnostico import como_dict, diagnosticar

    cfg = contexto.config()
    return {
        "grupos": como_dict(diagnosticar(cfg, testar_busca=d.booleano("testar_busca", True))),
        "indice": api.index_status(cfg),
        "mapa": api.mapa_do_indice(cfg),
    }


@rota("POST", "/api/indexar")
def indexar(d: Dados) -> dict:
    from .indexer import index_vault

    cfg = contexto.config()
    forcar = d.booleano("forcar")

    def trabalho(t):
        rep = index_vault(
            cfg, force=forcar, verbose=False,
            progress=lambda rel, r: t.andamento(r.processadas, r.total, rel),
        )
        return {
            "texto": rep.as_text(),
            "indexadas": rep.indexed,
            "removidas": rep.removed,
            "trechos": rep.chunks,
            "erros": rep.errors[:10],
        }

    return tarefas.iniciar("indexar", trabalho).como_dict()


@rota("GET", "/api/tarefas/{id}")
def tarefa(d: Dados) -> dict:
    t = tarefas.obter(d.texto("id", obrigatorio=True))
    if t is None:
        raise Recusa(404, "tarefa nao encontrada (o app reiniciou?)", "nao_encontrado")
    return t.como_dict()


# --------------------------------------------------------------- modelos
@rota("GET", "/api/ollama")
def ollama_estado(d: Dados) -> dict:
    from .store import Store

    cfg = contexto.config()
    est = ollama.estado(d.texto("url") or cfg.ollama_url)
    store = Store(cfg.db_path, cfg.embed_dim)
    try:
        indice_modelo = store.get_meta("model")
    finally:
        store.close()
    return {**est, "modelo": cfg.model, "juiz": cfg.rerank_model, "indice_modelo": indice_modelo,
            "config_url": cfg.ollama_url}


@rota("POST", "/api/ollama/embeddar")
def embeddar(d: Dados) -> dict:
    import numpy as np

    from .embed import OllamaEmbedder

    cfg = contexto.config()
    modelo = d.texto("modelo") or cfg.model
    texto = d.texto("texto", obrigatorio=True)[:4000]
    embedder = OllamaEmbedder(cfg.ollama_url, modelo, cfg.request_timeout, cfg.batch_size)
    inicio = time.perf_counter()
    vetor = embedder.embed_one(texto)
    ms = round((time.perf_counter() - inicio) * 1000)
    norma = float(np.linalg.norm(vetor))
    unitario = vetor / norma if norma else vetor
    return {
        "modelo": modelo,
        "dims": int(vetor.shape[0]),
        "ms": ms,
        "norma": round(norma, 4),
        "valores": [round(float(x), 4) for x in unitario],
    }


@rota("POST", "/api/ollama/baixar")
def baixar(d: Dados) -> dict:
    cfg = contexto.config()
    nome = d.texto("modelo", obrigatorio=True)

    def trabalho(t):
        ollama.baixar(
            cfg.ollama_url, nome,
            progresso=lambda status, feito, total: t.andamento(feito or 0, total, status),
        )
        return {"modelo": nome}

    return tarefas.iniciar("baixar", trabalho).como_dict()


@rota("POST", "/api/medir/paralelismo")
def medir_paralelismo(d: Dados) -> dict:
    from . import medicao

    cfg = contexto.config()
    niveis = [int(n) for n in (d.bruto("niveis") or [1, 2, 3, 4])][:6]

    def trabalho(t):
        textos, total_notas = medicao.amostra_de_trechos(cfg, d.inteiro("amostra", 32))
        if not textos:
            raise ValueError("nenhuma nota para medir")
        t.andamento(0, len(niveis), "aquecendo o modelo")
        resultados = medicao.medir_paralelismo(
            cfg, textos, niveis,
            ao_medir=lambda r: (t.parcial(r), t.andamento(len(t.parciais), len(niveis))),
        )
        melhor = medicao.melhor_nivel(resultados)
        return {
            "resultados": resultados,
            "melhor": melhor,
            "inutil": medicao.paralelismo_inutil(resultados),
            "amostra": len(textos),
            "total_notas": total_notas,
            "parallel_atual": cfg.parallel,
        }

    return tarefas.iniciar("paralelismo", trabalho).como_dict()


# ------------------------------------------------------------ calibracao
def _arquivo_de_perguntas() -> Path:
    return config_path().parent / "perguntas.txt"


@rota("POST", "/api/medir/calibracao")
def medir_calibracao(d: Dados) -> dict:
    from . import medicao

    cfg = contexto.config()
    arquivo = _arquivo_de_perguntas()
    perguntas = [p for p, _ in medicao.ler_perguntas(arquivo)] if arquivo.is_file() else []

    def trabalho(t):
        def ao_medir(item, feito, total):
            t.andamento(feito, total, item["pergunta"])
            t.parcial(item)

        return medicao.medir_calibracao(
            cfg, amostra=d.inteiro("amostra", 20), perguntas=perguntas or None, ao_medir=ao_medir,
        )

    return tarefas.iniciar("calibracao", trabalho).como_dict()


# ----------------------------------------------------------------- config
def _padroes() -> dict:
    return {
        f.name: f.default
        for f in fields(Config)
        if f.name in GRAVAVEIS and f.default is not MISSING
    }


@rota("GET", "/api/config")
def ler_config(d: Dados) -> dict:
    cfg = contexto.tentar()
    padroes = _padroes()
    return {
        "arquivo": str(config_path()),
        "configurado": cfg is not None,
        "valores": {k: getattr(cfg, k) for k in padroes} if cfg else padroes,
        "padroes": padroes,
        "reindexam": sorted(REINDEXAM),
        "perguntas": _arquivo_de_perguntas().is_file(),
    }


@rota("POST", "/api/config")
def gravar_config(d: Dados) -> dict:
    padroes = _padroes()
    pedidas = d.bruto("valores") or {}
    if not isinstance(pedidas, dict) or not pedidas:
        raise Recusa(400, "nada para gravar")

    mudancas = {}
    for chave, valor in pedidas.items():
        if chave not in padroes:
            raise Recusa(400, f"'{chave}' nao se ajusta por aqui")
        tipo = type(padroes[chave])
        try:
            mudancas[chave] = tipo(valor)
        except (TypeError, ValueError):
            raise Recusa(400, f"'{chave}' precisa ser {tipo.__name__}") from None

    antes = contexto.tentar()
    salvar(mudancas)
    contexto.recarregar()
    resposta = ler_config(d)
    resposta["reindexar"] = bool(antes) and any(
        k in REINDEXAM and getattr(antes, k) != v for k, v in mudancas.items()
    )
    return resposta


@rota("GET", "/api/recorte")
def recorte(d: Dados) -> dict:
    """Como uma nota real seria cortada com os parametros pedidos."""
    from .chunker import chunk_markdown
    from .store import Store

    cfg = contexto.config()
    caminho = d.texto("caminho")
    if not caminho:
        # Sem nota pedida, a maior: e onde o recorte faz diferenca de verdade.
        store = Store(cfg.db_path, cfg.embed_dim)
        try:
            row = store.conn.execute("SELECT path FROM files ORDER BY size DESC LIMIT 1").fetchone()
        finally:
            store.close()
        if row is None:
            raise Recusa(409, "indice vazio", "indice_vazio")
        caminho = row["path"]

    texto = api._safe_path(cfg, caminho).read_text(encoding="utf-8", errors="replace")
    alvo = d.inteiro("target_chars", cfg.target_chars)
    nota_ = chunk_markdown(
        texto,
        target_chars=alvo,
        hard_max_chars=max(d.inteiro("hard_max_chars", cfg.hard_max_chars), alvo),
        min_chars=d.inteiro("min_chars", cfg.min_chars),
    )
    return {
        "caminho": caminho,
        "chars": len(texto),
        "trechos": [
            {
                "ord": c.ord,
                "heading": c.heading_path,
                "linha": c.start_line,
                "chars": len(c.text),
                "inicio": " ".join(c.text.split())[:160],
            }
            for c in nota_.chunks
        ],
    }


# -------------------------------------------------------- primeiro uso
@rota("GET", "/api/vaults")
def vaults(d: Dados) -> list[dict]:
    achados = []
    for pasta in api.procurar_vaults():
        notas_md = 0
        for _ in pasta.rglob("*.md"):
            notas_md += 1
            if notas_md >= 5000:
                break  # contar o resto so atrasaria a tela
        achados.append({"caminho": str(pasta), "nome": pasta.name, "notas": notas_md})
    return achados


@rota("POST", "/api/vault")
def escolher_vault(d: Dados) -> dict:
    from .semente import criar_vault

    alvo = Path(d.texto("caminho", obrigatorio=True)).expanduser()
    criados = []
    if d.booleano("criar"):
        alvo.mkdir(parents=True, exist_ok=True)
        criados = criar_vault(alvo)
    if not alvo.is_dir():
        raise Recusa(400, f"pasta nao encontrada: {alvo}")
    salvar({"vault": alvo.as_posix()})
    if contexto.recarregar() is None:
        raise Recusa(400, contexto.motivo())
    return {"vault": str(alvo), "criados": criados, "estado": estado(d)}


# ------------------------------------------------------------- conectar
@rota("GET", "/api/conectar")
def conectar(d: Dados) -> dict:
    return {
        "url": f"http://127.0.0.1:{ganchos.porta}/mcp/",
        "token": ganchos.token,
        "python": sys.executable,
        "ferramentas": ganchos.ferramentas,
    }


# ------------------------------------------------------- desktop e sistema
class Ganchos:
    """O que o processo hospedeiro injeta: porta, token, e se e o app de desktop.

    O app de desktop registra aqui as acoes que so ele sabe fazer (mostrar a
    janela, ligar a inicializacao com o Windows). Rodando como servico puro,
    elas ficam vazias e a interface esconde os controles.
    """

    def __init__(self):
        self.porta = 8765
        self.token = ""
        self.ferramentas: list[str] = []
        self.desktop = False
        self.mostrar_janela: Callable[[], None] | None = None
        self.autostart: Any = None


ganchos = Ganchos()


@rota("GET", "/api/sistema")
def sistema(d: Dados) -> dict:
    a = ganchos.autostart
    return {
        "versao": __version__,
        "desktop": ganchos.desktop,
        "autostart": {"suportado": bool(a and a.suportado()), "ligado": bool(a and a.ligado())},
        "config": str(config_path()),
        "python": sys.executable,
    }


@rota("POST", "/api/sistema/autostart")
def autostart(d: Dados) -> dict:
    a = ganchos.autostart
    if not (a and a.suportado()):
        raise Recusa(400, "iniciar com o sistema so existe no app de desktop, no Windows")
    if d.booleano("ligado"):
        a.ligar()
    else:
        a.desligar()
    return sistema(d)


@rota("POST", "/api/sistema/mostrar")
def mostrar(d: Dados) -> dict:
    # Chamado pela segunda instancia: em vez de abrir outro app, traz a
    # janela da primeira para a frente.
    if ganchos.mostrar_janela:
        ganchos.mostrar_janela()
    return {"ok": bool(ganchos.mostrar_janela)}


# --------------------------------------------------------------- montagem
class Guarda:
    """Middleware ASGI com as tres travas descritas no topo do modulo."""

    ABERTAS = ("/saude",)
    ESTATICAS = ("/", "/index.html", "/favicon.svg")

    def __init__(self, app, *, token: str, hosts: set[str]):
        self.app = app
        self.token = token
        self.hosts = hosts
        self.origens = {f"http://{h}" for h in hosts}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        cab = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        caminho = scope["path"]

        if cab.get("host", "") not in self.hosts:
            return await self._negar(scope, receive, send, 403, "host nao permitido")

        if caminho in self.ABERTAS:
            return await self.app(scope, receive, send)

        origem = cab.get("origin")
        if scope["method"] not in ("GET", "HEAD", "OPTIONS") and origem and origem not in self.origens:
            return await self._negar(scope, receive, send, 403, "origem nao permitida")

        estatica = caminho in self.ESTATICAS or caminho.startswith("/assets/")
        if self.token and not estatica:
            if cab.get("authorization") != f"Bearer {self.token}":
                return await self._negar(scope, receive, send, 401, "token invalido ou ausente")

        return await self.app(scope, receive, send)

    @staticmethod
    async def _negar(scope, receive, send, status: int, motivo: str):
        await JSONResponse({"erro": motivo, "codigo": "negado"}, status)(scope, receive, send)


def _pagina_inicial(token: str) -> Response:
    indice = PASTA_UI / "index.html"
    if not indice.is_file():
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><title>vault-vector</title>"
            "<body style='font:15px system-ui;background:#121415;color:#c3c9c6;padding:40px'>"
            "<h1 style='color:#eef1ef'>Interface ainda nao compilada</h1>"
            "<p>O servidor esta no ar, mas falta montar a interface:</p>"
            "<pre style='background:#08090a;padding:12px;color:#5fdccd'>"
            "npm --prefix ui ci\nnpm --prefix ui run build</pre>",
            status_code=503,
        )
    pagina = indice.read_text(encoding="utf-8").replace(
        '<meta name="vv-token" content="">',
        f'<meta name="vv-token" content="{html.escape(token, quote=True)}">',
    )
    # O token muda se o arquivo .token for recriado: nada de cache.
    return HTMLResponse(pagina, headers={"Cache-Control": "no-store"})


def montar(app, *, token: str, host: str = "127.0.0.1", porta: int = 8765,
           ferramentas: list[str] | None = None) -> None:
    """Acrescenta API, interface e as travas a um app Starlette ja existente.

    Recebe o app do MCP em vez de criar outro: um processo, uma porta, e o
    lifespan do MCP (que gerencia as sessoes) continua sendo o do app.
    """
    ganchos.porta = porta
    ganchos.token = token
    ganchos.ferramentas = ferramentas or []

    def favicon(request):
        icone = PASTA_UI / "favicon.svg"
        return FileResponse(icone) if icone.is_file() else Response(status_code=404)

    rotas = [Route(c, _endpoint(fn), methods=[m]) for m, c, fn in ROTAS]
    rotas += [
        Route("/", lambda r: _pagina_inicial(token)),
        Route("/index.html", lambda r: _pagina_inicial(token)),
        Route("/favicon.svg", favicon),
        Mount("/assets", StaticFiles(directory=PASTA_UI / "assets", check_dir=False)),
    ]
    app.routes.extend(rotas)

    hosts = {f"127.0.0.1:{porta}", f"localhost:{porta}", f"{host}:{porta}"}
    app.add_middleware(Guarda, token=token, hosts=hosts)
