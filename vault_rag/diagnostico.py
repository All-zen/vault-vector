"""Tudo que a busca precisa para funcionar, e o que fazer quando algo falta.

Era o corpo do 'vault-vector doctor', que so imprimia. Virou dado para a
tela de saude do app mostrar a mesma checagem: CLI e interface leem a mesma
lista, entao nao tem como um dizer "ok" e o outro "falta".
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field

from . import ollama
from .config import Config


@dataclass
class Item:
    # "ok", "aviso" ou "falta". So "falta" conta como problema: aviso e
    # coisa que custa tempo (modelo frio, nota pendente), nao que quebra.
    status: str
    rotulo: str
    detalhe: str = ""
    dica: str = ""


@dataclass
class Grupo:
    id: str
    nome: str
    itens: list[Item] = field(default_factory=list)

    def add(self, ok: bool, rotulo: str, detalhe: str = "", dica: str = "",
            senao: str = "falta") -> None:
        self.itens.append(Item("ok" if ok else senao, rotulo, detalhe, "" if ok else dica))


def diagnosticar(cfg: Config, *, testar_busca: bool = True) -> list[Grupo]:
    from . import api

    grupos: list[Grupo] = []

    g = Grupo("config", "Configuração")
    g.add(True, "Config lida", str(cfg.vault))
    g.add(cfg.vault.is_dir(), "Vault existe", str(cfg.vault), "confira o caminho em config.toml")
    grupos.append(g)

    g = Grupo("ollama", "Ollama")
    est = ollama.estado(cfg.ollama_url, timeout=8)
    g.add(est["ok"], "Serviço respondendo", cfg.ollama_url,
          "abra o app do Ollama, ou rode 'ollama serve'")
    if est["ok"]:
        modelo = ollama.achar(est, cfg.model)
        g.add(modelo is not None, f"Modelo {cfg.model} baixado", "",
              f"rode: ollama pull {cfg.model}")
        if modelo is not None:
            g.add(modelo["carregado"],
                  "Modelo carregado na memória" if modelo["carregado"]
                  else "Modelo descarregado da memória",
                  "primeira busca instantânea" if modelo["carregado"] else "",
                  "a primeira busca paga ~30–60 s de recarga. "
                  "OLLAMA_KEEP_ALIVE evita isso.",
                  senao="aviso")
        if cfg.rerank_model:
            juiz = ollama.achar(est, cfg.rerank_model)
            g.add(juiz is not None, f"Juiz {cfg.rerank_model} baixado",
                  "só roda na faixa média",
                  f"rode: ollama pull {cfg.rerank_model}. Sem ele, a busca "
                  "sai sem o julgamento, como antes do reranker.",
                  senao="aviso")
    grupos.append(g)

    g = Grupo("indice", "Índice")
    try:
        info = api.index_status(cfg)
    except Exception as exc:
        g.add(False, "Índice legível", str(exc), "rode: vault-vector index")
        grupos.append(g)
        return grupos
    existe = (info.get("files") or 0) > 0
    g.add(existe, f"{info.get('files', 0)} notas, {info.get('chunks', 0)} trechos, "
                  f"{info.get('db_mb', 0)} MB",
          f"última indexação: {info.get('last_index') or 'nunca'}",
          "rode: vault-vector index")
    pend = info.get("pending", 0)
    g.add(pend == 0, "Nenhuma nota pendente" if pend == 0 else f"{pend} notas pendentes",
          "", "rode 'vault-vector index' ou espere a reindexação agendada",
          senao="aviso")
    modelo_indice = info.get("model")
    if modelo_indice and modelo_indice != cfg.model:
        g.add(False, f"Índice feito com {modelo_indice}, config pede {cfg.model}",
              "vetores de modelos diferentes não se comparam",
              "rode: vault-vector index --force")
    grupos.append(g)

    if testar_busca and existe:
        g = Grupo("busca", "Busca")
        try:
            hits = api.search(cfg, "rede servidor backup", top_k=2, expand=False)
            g.add(bool(hits), f"Consulta de teste devolveu {len(hits)} resultado(s)",
                  "", "o índice pode estar vazio")
            if hits:
                semantico = any(h.vec_rank is not None for h in hits)
                literal = any(h.fts_rank is not None for h in hits)
                lados = " + ".join(n for n, on in (("semântico", semantico),
                                                   ("literal", literal)) if on)
                g.add(semantico, f"Lados ativos: {lados}", "",
                      "só literal: o Ollama não respondeu e a busca caiu para "
                      "o modo degradado", senao="aviso")
        except Exception as exc:
            g.add(False, "Busca", str(exc))
        grupos.append(g)

    g = Grupo("escrita", "Escrita")
    hist = cfg.vault / "_historico"
    copias = len(list(hist.rglob("*.md"))) if hist.is_dir() else 0
    g.add(True, "Histórico em _historico/",
          f"{hist} ({copias} cópias)" if copias else f"{hist} (ainda vazio)")
    g.add(os.access(cfg.vault, os.W_OK), "Vault gravável", "", "confira as permissões da pasta")
    grupos.append(g)

    return grupos


def problemas(grupos: list[Grupo]) -> list[Item]:
    return [i for g in grupos for i in g.itens if i.status == "falta"]


def como_dict(grupos: list[Grupo]) -> list[dict]:
    return [asdict(g) for g in grupos]
