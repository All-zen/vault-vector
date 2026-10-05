#!/usr/bin/env python3
"""Cria um vault de demonstracao, com notas ficticias.

Existe por dois motivos. As screenshots do README precisam de conteudo que
nao seja o vault de ninguem - o verificar_vazamento.py pega caminho e IP, mas
nao pega assunto, e um print do vault real contaria mais do que deveria. E
quem quer experimentar o app antes de apontar para as proprias notas precisa
de alguma coisa para buscar.

As notas seguem as convencoes que o ranking aproveita: diario com data no
nome, MOC por secao, titulos como fronteira de trecho, wikilinks.

    python ferramentas/vault_demo.py CAMINHO
"""

from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

NOTAS: dict[str, str] = {
    "00-INDICE.md": """# Índice

Mapa do vault. Cada seção tem o seu MOC.

- [[Homelab/00-MOC|Homelab]] — servidor de casa, rede, backup
- [[Projetos/00-MOC|Projetos]] — o que estou construindo
- [[Estudos/00-MOC|Estudos]] — anotações de leitura e cursos
- Diário em `99-Diario/`, uma nota por acontecimento
""",
    "Homelab/00-MOC.md": """# Homelab — MOC

O servidor de casa, a rede e o que roda em cima.

- [[Homelab/Servidor]] — o mini PC e os containers
- [[Homelab/Rede]] — segmentação e Wi-Fi
- [[Homelab/Backup]] — estratégia 3-2-1 com restic
- [[Homelab/Runbook-Restauracao]] — do SSD morto ao servidor no ar
- [[Homelab/Monitoramento]] — Uptime Kuma e alertas
""",
    "Homelab/Servidor.md": """# Servidor

Mini PC com 32 GB de RAM e um SSD de 1 TB, ligado 24 horas. Consome uns
12 W em repouso, o que pesou mais na escolha do que desempenho.

## Containers

Tudo sobe por um único `docker-compose.yml` versionado no Git. Serviços:

| Serviço | Para quê | Porta |
|---|---|---|
| Jellyfin | filmes e séries da família | 8096 |
| Paperless-ngx | documentos escaneados, com OCR | 8000 |
| Uptime Kuma | monitora tudo, inclusive ele mesmo | 3001 |
| Caddy | proxy reverso com HTTPS interno | 443 |

## Por que não Kubernetes

Considerei k3s e desisti. Para uma máquina só, o custo de operar o
cluster é maior que o ganho: o compose sobe tudo em segundos e eu entendo
cada linha dele. A regra que ficou: só complico quando a dor aparecer.
""",
    "Homelab/Rede.md": """# Rede

## Segmentação

Três redes separadas no roteador: a principal, a de IoT e a de convidados.
As lâmpadas e a TV ficam na de IoT, sem acesso à principal. Convidado só
sai para a internet.

O motivo foi uma câmera barata que ficava varrendo a rede inteira. Separar
custou uma tarde de configuração e acabou com o problema de vez.

## Wi-Fi

Dois access points em modo mesh, um em cada andar. O de cima ficava
derrubando os clientes até eu fixar o canal em 5 GHz no 36 e baixar a
potência — os dois APs estavam brigando entre si.

Ver também [[99-Diario/2026-09-08-wifi-caindo]].

## DNS

AdGuard Home no servidor resolve os nomes internos (`jellyfin.casa`,
`docs.casa`) e bloqueia propaganda para a casa toda.
""",
    "Homelab/Backup.md": """# Backup

Regra 3-2-1: três cópias, em duas mídias, uma fora de casa.

## Como está montado

1. O servidor faz snapshot diário com **restic** para o NAS.
2. Toda madrugada o NAS sincroniza o repositório restic com um bucket na
   nuvem, criptografado do lado de cá.
3. Uma vez por mês, um HD externo recebe uma cópia e vai para a gaveta
   do escritório.

## Teste de restauração

Backup que nunca foi restaurado é só esperança. Todo primeiro domingo do
mês restauro uma pasta aleatória e comparo o hash com a original.

## O que já deu errado

Em agosto o job parou de rodar por duas semanas sem ninguém perceber: a
senha do repositório tinha mudado e o script engolia o erro. Detalhes em
[[99-Diario/2026-08-12-backup-parado]]. Desde então o job manda alerta
para o Uptime Kuma quando falha.
""",
    "Homelab/Runbook-Restauracao.md": """# Runbook — restaurar o servidor do zero

Passo a passo para quando o SSD do servidor morrer. Testado em julho com
um SSD reserva: do zero ao Jellyfin no ar levou 1h40.

## Antes de começar

Precisa de três coisas à mão, e nenhuma delas pode estar só no servidor:

- a senha do repositório restic, que fica no gerenciador de senhas;
- o pendrive com o instalador do Debian, na gaveta do rack;
- acesso ao NAS pela rede, que é de onde vem o backup.

Se o NAS também tiver morrido, a cópia é a do bucket na nuvem. Ela é mais
lenta para baixar, mas é a mesma: o NAS só espelha o repositório.

## Instalar o sistema

Debian estável, instalação mínima, sem ambiente gráfico. Na partição,
usar o disco inteiro com LVM: aumentar volume depois é bem mais simples.

Depois do primeiro boot, o mínimo para o resto do runbook funcionar:

```
apt install -y restic docker.io docker-compose-plugin
usermod -aG docker admin
```

Configurar o IP fixo antes de qualquer outra coisa. O DNS da casa inteira
aponta para este servidor, e sem ele no ar ninguém na rede resolve nome.

## Restaurar os dados

O restic restaura direto para a raiz. Os volumes dos containers voltam
com o dono certo porque o restic guarda o uid numérico.

```
export RESTIC_REPOSITORY=sftp:nas.casa:/backup/servidor
restic snapshots
restic restore latest --target /
```

Conferir o tamanho restaurado contra o do snapshot antes de seguir. Da
última vez faltava uma pasta inteira por causa de uma regra de exclusão
esquecida no script de backup.

## Subir os serviços

Todos sobem pelo mesmo compose, que veio junto na restauração.

| Ordem | Serviço | Por que nessa ordem |
|---|---|---|
| 1 | AdGuard Home | sem DNS, os outros não acham uns aos outros |
| 2 | Caddy | o HTTPS interno depende do DNS |
| 3 | Paperless-ngx | o mais demorado para subir, por causa do OCR |
| 4 | Jellyfin | o último: é o que a família nota primeiro |
| 5 | Uptime Kuma | volta a vigiar tudo, inclusive o backup |

```
cd /srv && docker compose up -d adguard caddy
docker compose up -d
```

## Conferir

O serviço estar de pé não quer dizer que ele está certo. A lista que
importa:

1. `jellyfin.casa` abre e mostra a biblioteca inteira, não vazia;
2. um documento recente aparece buscável no Paperless;
3. o Uptime Kuma recebe o heartbeat do backup na madrugada seguinte;
4. o primeiro backup depois da restauração termina sem erro.

O item 4 é o que mais pega: o restic estranha o host novo e cria uma
cadeia de snapshots separada. Rodar `restic snapshots --host` para ver.

## O que faria diferente

Na próxima vez, guardar a configuração do roteador junto com o backup do
servidor. Refazer as reservas de DHCP de cabeça levou mais tempo do que
restaurar os dados.
""",
    "Homelab/Monitoramento.md": """# Monitoramento

Uptime Kuma checa cada serviço a cada minuto e manda notificação no
celular quando algo cai.

## Heartbeat do backup

Além dos serviços, o script de backup chama uma URL de heartbeat no fim de
cada execução. Se o Kuma não recebe o sinal em 26 horas, avisa. É o que
pega o caso silencioso — o job que nem chegou a rodar.

## Disco

Alerta quando qualquer volume passa de 85%. O NAS chegou a 97% uma vez por
causa de snapshots antigos que a política de retenção não estava podando.
""",
    "Projetos/00-MOC.md": """# Projetos — MOC

- [[Projetos/Caderneta/00-MOC|Caderneta]] — app de finanças pessoais
- [[Projetos/Site-Pessoal/00-MOC|Site pessoal]] — blog estático
""",
    "Projetos/Caderneta/00-MOC.md": """# Caderneta — MOC

App de finanças pessoais para a família: lança gasto pelo celular, vê o
mês por categoria, sem mandar extrato bancário para empresa nenhuma.

- [[Projetos/Caderneta/Arquitetura]]
- [[Projetos/Caderneta/Decisoes]]
- [[Projetos/Caderneta/Importacao-OFX]]
""",
    "Projetos/Caderneta/Arquitetura.md": """# Caderneta — Arquitetura

## Visão geral

Backend em FastAPI, banco SQLite, frontend em React servido pelo próprio
backend. Um processo, um arquivo de banco, deploy com um `docker run`.

## Camadas

- `api/` recebe HTTP e valida com Pydantic
- `dominio/` tem as regras: categorização, orçamento, recorrência
- `repositorio/` é o único lugar que sabe SQL

O domínio não importa nada de fora. Trocar SQLite por Postgres mexeria só
no repositório.

## Sincronização offline

O app do celular grava local e sincroniza quando tem rede. Conflito é
resolvido por último-a-escrever-vence por campo, não por registro: duas
pessoas editando o mesmo gasto, uma o valor e outra a categoria, não
perdem nada.
""",
    "Projetos/Caderneta/Decisoes.md": """# Caderneta — Decisões

Registro de decisões, no formato contexto → decisão → consequência.

## 001 — SQLite em vez de Postgres

**Contexto.** Uma família, poucos milhares de lançamentos por ano.

**Decisão.** SQLite com WAL. Backup é copiar um arquivo.

**Consequência.** Sem servidor de banco para manter. Se um dia virar
produto com muitos usuários, a camada de repositório isola a troca.

## 002 — Sem microsserviços

**Contexto.** Eu sou o único desenvolvedor.

**Decisão.** Monólito modular. Fronteiras de módulo bem definidas valem
mais do que fronteiras de rede.

**Consequência.** Deploy simples, um log só, debug com breakpoint.

## 003 — Categorização por regra antes de IA

**Contexto.** 80% dos gastos se repetem: mercado, farmácia, combustível.

**Decisão.** Regras simples por descrição do lançamento primeiro; modelo
de linguagem só para o que sobrar.

**Consequência.** Rápido, explicável, e funciona sem internet.
""",
    "Projetos/Caderneta/Importacao-OFX.md": """# Caderneta — Importação de OFX

Os bancos exportam extrato em OFX, que é SGML disfarçado de XML. A
biblioteca padrão quebra com os arquivos de dois dos bancos que testei.

## O que funcionou

Parser próprio de umas 80 linhas: lê as tags de transação linha a linha e
ignora o resto. Testado com extratos reais (anonimizados) de quatro
bancos.

## Duplicatas

Importar o mesmo extrato duas vezes não pode duplicar lançamento. A chave
é o FITID do banco; quando o banco não manda FITID, uso hash de data +
valor + descrição.
""",
    "Projetos/Site-Pessoal/00-MOC.md": """# Site pessoal — MOC

Blog estático gerado com Astro, hospedado de graça.

- [[Projetos/Site-Pessoal/Deploy]]
""",
    "Projetos/Site-Pessoal/Deploy.md": """# Site pessoal — Deploy

Push na main dispara o build no CI e publica. Leva menos de um minuto.

## Domínio

O domínio aponta para o provedor de hospedagem estática. HTTPS automático.

## Por que estático

Sem servidor, sem banco, sem atualização de segurança para aplicar às 23h
de sexta. Comentários ficam de fora de propósito.
""",
    "Estudos/00-MOC.md": """# Estudos — MOC

- [[Estudos/Busca-Hibrida]] — vetor + texto, e como fundir
- [[Estudos/Embeddings]] — o que são, na prática
- [[Estudos/Designing-Data-Intensive-Applications]] — anotações do livro
""",
    "Estudos/Busca-Hibrida.md": """# Busca híbrida

Busca vetorial acha o que tem o mesmo sentido com outras palavras. Busca
literal (BM25) acha o identificador exato — o nome de um host, um código de
erro. Cada uma falha onde a outra acerta.

## Reciprocal Rank Fusion

Para juntar as duas listas sem precisar calibrar escalas diferentes, cada
documento recebe `1 / (k + posição)` em cada lista, e as notas somam. Com
k = 60 o topo de cada ranker não domina sozinho.

O que o RRF mede é **concordância** entre os rankers, não relevância. Se os
dois concordam num resultado errado, ele sobe com nota alta do mesmo jeito.
""",
    "Estudos/Embeddings.md": """# Embeddings

Um modelo de embedding transforma texto num vetor de algumas centenas ou
milhares de números. Textos de sentido parecido viram vetores próximos, e
a proximidade se mede pelo cosseno do ângulo entre eles.

## Na prática

- Normalizar os vetores deixa o cosseno igual ao produto escalar.
- Até centenas de milhares de vetores, força bruta com numpy resolve em
  milissegundos. Índice aproximado (HNSW) só depois disso.
- Trocar de modelo exige recalcular tudo: vetores de modelos diferentes
  não se comparam.

## Limite

Similaridade alta não quer dizer que o trecho responde a pergunta. Quer
dizer que fala do mesmo assunto.
""",
    "Estudos/Designing-Data-Intensive-Applications.md": """# Designing Data-Intensive Applications

Anotações do livro do Kleppmann.

## Cap. 3 — Armazenamento e recuperação

LSM-tree escreve rápido e compacta depois; B-tree lê rápido e escreve no
lugar. O SQLite usa B-tree. O write-ahead log existe para o banco
sobreviver a uma queda no meio da escrita.

## Cap. 5 — Replicação

Replicação assíncrona aceita perder as últimas escritas se o líder cair.
"Ler a própria escrita" é a garantia que o usuário sente falta primeiro.

## Cap. 9 — Consistência

Linearizabilidade custa latência. A maioria dos sistemas não precisa dela
em tudo — só em pontos como unicidade de nome de usuário.
""",
    "99-Diario/2026-08-12-backup-parado.md": """# 2026-08-12 — Backup parado há duas semanas

Fui restaurar um arquivo e o snapshot mais recente era de 29/07.

## Causa

Troquei a senha do repositório restic e esqueci de atualizar a variável no
script. O script rodava, o restic falhava, e o `|| true` no fim da linha
engolia o erro. Ninguém foi avisado.

## Correção

- Tirei o `|| true`.
- O script agora chama o heartbeat do Uptime Kuma só se tudo deu certo.
- Rodei o backup na mão e conferi a restauração de uma pasta.

Lição: erro silencioso em backup é o pior tipo de erro.
""",
    "99-Diario/2026-08-30-migracao-banco.md": """# 2026-08-30 — Migração do schema da Caderneta

Adicionei a coluna de recorrência nos lançamentos. Migração escrita à mão,
testada contra uma cópia do banco de produção antes.

Demorou 0,3 s em 4.200 lançamentos. O SQLite não precisa reescrever a
tabela para adicionar coluna com default nulo.
""",
    "99-Diario/2026-09-08-wifi-caindo.md": """# 2026-09-08 — Wi-Fi do andar de cima caindo

A TV perdia a conexão várias vezes por noite.

O analisador mostrou os dois APs no mesmo canal de 5 GHz, com potência
máxima, um ouvindo o outro. Fixei o de cima no canal 36 e o de baixo no
149, potência média nos dois.

Uma semana sem queda depois disso. Atualizei [[Homelab/Rede]].
""",
    "99-Diario/2026-09-21-ideia-leitura.md": """# 2026-09-21 — Ideia: lista de leitura que lembra de mim

Salvo artigo para ler depois e nunca leio. Ideia: um resumo semanal com os
três links salvos há mais tempo, com duas linhas de cada um.

Não é projeto ainda. Fica anotado.
""",
    "99-Diario/2026-10-01-revisao-mensal.md": """# 2026-10-01 — Revisão de setembro

## Fiz

- Backup com alerta de falha, testado
- Wi-Fi estável no andar de cima
- Importação de OFX da Caderneta com quatro bancos

## Não fiz

- Monitorar temperatura do NAS
- Escrever o post sobre busca híbrida

## Próximo mês

Prioridade é o post. A nota [[Estudos/Busca-Hibrida]] já tem metade.
""",
}


def _quando(rel: str, ordem: int, agora: float) -> float:
    """Data de edicao plausivel: o diario na data do nome, o resto espalhado.

    Sem isso todas as notas nascem editadas "agora", e o frescor do
    ranking e a lista de recentes ficam sem nada para mostrar.
    """
    m = re.search(r"(20\d\d)-(\d\d)-(\d\d)", rel)
    if m:
        return datetime(int(m[1]), int(m[2]), int(m[3]), 21, 30).timestamp()
    return agora - (2 + (ordem * 13) % 140) * 86400 - ordem * 3700


def criar(destino: Path) -> list[str]:
    criados = []
    agora = time.time()
    for ordem, (rel, conteudo) in enumerate(NOTAS.items()):
        alvo = destino / rel
        if alvo.exists():
            continue
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(conteudo, encoding="utf-8")
        quando = _quando(rel, ordem, agora)
        os.utime(alvo, (quando, quando))
        criados.append(rel)
    return criados


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 1
    destino = Path(sys.argv[1]).expanduser()
    criados = criar(destino)
    print(f"{len(criados)} nota(s) criada(s) em {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
