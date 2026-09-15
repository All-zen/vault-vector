"""Descobre sozinho como o vault esta organizado, e escreve isso em prosa.

Existe para o servidor MCP nao precisar de uma descricao escrita a mao. Sem
isto, ou o codigo carrega a estrutura do vault de quem escreveu (e vaza os
assuntos dele para quem clonar), ou quem instala precisa redigir a descricao
antes de a ferramenta servir para alguma coisa. As duas saidas sao ruins.

O texto gerado vai nas instructions do MCP: e o que faz o modelo saber navegar
um vault que ele nunca viu, sem ninguem explicar.
"""

from __future__ import annotations

import re
from collections import Counter

# Nome de pasta que marca registro datado, em portugues e ingles. Vault de
# quem escreve diario costuma ter uma dessas, com nomes AAAA-MM-DD dentro.
_PADROES_DIARIO = re.compile(r"(?i)^(99[-_])?(diario|daily|journal|log|dailies)$")
_NOME_DATADO = re.compile(r"^\d{4}-\d{2}-\d{2}")
_NOME_INDICE = re.compile(r"(?i)^(00[-_])?(moc|index|indice|pipeline|mapa)\b")


def _rotulo(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def perfilar(store) -> dict:
    """Le o indice e devolve os fatos que descrevem a organizacao do vault."""
    linhas = store.conn.execute(
        "SELECT path, section, note_kind, n_chunks FROM files WHERE n_chunks > 0"
    ).fetchall()
    if not linhas:
        return {"secoes": [], "total": 0, "diarios": [], "indices": 0, "subpastas": {}}

    por_secao: Counter = Counter()
    subpastas: dict[str, Counter] = {}
    diarios: set[str] = set()
    indices = 0

    for r in linhas:
        secao = r["section"] or "(raiz)"
        por_secao[secao] += 1
        partes = r["path"].replace("\\", "/").split("/")
        arquivo = partes[-1]
        datado = bool(_NOME_DATADO.match(arquivo))

        # O diario pode ser a propria secao (99-Diario/2026-09-15-x.md) ou uma
        # subpasta dentro dela (Trabalho/99-Diario/2026-09-15-x.md). Olhar so
        # subpasta perdia o primeiro caso, que e justamente o de vault novo.
        if len(partes) > 2:
            sub = partes[1]
            subpastas.setdefault(secao, Counter())[sub] += 1
            if _PADROES_DIARIO.match(sub) or datado:
                diarios.add(f"{secao}/{sub}")
        elif _PADROES_DIARIO.match(secao) or datado:
            diarios.add(secao)

        if r["note_kind"] == "indice" or _NOME_INDICE.match(arquivo):
            indices += 1

    return {
        "secoes": por_secao.most_common(),
        "total": sum(por_secao.values()),
        "diarios": sorted(diarios),
        "indices": indices,
        "subpastas": {s: c.most_common(4) for s, c in subpastas.items()},
    }


def descrever(store, nome_vault: str = "") -> str:
    """Monta as instructions do MCP a partir do que o vault realmente tem.

    Descreve estrutura e convencoes - nunca o conteudo. O modelo precisa saber
    onde procurar, nao o que esta escrito; e assim a descricao serve a qualquer
    vault sem expor o assunto de nenhum.
    """
    p = perfilar(store)
    if not p["total"]:
        return (
            "Busca num vault de notas em markdown. O indice esta vazio - rode "
            "'vault-rag index' antes de usar."
        )

    onde = f" em {nome_vault}" if nome_vault else ""
    out = [
        f"Busca e escrita num vault de notas markdown{onde}, com "
        f"{_rotulo(p['total'], 'nota', 'notas')} indexadas. A pessoa que usa este "
        "vault costuma perguntar em vez de abrir a nota, entao consulte antes de "
        "dizer que nao sabe algo sobre o trabalho dela.",
        "",
        "SECOES (use como filtro 'section' quando o assunto for obvio):",
    ]
    for secao, n in p["secoes"][:12]:
        detalhe = ""
        subs = p["subpastas"].get(secao)
        if subs:
            nomes = ", ".join(s for s, _ in subs[:3])
            detalhe = f" — subpastas: {nomes}"
        out.append(f"  {secao}  ({_rotulo(n, 'nota', 'notas')}){detalhe}")

    if p["diarios"]:
        out += [
            "",
            "REGISTRO DATADO: " + ", ".join(p["diarios"][:6]),
            "  A data no nome do arquivo e a data do EVENTO, e vem marcada no "
            "resultado. Confira antes de tratar algo como atual.",
        ]
    if p["indices"]:
        out += [
            "",
            f"MAPAS DE CONTEUDO: {p['indices']} nota(s) de indice (MOC/INDEX). "
            "Boas para navegar, ruins como resposta factual - o ranking ja "
            "rebaixa essas em pergunta factual e promove em pergunta de "
            "navegacao.",
        ]

    out += [
        "",
        "COMO USAR:",
        "  1. vault_search localiza. Funciona para pergunta conceitual e para "
        "identificador exato (hostname, IP, codigo de erro), porque funde busca "
        "semantica e literal.",
        "  2. vault_read quando o trecho nao bastar.",
        "  3. vault_list para navegar sem saber o caminho.",
        "  4. vault_edit altera trecho, vault_append acrescenta, vault_write cria "
        "nota nova. As tres reindexam sozinhas.",
        "  5. vault_move renomeia corrigindo wikilinks; vault_delete manda para a "
        "lixeira do historico.",
        "",
        "CONFIANCA DO RESULTADO:",
        "  Cada busca vem classificada em alta, media ou baixa, com a "
        "similaridade crua. Faixa BAIXA significa que nada no vault tem relacao "
        "com a pergunta - diga isso, em vez de responder por conhecimento geral. "
        "Faixa MEDIA e a zona onde pergunta legitima com outro vocabulario e "
        "pergunta sem resposta se confundem: leia o trecho e decida, em vez de "
        "assumir que responde por ter vindo no topo.",
        "",
        "  Cite sempre o caminho da nota, para a origem poder ser conferida.",
    ]
    return "\n".join(out)
