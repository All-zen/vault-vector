"""Cria um vault novo, com as convencoes que a busca sabe aproveitar.

Existe para quem nao tem nada: sem isto, a ferramenta so serve a quem ja usa
Obsidian ha tempo. E uma pasta vazia tambem nao resolve - o ranking deste
projeto aproveita convencoes concretas (pasta de diario com nome datado, nota
de indice, secoes na raiz), e vault que nasce sem elas cresce torto.

As notas criadas aqui sao esqueleto e explicacao, nunca conteudo de ninguem.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

INDICE = """# Indice

Mapa deste vault. Toda nota nova entra aqui embaixo, na secao a que pertence.

## Como isto esta organizado

| Pasta | Para que serve |
|---|---|
| `99-Diario/` | Registro datado: o que aconteceu, quando. Nome do arquivo comeca com a data (`AAAA-MM-DD-assunto.md`) |
| `Projetos/` | Uma pasta por projeto, cada uma com seu `00-MOC.md` |
| `Referencias/` | O que voce consulta mas nao escreveu: resumos, recortes, links comentados |

## Convencoes que a busca entende

Nao sao regras de estilo - o ranking usa cada uma delas:

- **Data no nome do arquivo**, em `99-Diario/`, e tratada como a data do
  evento. Pergunta com recorte temporal ("o que decidi em agosto") promove
  essas notas.
- **`00-MOC.md` e `00-INDICE.md`** sao mapas de conteudo. Sao rebaixados em
  pergunta factual e promovidos em pergunta de navegacao, porque lista de
  links raramente e a resposta.
- **Titulos (`##`)** delimitam os trechos indexados. Nota com titulos rende
  busca melhor que parede de texto.
- **Wikilinks** (`[[nota]]`) contam: nota muito referenciada sobe um pouco no
  ranking. Prefira o caminho completo quando houver nomes repetidos entre
  pastas: `[[Projetos/algo/00-MOC|Algo]]`.

## Notas

- [[99-Diario/{hoje}-primeiro-dia|{hoje} — Primeiro dia]]
- [[Projetos/00-MOC|Projetos]]
"""

PRIMEIRO_DIA = """# {hoje} — Primeiro dia

Vault criado hoje. Esta nota existe para o indice nao nascer vazio e para
servir de exemplo do formato de diario.

## O que vale registrar aqui

Decisao tomada e o motivo, problema que apareceu e como foi resolvido, coisa
que voce quer lembrar daqui a seis meses e nao vai. O valor nao esta em
escrever bonito - esta em ter escrito.

## Uma coisa que ajuda

Escreva o **porque**, nao so o **que**. "Troquei para Postgres" envelhece mal;
"troquei para Postgres porque o SQLite travava com duas escritas simultaneas"
responde a pergunta que voce vai fazer depois.
"""

PROJETOS_MOC = """# Projetos — MOC

Mapa dos projetos. Cada projeto ganha uma subpasta com seu proprio `00-MOC.md`.

## Ativos

_(nenhum ainda)_

## Modelo para um projeto novo

Crie `Projetos/nome-do-projeto/00-MOC.md` com:

- o que e, em uma frase
- estado atual
- decisoes tomadas e o motivo de cada uma
- links para as notas de detalhe
"""

REFERENCIAS = """# Referencias

O que voce consulta mas nao escreveu: resumo de artigo, recorte de
documentacao, link comentado.

## Por que resumir em vez de so guardar o link

Link morre e pagina muda. Um paragrafo seu dizendo o que aquilo resolvia
sobrevive aos dois, e e o que a busca vai encontrar.
"""


def criar_vault(destino: Path) -> list[str]:
    """Escreve o esqueleto. Nao toca em arquivo que ja exista."""
    hoje = date.today().isoformat()
    arquivos = {
        "00-INDICE.md": INDICE.format(hoje=hoje),
        f"99-Diario/{hoje}-primeiro-dia.md": PRIMEIRO_DIA.format(hoje=hoje),
        "Projetos/00-MOC.md": PROJETOS_MOC,
        "Referencias/00-MOC.md": REFERENCIAS,
    }
    criados = []
    for rel, conteudo in arquivos.items():
        caminho = destino / rel
        if caminho.exists():
            continue
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(conteudo, encoding="utf-8")
        criados.append(rel)
    return criados
