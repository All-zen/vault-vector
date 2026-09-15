"""Chunking de markdown consciente da estrutura de uma nota Obsidian.

Regras que importam neste vault:
  - quebra preferencialmente em fronteira de heading, acumulando o caminho
    de headings ("Titulo > Secao > Subsecao");
  - tabelas markdown e blocos de codigo sao atomicos: nunca sao cortados no
    meio. Tabela grande demais e quebrada por linhas, repetindo o cabecalho;
  - secoes curtas consecutivas sao fundidas, para MOC e indice nao virarem
    dezenas de chunks de duas linhas;
  - o texto do chunk preserva as linhas de heading, entao nada de contexto
    se perde mesmo quando secoes sao fundidas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
TABLE_ROW_RE = re.compile(r"^\s*\|")
WIKILINK_RE = re.compile(r"\[\[([^\]\|#]+)(?:#[^\]\|]*)?(?:\|[^\]]*)?\]\]")
TAG_RE = re.compile(r"(?:^|[\s(\[])#([A-Za-zÀ-ÿ][\w\-/]{1,60})")


@dataclass
class Chunk:
    ord: int
    heading_path: str
    text: str
    start_line: int


@dataclass
class ParsedNote:
    title: str
    lead: str
    frontmatter: str
    tags: list[str]
    links: list[str]
    chunks: list[Chunk]


@dataclass
class _Block:
    """Unidade atomica: nunca cortada, exceto tabela gigante."""

    kind: str  # heading | table | code | text
    lines: list[str]
    start_line: int
    level: int = 0  # so para heading

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def size(self) -> int:
        return len(self.text) + 1


def split_frontmatter(raw: str) -> tuple[str, str, int]:
    """Devolve (frontmatter, corpo, linhas_consumidas)."""
    if not raw.startswith("---"):
        return "", raw, 0
    lines = raw.split("\n")
    if lines[0].strip() != "---":
        return "", raw, 0
    for i in range(1, min(len(lines), 200)):
        if lines[i].strip() in ("---", "..."):
            fm = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :])
            return fm, body, i + 1
    return "", raw, 0


def _frontmatter_tags(fm: str) -> list[str]:
    """Parser tolerante: pega 'tags: [a, b]', 'tags: a b' e lista com hifen."""
    tags: list[str] = []
    lines = fm.split("\n")
    for idx, line in enumerate(lines):
        key, sep, value = line.partition(":")
        if not sep or key.strip().lower() not in ("tags", "tag"):
            continue
        value = value.strip()
        if value:
            value = value.strip("[]")
            tags += [t.strip().strip("'\"#") for t in re.split(r"[,\s]+", value) if t.strip()]
        for follow in lines[idx + 1 :]:
            stripped = follow.strip()
            if stripped.startswith("-"):
                tags.append(stripped.lstrip("-").strip().strip("'\"#"))
            elif stripped:
                break
    return [t for t in tags if t]


def _blocks(body: str, line_offset: int) -> list[_Block]:
    """Quebra o corpo em blocos atomicos."""
    lines = body.split("\n")
    blocks: list[_Block] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        lineno = line_offset + i + 1

        if not line.strip():
            i += 1
            continue

        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            buf = [line]
            i += 1
            while i < n:
                buf.append(lines[i])
                if lines[i].strip().startswith(marker):
                    i += 1
                    break
                i += 1
            blocks.append(_Block("code", buf, lineno))
            continue

        heading = HEADING_RE.match(line)
        if heading:
            blocks.append(_Block("heading", [line], lineno, level=len(heading.group(1))))
            i += 1
            continue

        if TABLE_ROW_RE.match(line):
            buf = []
            while i < n and TABLE_ROW_RE.match(lines[i]):
                buf.append(lines[i])
                i += 1
            blocks.append(_Block("table", buf, lineno))
            continue

        # paragrafo / lista / citacao: linhas ate a proxima linha em branco
        # ou o inicio de um bloco de outro tipo.
        buf = []
        while i < n and lines[i].strip():
            if HEADING_RE.match(lines[i]) or TABLE_ROW_RE.match(lines[i]) or FENCE_RE.match(lines[i]):
                break
            buf.append(lines[i])
            i += 1
        if buf:
            blocks.append(_Block("text", buf, lineno))

    return blocks


def _split_table(block: _Block, limit: int) -> list[_Block]:
    """Quebra tabela grande repetindo cabecalho e separador em cada pedaco."""
    lines = block.lines
    header = lines[:2] if len(lines) > 2 else lines[:1]
    header_size = sum(len(x) + 1 for x in header)
    out: list[_Block] = []
    buf: list[str] = []
    size = header_size
    for line in lines[len(header) :]:
        if buf and size + len(line) + 1 > limit:
            out.append(_Block("table", header + buf, block.start_line))
            buf = []
            size = header_size
        buf.append(line)
        size += len(line) + 1
    if buf:
        out.append(_Block("table", header + buf, block.start_line))
    return out or [block]


def _split_code(block: _Block, limit: int) -> list[_Block]:
    """Quebra bloco de codigo grande, refechando a cerca em cada pedaco."""
    lines = block.lines
    opener = lines[0]
    marker = opener.strip()[:3]
    body = lines[1:]
    if body and body[-1].strip().startswith(marker):
        body = body[:-1]

    out: list[_Block] = []
    buf: list[str] = []
    size = len(opener) + len(marker) + 2
    for line in body:
        if buf and size + len(line) + 1 > limit:
            out.append(_Block("code", [opener, *buf, marker], block.start_line))
            buf = []
            size = len(opener) + len(marker) + 2
        buf.append(line)
        size += len(line) + 1
    if buf:
        out.append(_Block("code", [opener, *buf, marker], block.start_line))
    return out or [block]


def _split_text(block: _Block, limit: int) -> list[_Block]:
    """Quebra bloco de texto por linhas, ultimo recurso."""
    out: list[_Block] = []
    buf: list[str] = []
    size = 0
    for line in block.lines:
        if buf and size + len(line) + 1 > limit:
            out.append(_Block("text", buf, block.start_line))
            buf = []
            size = 0
        buf.append(line)
        size += len(line) + 1
    if buf:
        out.append(_Block("text", buf, block.start_line))
    return out or [block]


def _merge_short(chunks: list[Chunk], min_chars: int, target_chars: int) -> list[Chunk]:
    """Funde chunk curto no anterior quando couber.

    Chunk curto tem pouco sinal: o vetor acaba dominado por duas ou tres
    palavras e recupera mal. Como o texto preserva as linhas de heading, a
    fusao nao perde a informacao de secao - so o heading_path do bloco
    absorvido, que ja esta escrito dentro do proprio texto.
    """
    out: list[Chunk] = []
    for chunk in chunks:
        if out and len(chunk.text) < min_chars:
            previous = out[-1]
            if len(previous.text) + len(chunk.text) + 2 <= target_chars:
                previous.text = f"{previous.text}\n\n{chunk.text}"
                continue
        out.append(chunk)
    for i, chunk in enumerate(out):
        chunk.ord = i
    return out


def _heading_path(stack: list[tuple[int, str]]) -> str:
    return " > ".join(title for _, title in stack)


def chunk_markdown(
    raw: str,
    *,
    target_chars: int = 2400,
    hard_max_chars: int = 6000,
    min_chars: int = 600,
) -> ParsedNote:
    fm, body, consumed = split_frontmatter(raw)
    blocks = _blocks(body, consumed)

    # normaliza blocos que estouram o limite duro
    normalized: list[_Block] = []
    for block in blocks:
        if block.size <= hard_max_chars or block.kind == "heading":
            normalized.append(block)
        elif block.kind == "table":
            normalized += _split_table(block, hard_max_chars)
        elif block.kind == "code":
            normalized += _split_code(block, hard_max_chars)
        else:
            normalized += _split_text(block, hard_max_chars)

    chunks: list[Chunk] = []
    stack: list[tuple[int, str]] = []
    buf: list[_Block] = []
    buf_path = ""
    buf_start = 1

    def flush() -> None:
        nonlocal buf, buf_path, buf_start
        if not buf:
            return
        # nao emite chunk que so tem headings
        if all(b.kind == "heading" for b in buf):
            buf = []
            return
        text = "\n\n".join(b.text for b in buf).strip()
        if text:
            chunks.append(Chunk(len(chunks), buf_path, text, buf_start))
        buf = []

    def buf_size() -> int:
        return sum(b.size + 1 for b in buf)

    for block in normalized:
        if block.kind == "heading":
            level = block.level
            # heading novo fecha o chunk atual, a menos que o acumulado ainda
            # esteja curto demais para valer um chunk proprio.
            if buf and buf_size() >= min_chars:
                flush()
            while stack and stack[-1][0] >= level:
                stack.pop()
            title = HEADING_RE.match(block.lines[0]).group(2)
            stack.append((level, title))
            if not buf:
                buf_path = _heading_path(stack)
                buf_start = block.start_line
            buf.append(block)
            continue

        if not buf:
            buf_path = _heading_path(stack)
            buf_start = block.start_line

        if buf_size() + block.size > target_chars and buf_size() >= min_chars:
            flush()
            buf_path = _heading_path(stack)
            buf_start = block.start_line

        buf.append(block)

        if buf_size() >= hard_max_chars:
            flush()

    flush()
    chunks = _merge_short(chunks, min_chars, target_chars)

    match = re.search(r"^#\s+(.*\S)\s*$", body, re.MULTILINE)
    title = match.group(1) if match else ""

    # Lead: as primeiras linhas de conteudo da nota. Quase toda nota daqui
    # abre com um paragrafo de contexto ou um blockquote de status, e isso
    # situa qualquer trecho do meio do documento de graca - o mesmo efeito do
    # contextual retrieval, sem chamar um LLM por chunk.
    lead_partes: list[str] = []
    tamanho = 0
    for bloco in normalized:
        if bloco.kind == "heading":
            continue
        if bloco.kind not in ("text", "table"):
            break
        trecho = bloco.text.strip()
        if not trecho:
            continue
        lead_partes.append(trecho)
        tamanho += len(trecho)
        if tamanho >= 240:
            break
    lead = " ".join(" ".join(lead_partes).split())[:260]

    tags = sorted(set(_frontmatter_tags(fm)) | set(TAG_RE.findall(body)))
    links = sorted({m.strip() for m in WIKILINK_RE.findall(body) if m.strip()})

    return ParsedNote(
        title=title, lead=lead, frontmatter=fm, tags=tags, links=links, chunks=chunks
    )
