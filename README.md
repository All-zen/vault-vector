# vault-vector

Busca semântica e escrita nas suas notas markdown, expostas ao Claude como MCP server. Roda inteiro na sua máquina: os embeddings saem do Ollama e o índice é um arquivo SQLite local. Funciona com o Obsidian fechado.

```
vault-vector init
```

Se você já tem notas, o `init` encontra seus vaults do Obsidian, checa o Ollama, escreve a configuração, indexa e mostra como conectar ao Claude Code e ao Claude Desktop.

Se você ainda não tem nenhuma, ele cria o vault com a estrutura que a busca sabe aproveitar: pasta de diário com data no nome, MOC por seção, títulos como fronteira de trecho. O que sai disso é uma pasta de markdown comum, que você pode abrir no Obsidian depois ou deixar só para o Claude escrever e consultar.

---

## O que faz

**Busca híbrida.** Similaridade vetorial e busca literal (FTS5) fundidas por Reciprocal Rank Fusion. Funciona tanto para pergunta conceitual ("como decidi o particionamento das VLANs") quanto para identificador exato (hostname, IP, código de erro), já que os dois lados cobrem falhas diferentes um do outro.

**Escrita com histórico.** Sete ferramentas MCP: editar trecho, acrescentar, criar nota, mover, apagar, listar, reindexar. Toda gravação copia a versão anterior para `_historico/` antes de escrever, e mover uma nota reescreve os wikilinks que apontavam para ela.

**Descrição automática do vault.** O servidor lê o próprio índice e monta para o modelo a descrição da estrutura: seções, subpastas, convenções de diário e de índice. Como nada disso fica embutido no código, o modelo consegue navegar um vault que nunca viu sem que você precise escrever instruções para ele.

**Sinalização de incerteza.** Foi a parte que levou mais trabalho e está explicada na seção seguinte.

**Uso sem vault prévio.** Não pressupõe que você já tenha notas nem que use Obsidian. Para quem quer apenas uma memória persistente onde o Claude escreve e consulta, o `init` monta isso em um comando.

---

## Quando o vault não tem a resposta

Um sistema de busca por similaridade sempre devolve os `top_k` trechos mais parecidos. Quando a pergunta não tem resposta no corpus, ele devolve os menos distantes com a mesma aparência de acerto, e o modelo de linguagem que lê esses trechos responde a partir deles.

O caso que expôs isso aqui foi a pergunta **"receita de pão de queijo mineiro"** contra um vault de infraestrutura e desenvolvimento: ela tirou o **maior score da sessão**, acima de perguntas cuja resposta estava no vault. O que voltou foram planilhas de produção de laticínio, porque a palavra "receita" existe no vault com outro sentido e os dois rankers concordaram com força. O score do RRF mede concordância entre rankers, e concordância não separa o caso em que os dois acertaram do caso em que os dois erraram junto.

### Piso de similaridade não resolveu

A primeira correção foi cortar resultados abaixo de um limiar de cosseno. Medindo as duas populações:

| População | faixa de similaridade |
|---|---|
| Pergunta sem resposta no vault | 0,387 – 0,527 |
| Pergunta legítima com vocabulário diferente do das notas | 0,435 – 0,607 |

As duas se sobrepõem em quase toda a extensão, então qualquer corte único ou deixa passar ruído ou recusa pergunta boa. Com o piso em 0,55, três de cinco perguntas legítimas verificáveis foram recusadas, uma delas com a nota correta em primeiro lugar.

### Faixas de confiança

O resultado sai sempre, classificado em três faixas, com a incerteza anexada a ele:

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

As duas pontas ficam limpas: nenhuma resposta correta desencorajada e nenhum ruído entregue sem ressalva. A faixa média concentra 69% dos casos com acerto perto de 50%, o que dá a medida de quanta informação a similaridade de vetor não carrega e justifica em número a etapa seguinte, um reranker cross-encoder que lê pergunta e trecho juntos.

Os números acima são do vault onde o projeto nasceu e mudam com o idioma, o assunto e o tamanho do corpus. Dois comandos refazem a medição no seu:

```
vault-vector calibrar          # mede as duas populações no seu vault
vault-vector testar-confianca  # matriz de confusão das faixas
```

---

## Decisões de projeto

| Ponto | Escolha | Por quê |
|---|---|---|
| Banco vetorial | SQLite + numpy | ~4.500 trechos dão 22 MB de matriz e o produto escalar leva menos de 1 ms. Extensão nativa quebra no Windows e não traz ganho mensurável nessa escala |
| Recorte | fronteira de heading | Tabela e bloco de código nunca partidos no meio; tabela grande repete o cabeçalho em cada pedaço |
| Contexto do trecho | caminho + título + trilha de headings + lead | O trecho isolado não diz de onde veio, e isso resolve sem custo de LLM |
| Devolução | small-to-big | Embedda o trecho pequeno e devolve a seção inteira, mantendo a precisão da busca sem perder contexto na leitura |
| Reindexação | reuso de vetor por hash | Editar uma linha reembedda só o trecho alterado |
| Metadados | derivados do caminho | Frontmatter é raro na prática, enquanto a convenção de pastas costuma estar lá |

---

## Requisitos

- Python 3.11+
- [Ollama](https://ollama.com/download) com um modelo de embedding (`ollama pull bge-m3`)
- Notas em markdown, ou nenhuma, já que o `init` cria o vault

Testado no Windows. O código é portátil, mas os scripts de serviço (`.ps1`) são específicos do Windows.

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
- Sem reranking. As faixas cobrem o caso grosseiro. O caso fino, em que a similaridade é alta e o trecho mesmo assim não responde, depende de um cross-encoder, que custa torch ou llama.cpp separado.
- O `top_k` completa o resultado até o limite pedido, então as últimas posições podem vir com score muito baixo.
- Reindexação em lote pelo MCP pode estourar o tempo limite do cliente. Para lote, use o CLI.

## Licença

MIT.
