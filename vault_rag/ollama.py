"""Perguntas administrativas ao Ollama: esta de pe, que modelos tem, baixar.

embed.py e rerank.py falam com o Ollama para fazer o trabalho. Este modulo
responde a quem administra - o doctor, a tela de saude, a tela de modelos - e
por isso nunca levanta excecao por servico fora do ar: "fora do ar" e uma
resposta valida aqui, nao um erro.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


def _get(url: str, caminho: str, timeout: float) -> dict:
    with urllib.request.urlopen(f"{url.rstrip('/')}{caminho}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def mesmo_modelo(pedido: str, instalado: str) -> bool:
    """'bge-m3' casa com 'bge-m3:latest'; 'qwen2.5:3b' nao casa com 'qwen2.5:7b'."""
    if pedido == instalado:
        return True
    if ":" in pedido:
        return instalado == pedido or instalado == f"{pedido}:latest"
    return instalado.split(":")[0] == pedido


def estado(url: str, timeout: float = 5.0) -> dict:
    """Servico, versao e modelos instalados, com quem esta carregado na RAM.

    O tipo vem de 'capabilities' (embedding x completion) e as dimensoes de
    'embedding_length'. Versao antiga do Ollama que nao manda esses campos
    cai no palpite pelo nome, que e o que o doctor fazia antes.
    """
    inicio = time.perf_counter()
    try:
        tags = _get(url, "/api/tags", timeout)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"ok": False, "url": url, "ms": None, "versao": None,
                "erro": str(getattr(exc, "reason", exc)), "modelos": []}
    ms = round((time.perf_counter() - inicio) * 1000)

    carregados: dict[str, str | None] = {}
    versao = None
    try:
        for m in _get(url, "/api/ps", timeout).get("models", []):
            carregados[m.get("name", "")] = m.get("expires_at")
        versao = _get(url, "/api/version", timeout).get("version")
    except (urllib.error.URLError, OSError, ValueError):
        pass  # sem /api/ps o resto da resposta continua valendo

    modelos = []
    for m in tags.get("models", []):
        nome = m.get("name", "")
        det = m.get("details") or {}
        caps = m.get("capabilities") or []
        if caps:
            tipo = "embedding" if "embedding" in caps else "instrucao"
        else:
            tipo = "embedding" if "embed" in nome or det.get("family") == "bert" else "instrucao"
        modelos.append({
            "nome": nome,
            "tipo": tipo,
            "dims": det.get("embedding_length") if tipo == "embedding" else None,
            "bytes": m.get("size"),
            "parametros": det.get("parameter_size"),
            "quantizacao": det.get("quantization_level"),
            "carregado": nome in carregados,
            "expira": carregados.get(nome),
        })
    modelos.sort(key=lambda m: (m["tipo"] != "embedding", m["nome"]))
    return {"ok": True, "url": url, "ms": ms, "versao": versao, "erro": "", "modelos": modelos}


def achar(estado_: dict, pedido: str) -> dict | None:
    """O modelo instalado que atende ao nome pedido no config, se houver."""
    return next((m for m in estado_["modelos"] if mesmo_modelo(pedido, m["nome"])), None)


def baixar(url: str, nome: str, progresso=None, timeout: float = 30.0) -> None:
    """ollama pull, repassando o andamento a cada linha do stream.

    progresso(status, feito, total) recebe bytes quando o Ollama informa, e
    so o status nas fases sem tamanho (manifesto, verificacao).
    """
    corpo = json.dumps({"model": nome, "stream": True}).encode("utf-8")
    req = urllib.request.Request(
        f"{url.rstrip('/')}/api/pull", data=corpo,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    # O timeout vale por leitura, nao pelo download inteiro: um modelo de
    # 2 GB leva minutos, mas o Ollama manda linha de andamento o tempo todo.
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for linha in resp:
            if not linha.strip():
                continue
            evento = json.loads(linha.decode("utf-8"))
            if evento.get("error"):
                raise RuntimeError(evento["error"])
            if progresso:
                progresso(evento.get("status", ""), evento.get("completed"), evento.get("total"))
