# vault-vector

Busca semântica e escrita nas suas notas markdown, expostas ao Claude como MCP server. Roda inteiro na sua máquina: os embeddings saem do Ollama, o índice é um arquivo SQLite, nada sai para a nuvem. Independe do Obsidian estar aberto.

```
vault-vector init
```

Um comando, dois caminhos:

**Já tem notas?** Ele encontra seus vaults do Obsidian, checa o Ollama, escreve a configuração, indexa e mostra como conectar ao Claude Code e ao Claude Desktop.

**Não tem nada ainda?** Ele cria o vault para você, já com a estrutura que a busca sabe aproveitar: pasta de diário com data no nome, MOC por seção, títulos como fronteira de trecho. É uma pasta de markdown comum — abra no Obsidian depois, se quiser, ou nunca abra e deixe o Claude escrever nela por você.

---

## O que faz

**Busca híbrida.** Similaridade vetorial e busca literal (FTS5) fundidas por Reciprocal Rank Fusion. Funciona tanto para pergunta conceitual ("como decidi o particionamento das VLANs") quanto para identificador exato (hostname, IP, código de erro), porque os dois lados cobrem falhas diferentes um do outro.

**Escrita com rede de segurança.** Sete ferramentas MCP: editar trecho, acrescentar, criar nota, mover, apagar, listar, reindexar. Toda gravação copia a versão anterior para `_historico/` antes de escrever. Mover uma nota reescreve os wikilinks que apontavam para ela.

**Se descreve sozinho.** O servidor lê o próprio índice e monta a descrição do vault para o modelo: seções, subpastas, convenções de diário e de índice. Nenhuma estrutura fica embutida no código, então não é preciso escrever nada para o modelo saber navegar um vault que nunca viu.

**Diz quando não sabe.** É a parte que levou mais trabalho, e está explicada abaixo.

**Serve para começar do zero.** Não pressupõe que você já tenha um vault, nem que use Obsidian. Se quiser só uma memória persistente para o Claude escrever e consultar, `init` monta isso em um comando.

---

## O problema que a maioria dos RAG caseiros tem

Um sistema de busca por similaridade sempre devolve os `top_k` trechos mais parecidos. Se a pergunta não tem resposta no corpus, ele devolve os menos distantes, com a mesma cara de quem acertou. Quem consome os trechos — um modelo de linguagem — responde a partir deles.

O caso que expôs isso neste projeto: a pergunta **"receita de pão de queijo mineiro"**, sobre um vault de infraestrutura e desenvolvimento, tirou o **maior score da sessão** — acima de perguntas cuja resposta estava lá. Devolveu planilhas de produção de laticínio, porque a palavra "receita" existia no vault com outro sentido, e os dois rankers concordaram com força.

O score do RRF mede concordância entre rankers, não relevância. Ele não distingue "os dois acertaram" de "os dois erraram junto".

### O que não resolveu

**Piso de similaridade.** A primeira correção foi cortar resultados abaixo de um limiar de cosseno. Medindo:

| População | faixa de similaridade |
|---|---|
| Pergunta sem resposta no vault | 0,387 – 0,527 |
| Pergunta legítima com vocabulário diferente do das notas | 0,435 – 0,607 |

As duas se sobrepõem em quase toda a extensão. Qualquer corte único ou deixa passar ruído ou recusa pergunta boa. Com o piso em 0,55, três de cinco perguntas legítimas verificáveis foram recusadas, incluindo uma cuja nota correta viria em primeiro lugar.

**Corte binário é a ferramenta errada quando as distribuições se sobrepõem.**

### O que resolveu

O resultado sai sempre, classificado em três faixas, e a incerteza vai junto em vez de ser decidida no escuro:

| Faixa | Critério | Saída |
|---|---|---|
| alta | ≥ 0,60, ou termo raro com cobertura | sem ressalva |
| média | 0,43 – 0,60 | *"esta faixa contém tanto pergunta legítima com outro vocabulário quanto pergunta que o vault não responde; leia o trecho e decida"* |
| baixa | < 0,43 | *"trate como o vault não responde isso"* |

Medido em 8 perguntas legítimas com vocabulário trocado contra 8 perguntas fora do domínio:

| | alta | média | baixa |
|---|---|---|---|
| **legítima** | 2 | 6 | **0** |
| **ruído** | **0** | 5 | 3 |

As duas pontas ficam limpas: nenhuma resposta correta desencorajada, nenhum ruído entregue sem ressalva. A faixa média concentra 69% dos casos e é quase cara ou coroa — o que é a medida direta de quanta informação a similaridade de vetor não carrega, e o argumento quantificado para um reranker cross-encoder, que lê pergunta e trecho juntos.

Os números acima são do vault onde o projeto nasceu. Eles mudam com o idioma, o assunto e o tamanho do corpus:

```
vault-vector calibrar          # mede as duas populações no seu vault
vault-vector testar-confianca  # matriz de confusão das faixas
```

---

## Decisões de projeto

| Ponto | Escolha | Por quê |
|---|---|---|
| Banco vetorial | SQLite + numpy | ~4.500 trechos dão 22 MB de matriz e o produto escalar leva menos de 1 ms. Extensão nativa quebra no Windows, e isso é custo permanente por ganho nenhum nessa escala |
| Recorte | fronteira de heading | Tabela e bloco de código nunca partidos no meio; tabela grande repete o cabeçalho em cada pedaço |
| Contexto do trecho | caminho + título + trilha de headings + lead | Contextual retrieval sem custo de LLM: o trecho isolado não diz de onde veio |
| Devolução | small-to-big | Embedda o trecho pequeno, devolve a seção inteira: precisão na busca, contexto na leitura |
| Reindexação | reuso de vetor por hash | Editar uma linha manda um trecho ao modelo, não a nota toda |
| Metadados | derivados do caminho | Frontmatter é raro na prática; a convenção de pastas é o que existe de verdade |

---

## Requisitos

- Python 3.11+
- [Ollama](https://ollama.com/download) com um modelo de embedding (`ollama pull bge-m3`)
- Notas em markdown (ou nenhuma — o `init` cria)

Testado no Windows. O código é portátil; os scripts de serviço (`.ps1`) são específicos do Windows.

---

## Comandos

```
vault-vector init                 instala do zero
vault-vector index                incremental; --force reindexa tudo
vault-vector search "termo"       busca pela linha de comando
vault-vector stats                total, pendências, seções
vault-vector doctor               checa Ollama, índice, busca e escrita
vault-vector calibrar             mede as faixas de confiança no seu vault
vault-vector testar-confianca     matriz de confusão das faixas
vault-vector serve --http         um processo servindo todos os clientes MCP
python selftest.py                ~60 checagens, não precisa do Ollama
```

---

## Limites conhecidos

- Indexa só `.md`. PDF, imagem, anexo e `.canvas` ficam de fora.
- Sem reranking. O piso cobre o caso grosseiro; o fino (similaridade alta e o trecho mesmo assim não responder) depende de um cross-encoder, que custa torch ou llama.cpp separado.
- `top_k` preenche o resultado até o limite, então as últimas posições podem ser enchimento.
- Reindexação em lote pelo MCP pode estourar o tempo limite do cliente. Para lote, use o CLI.

## Licença

MIT.
