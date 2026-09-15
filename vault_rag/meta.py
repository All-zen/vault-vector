"""Metadados derivados do caminho e do nome do arquivo.

Neste vault o frontmatter aparece em menos de 10% das notas e as tags sao
praticamente inexistentes, mas a convencao de nomenclatura e rigorosa e vale
para 100% dos arquivos. Entao o metadado confiavel vem do caminho:

    Trabalho/99-Diario/2026-07-26-auditoria-aps.md
    ^ secao            ^ tipo    ^ data      ^ assunto
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

DATE_IN_NAME = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")

# Nome de arquivo que denuncia nota de navegacao: mapa de conteudo, indice,
# pipeline. Otimas para achar o caminho, ruins como resposta factual - sao
# lista de links, nao conteudo.
INDEX_NAME = re.compile(
    r"(^|[-_ ])(MOC|INDEX|INDICE|VAULT|PIPELINE|README|HANDOFF|SUMARIO)([-_. ]|$)",
    re.IGNORECASE,
)

# Marcas de pasta -> tipo da nota, em ordem de precedencia.
FOLDER_KINDS = [
    (("99-diario", "99-daily", "diario", "daily"), "diario"),
    (("operacional", "incidentes", "runbook", "runbooks"), "operacional"),
    (("modulos", "core", "spec", "specs"), "spec"),
    (("pesquisa", "00-aprender", "exercicios", "recursos"), "pesquisa"),
    (("consultoria", "estrategias", "estrategia"), "estrategia"),
]

KINDS = ("indice", "diario", "operacional", "spec", "pesquisa", "estrategia", "nota")

# Marcas de pergunta temporal: "o que aconteceu recentemente", "ultima queda".
TEMPORAL_HINTS = {
    "recente", "recentes", "recentemente", "ultimo", "ultima", "ultimos",
    "ultimas", "último", "última", "últimos", "últimas", "ontem", "hoje",
    "agora", "atual", "atualmente", "novo", "nova", "aconteceu", "andamento",
    "semana", "mes", "mês", "latest", "recent", "hoje", "ainda",
}

# Marcas de pergunta de navegacao: aqui a nota-indice e exatamente o que serve.
NAV_HINTS = {
    "indice", "índice", "mapa", "moc", "sumario", "sumário", "estrutura",
    "organizacao", "organização", "visao", "visão", "geral", "lista",
    "listar", "quais", "onde", "overview",
}


def note_kind(rel_path: str) -> str:
    """Classifica a nota pelo caminho. Sempre devolve algo."""
    rel = rel_path.replace("\\", "/")
    name = rel.rsplit("/", 1)[-1]
    stem = name[:-3] if name.lower().endswith(".md") else name

    # Atencao: o prefixo "00-" NAO implica indice aqui. No vault ele marca
    # "documento de entrada da secao", e varios sao conteudo denso
    # (00-CONECTAR-CLAUDES, 00-METODO-PESQUISA-PRIMARIA, 00-Padroes-Software).
    # Só o nome explicito conta.
    if INDEX_NAME.search(stem):
        return "indice"

    partes = {p.lower() for p in rel.split("/")[:-1]}
    for marcas, kind in FOLDER_KINDS:
        if partes & set(marcas):
            return kind

    if DATE_IN_NAME.match(stem):
        return "diario"
    return "nota"


def note_date(rel_path: str) -> float | None:
    """Timestamp da data no nome do arquivo, quando houver.

    E a data do evento, diferente do mtime, que e a data da ultima edicao.
    Uma nota de incidente de julho editada ontem continua sendo de julho.
    """
    name = rel_path.replace("\\", "/").rsplit("/", 1)[-1]
    match = DATE_IN_NAME.search(name)
    if not match:
        return None
    try:
        ano, mes, dia = (int(g) for g in match.groups())
        return datetime(ano, mes, dia, tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def query_flags(query: str) -> tuple[bool, bool]:
    """(pergunta temporal?, pergunta de navegacao?)"""
    palavras = {w.lower() for w in re.findall(r"[^\W_]+", query, re.UNICODE)}
    return bool(palavras & TEMPORAL_HINTS), bool(palavras & NAV_HINTS)


def resolve_link(target: str, by_path: dict[str, str], by_stem: dict[str, list[str]]) -> str | None:
    """Resolve o alvo de um wikilink para um caminho real do vault."""
    alvo = target.replace("\\", "/").strip().strip("[]").split("#")[0].strip()
    if not alvo:
        return None
    for candidato in (alvo, f"{alvo}.md"):
        if candidato in by_path:
            return by_path[candidato]
    stem = alvo.rsplit("/", 1)[-1].lower()
    encontrados = by_stem.get(stem)
    # Nome ambiguo (o vault tem varios 00-MOC.md) nao conta como backlink:
    # atribuir ao arquivo errado e pior do que nao contar.
    if encontrados and len(encontrados) == 1:
        return encontrados[0]
    return None
