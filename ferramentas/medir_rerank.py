"""Distribuicao das notas do juiz, para escolher o corte com dado.

O corte de promocao foi definido em 15/09 com QUATRO pares e estava errado:
na medicao completa o juiz subiu 4 dos 5 ruidos da faixa media junto com as
legitimas. Amostra de quatro nao e amostra. Este script existe para nao
repetir isso: mede as duas populacoes inteiras e mostra, para cada corte
possivel, quantas legitimas subiriam e quantos ruidos subiriam junto.

Uso:
  set VAULT_RAG_CONFIG=C:\\Memorias\\_tools\\vault-rag\\config-rerank.toml
  python ferramentas/medir_rerank.py --perguntas perguntas.txt
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vault_rag import api
from vault_rag.config import load_config
from vault_rag.rerank import OllamaJudge

RUIDO = [
    "receita de pao de queijo mineiro",
    "route reflector do BGP",
    "como podar roseiras no inverno",
    "escalacao do Gremio na final de 1983",
    "dosagem de paracetamol para crianca",
    "preco do quilo do camarao rosa",
    "regra do roque no xadrez",
    "rede de protecao para varanda de apartamento",
]


def notas_da_pergunta(cfg, juiz, pergunta: str, top: int) -> tuple[list[int], float]:
    # rerank_model vazio: queremos os hits CRUS, e julgar por fora, para nao
    # medir a decisao de faixa que justamente esta em questao.
    guardado, cfg.rerank_model = cfg.rerank_model, ""
    try:
        hits = api.search(cfg, pergunta, top_k=top, expand=True)
    finally:
        cfg.rerank_model = guardado
    t0 = time.perf_counter()
    notas = [juiz.nota(pergunta, h.context_text or h.text) for h in hits]
    return [n for n in notas if n is not None], time.perf_counter() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--perguntas", required=True)
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()

    cfg = load_config()
    if not cfg.rerank_model:
        print("config sem rerank_model - use o config-rerank.toml", file=sys.stderr)
        return 1
    juiz = OllamaJudge(cfg.ollama_url, cfg.rerank_model, cfg.rerank_timeout, cfg.rerank_chars)
    if not juiz.disponivel():
        print(f"modelo {cfg.rerank_model} nao esta no Ollama", file=sys.stderr)
        return 1

    legitimas = []
    for linha in Path(args.perguntas).read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and not linha.startswith("REESCREVA"):
            legitimas.append(linha.partition("|")[0].strip())

    print(f"juiz {cfg.rerank_model} · top {args.top} · corte {cfg.rerank_chars} chars\n")
    resultado: dict[str, list[int]] = {}
    for rotulo, perguntas in (("legitima", legitimas), ("ruido", RUIDO)):
        print(f"{rotulo.upper()}")
        maximos = []
        for p in perguntas:
            notas, seg = notas_da_pergunta(cfg, juiz, p, args.top)
            melhor = max(notas) if notas else -1
            maximos.append(melhor)
            print(f"  max {melhor:>2}  notas {str(notas):22} {seg:5.1f}s  {p[:46]}")
        resultado[rotulo] = maximos
        print()

    print("Corte de promocao: quantas subiriam para alta em cada limiar")
    print("  corte  legitimas  ruidos   (de 8 cada)")
    for corte in range(4, 11):
        leg = sum(1 for m in resultado["legitima"] if m >= corte)
        rui = sum(1 for m in resultado["ruido"] if m >= corte)
        marca = "  <-- separa" if leg >= 5 and rui == 0 else ""
        print(f"  >= {corte:<3}    {leg}/8        {rui}/8{marca}")
    print("\nCorte de rebaixamento: quantas cairiam para baixa")
    print("  corte  legitimas  ruidos   (legitima aqui e erro)")
    for corte in range(0, 5):
        leg = sum(1 for m in resultado["legitima"] if m <= corte)
        rui = sum(1 for m in resultado["ruido"] if m <= corte)
        print(f"  <= {corte:<3}    {leg}/8        {rui}/8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
