#!/usr/bin/env python3
"""Falha se dado de vault real vazar para o repositorio.

Roda no CI a cada push. Existe porque este projeto nasceu dentro de um vault
com notas de trabalho e de cliente: caminho absoluto, nome de empresa e
estrutura de pastas reais entraram no codigo mais de uma vez durante o
desenvolvimento, e revisao a olho nao pega isso de forma confiavel.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Nao e lista de palavras proibidas: sao FORMAS de vazamento.
PADROES = [
    (r"[A-Za-z]:\\\\(?!caminho|CAMINHO|ferramentas|Users\\\\seu)[A-Za-z_]", "caminho absoluto do Windows"),
    (r"/home/(?!runner|usuario)[a-z][a-z0-9_-]*/", "caminho absoluto de usuario"),
    (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "endereco IP"),
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "e-mail"),
    (r"(?i)\b(?:token|senha|password|secret|api[_-]?key)\s*[=:]\s*[\"'][^\"'\s]{12,}", "credencial literal"),
    (r"(?i)\bsk-[A-Za-z0-9]{16,}", "chave de API"),
]

# Onde o padrao e legitimo: documentacao que precisa mostrar o formato.
PERMITIDO = {
    "endereco IP": re.compile(r"127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d+\.\d+/24"),
    "e-mail": re.compile(r"noreply@|exemplo\.com|example\.com"),
}

IGNORAR_DIR = {".git", ".venv", "__pycache__", ".github", "node_modules"}
EXTENSOES = {".py", ".toml", ".md", ".ps1", ".yml", ".yaml", ".json", ".txt", ".cfg"}


def main() -> int:
    achados = []
    for caminho in sorted(RAIZ.rglob("*")):
        if not caminho.is_file() or caminho.suffix not in EXTENSOES:
            continue
        if any(parte in IGNORAR_DIR for parte in caminho.parts):
            continue
        if caminho.name == "verificar_vazamento.py":
            continue  # os proprios padroes casariam consigo mesmos
        rel = caminho.relative_to(RAIZ)
        try:
            texto = caminho.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for n, linha in enumerate(texto.splitlines(), 1):
            for padrao, rotulo in PADROES:
                for m in re.finditer(padrao, linha):
                    escape = PERMITIDO.get(rotulo)
                    if escape and escape.search(m.group(0)):
                        continue
                    achados.append((rel, n, rotulo, m.group(0)[:60], linha.strip()[:80]))

    if not achados:
        print("nenhum vazamento encontrado")
        return 0

    print(f"{len(achados)} possivel(is) vazamento(s):\n")
    for rel, n, rotulo, trecho, linha in achados:
        print(f"  {rel}:{n}  [{rotulo}]  {trecho}")
        print(f"      {linha}")
    print("\nSe algum for falso positivo, ajuste PERMITIDO em", __file__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
