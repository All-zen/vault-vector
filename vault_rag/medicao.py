"""Medicoes feitas no vault de quem roda: paralelismo e calibracao.

Eram o corpo do 'bench' e do 'calibrar', que so imprimiam. Viraram funcoes
que devolvem os numeros, para as telas de modelos e de calibracao mostrarem
a mesma medicao que o terminal. Quem quer acompanhar passa um callback e
recebe cada resultado assim que sai - medir leva de segundos a minutos.

Os numeros certos dependem da maquina, do idioma e do vault. Nada aqui tem
limiar embutido: tudo e medido onde vai ser usado.
"""

from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .config import Config
from .embed import EmbeddingError, OllamaEmbedder

# Perguntas que o vault comprovadamente NAO responde. Escolhidas para nao
# compartilhar vocabulario com o dominio - e duas de proposito que
# compartilham ("receita", "rede"), porque sao esses os casos que enganam.
FORA_DO_VAULT = [
    "receita de pao de queijo mineiro",
    "route reflector do BGP",
    "como podar roseiras no inverno",
    "escalacao do Gremio na final de 1983",
    "dosagem de paracetamol para crianca",
    "conjugacao de verbo irregular em alemao",
    "preco do quilo do camarao rosa",
    "regra do roque no xadrez",
    "como trocar a correia dentada do carro",
    "rede de protecao para varanda de apartamento",
]


def _embedder(cfg: Config, num_thread: int = 0) -> OllamaEmbedder:
    return OllamaEmbedder(
        cfg.ollama_url, cfg.model, cfg.request_timeout, cfg.batch_size,
        num_thread=num_thread or cfg.num_thread,
    )


# ------------------------------------------------------------ paralelismo
def amostra_de_trechos(cfg: Config, quantos: int) -> tuple[list[str], int]:
    """Trechos reais do vault, cortados como a indexacao corta.

    Devolve tambem o total de notas, para estimar quanto a indexacao
    completa levaria na taxa medida.
    """
    from .chunker import chunk_markdown
    from .indexer import iter_notes

    textos: list[str] = []
    total_notas = 0
    for path, _rel in iter_notes(cfg):
        total_notas += 1
        if len(textos) < quantos:
            note = chunk_markdown(
                path.read_text(encoding="utf-8", errors="replace"),
                target_chars=cfg.target_chars,
                hard_max_chars=cfg.hard_max_chars,
                min_chars=cfg.min_chars,
            )
            textos += [c.text for c in note.chunks]
    return textos[:quantos], total_notas


def medir_paralelismo(
    cfg: Config,
    textos: list[str],
    niveis: list[int],
    *,
    num_thread: int = 0,
    ao_medir=None,
) -> list[dict]:
    """Trechos por segundo em cada nivel de paralelismo, com os mesmos textos.

    O primeiro nivel e a base do ganho. Antes de medir, aquece o modelo: a
    primeira chamada paga a carga na RAM e distorceria o nivel 1.
    """
    embedder = _embedder(cfg, num_thread)
    embedder.check()
    embedder.embed(textos[:2])

    resultados: list[dict] = []
    base = None
    for nivel in niveis:
        inicio = time.perf_counter()
        if nivel <= 1:
            embedder.embed(textos)
            chamadas = math.ceil(len(textos) / cfg.batch_size)
        else:
            fatias = [textos[i::nivel] for i in range(nivel)]
            with ThreadPoolExecutor(max_workers=nivel) as pool:
                list(pool.map(embedder.embed, fatias))
            chamadas = sum(math.ceil(len(f) / cfg.batch_size) for f in fatias)
        dt = time.perf_counter() - inicio
        base = base or dt
        r = {
            "paralelo": nivel,
            "chamadas": chamadas,
            "segundos": round(dt, 2),
            "taxa": round(len(textos) / dt, 2),
            "ganho": round(base / dt, 2),
        }
        resultados.append(r)
        if ao_medir:
            ao_medir(r)
    return resultados


def melhor_nivel(resultados: list[dict]) -> dict:
    return max(resultados, key=lambda r: r["taxa"])


def paralelismo_inutil(resultados: list[dict]) -> bool:
    """Ganho abaixo de 30%: o problema nao e falta de paralelismo."""
    melhor = melhor_nivel(resultados)
    return melhor["paralelo"] == 1 or melhor["ganho"] < 1.3


# ------------------------------------------------------------- calibracao
def ler_perguntas(caminho: Path) -> list[tuple[str, str]]:
    """Le 'pergunta | pedaco-do-caminho' por linha, pulando comentario e
    as linhas do modelo que ainda nao foram reescritas."""
    perguntas = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        pergunta, _, alvo = linha.partition("|")
        if pergunta.strip().startswith("REESCREVA"):
            continue
        perguntas.append((pergunta.strip(), alvo.strip()))
    return perguntas


def medir_calibracao(
    cfg: Config,
    *,
    amostra: int = 30,
    perguntas: list[str] | None = None,
    ao_medir=None,
) -> dict:
    """Melhor similaridade de cada pergunta, em duas populacoes.

    'fora' sao perguntas que o vault nao responde. 'dentro' sao perguntas
    que ele responde: as que a pessoa escreveu, quando existem, ou os
    titulos de notas reais. Titulo casa com a propria nota quase por
    construcao, entao mede o caso facil - por isso 'fonte' vai junto, para
    quem le saber qual das duas medicoes esta olhando.

    O score do resultado e RRF: diz que os dois rankers concordaram, nao
    que o trecho responde. A similaridade de cosseno crua e a unica medida
    absoluta do pipeline, e e ela que separa (ou nao) as duas populacoes.
    """
    from .store import Store

    store = Store(cfg.db_path, cfg.embed_dim)
    try:
        if perguntas:
            dentro, fonte = list(perguntas), "perguntas"
        else:
            rows = store.conn.execute(
                "SELECT title FROM files WHERE n_chunks > 0 AND title != ''"
                " ORDER BY RANDOM() LIMIT ?",
                (amostra,),
            ).fetchall()
            dentro, fonte = [r["title"] for r in rows], "titulos"
        if not dentro:
            raise ValueError("Indice vazio. Rode 'vault-vector index' primeiro.")

        embedder = _embedder(cfg)
        total = len(FORA_DO_VAULT) + len(dentro)
        feitos = 0

        def medir(lista: list[str], grupo: str) -> list[dict]:
            nonlocal feitos
            saida = []
            for q in lista:
                feitos += 1
                try:
                    sim = round(store.similaridade_maxima(embedder.embed_one(q)), 4)
                    item = {"grupo": grupo, "pergunta": q, "sim": sim}
                    saida.append(item)
                except EmbeddingError as exc:
                    item = {"grupo": grupo, "pergunta": q, "sim": None, "erro": str(exc)}
                if ao_medir:
                    ao_medir(item, feitos, total)
            return saida

        fora = medir(FORA_DO_VAULT, "fora")
        dentro_medido = medir(dentro, "dentro")
    finally:
        store.close()

    return {
        "fonte": fonte,
        "fora": fora,
        "dentro": dentro_medido,
        "sugestao": sugerir_limiar([i["sim"] for i in fora], [i["sim"] for i in dentro_medido]),
    }


def sugerir_limiar(fora: list[float], dentro: list[float]) -> dict | None:
    """Onde cortar, dadas as duas populacoes medidas.

    Sem sobreposicao, o meio do vao. Com sobreposicao, escolher o piso e
    trocar falso positivo por falso negativo: o conservador corta todo o
    ruido e perde algumas boas, o equilibrado mantem 90% das boas. Resposta
    errada com confianca e o pior dos dois erros.
    """
    if not fora or not dentro:
        return None
    fora_v, dentro_v = sorted(fora), sorted(dentro)
    teto_fora, piso_dentro = fora_v[-1], dentro_v[0]
    r = {
        "teto_fora": teto_fora,
        "mediana_fora": fora_v[len(fora_v) // 2],
        "piso_dentro": piso_dentro,
        "mediana_dentro": dentro_v[len(dentro_v) // 2],
        "sobrepoe": teto_fora >= piso_dentro,
    }
    if not r["sobrepoe"]:
        r["sugerido"] = round((teto_fora + piso_dentro) / 2, 3)
    else:
        r["conservador"] = round(teto_fora + 0.005, 3)
        r["equilibrado"] = round(dentro_v[max(0, len(dentro_v) // 10)], 3)
        r["perdidas_no_conservador"] = sum(1 for s in dentro_v if s < teto_fora + 0.005)
    return r
