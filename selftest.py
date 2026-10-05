"""Autoteste do vault-rag, sem precisar do Ollama.

Roda o pipeline inteiro (chunk -> embed -> store -> busca hibrida) num vault
sintetico, usando um embedder falso deterministico. Serve para confirmar que
a instalacao esta sa depois de mexer no codigo.

    python selftest.py
"""

from __future__ import annotations

import hashlib
import re
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

from vault_rag import embed as embed_mod

TOK = re.compile(r"[^\W_]+", re.UNICODE)


class _StubEmbedder:
    """Bag of hashed tokens: nao e semantico de verdade, mas e deterministico
    e suficiente para exercitar o caminho completo."""

    def __init__(self, *args, **kwargs):
        self.model = "stub"
        self.url = "stub://"
        self.batch_size = 16

    def check(self):
        return {"model": "stub"}

    def embed(self, texts):
        return [self._one(t) for t in texts]

    def embed_one(self, text):
        return self._one(text)

    def _one(self, text):
        vec = np.zeros(1024, dtype=np.float32)
        for tok in (t.lower() for t in TOK.findall(text)):
            vec[int(hashlib.md5(tok.encode()).hexdigest()[:8], 16) % 1024] += 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec


FIXTURES = {
    "infra/incidente-aps.md": (
        "# Incidente nos APs\n\n## Sintoma\n\nTodos os access points zeraram o uptime "
        "as 05h00.\n\n## Causa\n\nReboot programado no controlador UniFi.\n"
    ),
    "infra/backup-nas.md": (
        "# Arquitetura de backup\n\n## Cadeia do PBS\n\n```\nNAS -> NFS -> host -> CT213\n```\n\n"
        "## Ordem de desmontagem\n\n1. Desabilitar o job\n2. Parar o container\n"
    ),
    "dev/pool-esgotado.md": (
        "# Pool de conexoes esgotado\n\nO sistema saiu do ar porque o pool do banco "
        "estourou o limite de conexoes simultaneas.\n"
    ),
    "dev/tabela.md": "# Comparativo\n\n| opcao | preco |\n|---|---|\n"
    + "".join(f"| item {i} | {i * 100} |\n" for i in range(200)),
    "_to_delete/lixo.md": "# Lixo\n\nNao deve ser indexado jamais.\n",
    "vazio.md": "",
    "infra/00-MOC.md": (
        "# Mapa da secao\n\n- [[infra/incidente-aps|Incidente nos APs]]\n"
        "- [[infra/backup-nas|Backup]]\n- [[dev/pool-esgotado|Pool]]\n"
    ),
    "infra/99-Diario/2026-09-01-ronda.md": (
        "# Ronda de setembro\n\nVerificacao de rotina dos access points, tudo normal.\n"
    ),
    "curtinhas.md": (
        "# Curtas\n\n## A\n\nUma linha.\n\n## B\n\nOutra linha.\n\n"
        "## C\n\nMais uma linha curta que sozinha nao vale um chunk.\n"
    ),
}

CASOS = [
    ("por que os access points reiniciaram", "incidente-aps"),
    ("pool de conexoes do banco estourou", "pool-esgotado"),
    ("desmontar o NAS com seguranca", "backup-nas"),
]


def main() -> int:
    embed_mod.OllamaEmbedder = _StubEmbedder

    from vault_rag import api
    from vault_rag.config import Config
    from vault_rag.indexer import index_vault

    tmp = Path(tempfile.mkdtemp(prefix="vault-rag-selftest-"))
    falhas = []
    try:
        for rel, content in FIXTURES.items():
            f = tmp / "vault" / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content, encoding="utf-8")

        cfg = Config(vault=tmp / "vault", db_path=tmp / "index.db", model="stub")
        report = index_vault(cfg, verbose=False)
        print(f"indexacao: {report.as_text()}")

        def check(nome, condicao, detalhe=""):
            print(f"  {'ok  ' if condicao else 'FALHA'}  {nome}{'' if condicao else '  <- ' + detalhe}")
            if not condicao:
                falhas.append(nome)

        check("indexou as notas validas", report.indexed == 7, f"indexou {report.indexed}")
        check("ignorou _to_delete e arquivo vazio", report.skipped >= 1)
        check("sem erros na indexacao", not report.errors, str(report.errors[:3]))

        # Nota vazia nao rende chunk, mas tem que ficar REGISTRADA. Se nao
        # ficar, stale_files a devolve em toda passagem e a lista de pendentes
        # nunca esvazia - escondendo as pendencias de verdade atras do ruido.
        from vault_rag.indexer import stale_files

        pendentes = stale_files(cfg)
        check("nota vazia nao fica pendente para sempre",
              "vazio.md" not in pendentes, f"pendentes: {pendentes}")
        check("nada mais ficou pendente logo apos indexar",
              not pendentes, f"pendentes: {pendentes}")

        # O buraco achado em 15/09: pergunta que o vault NAO responde vinha
        # com score alto e sem nenhum aviso, porque o RRF so mede concordancia
        # entre rankers - e eles concordam com forca quando uma palavra da
        # pergunta existe no vault com outro sentido.
        # As faixas de confianca, testadas com os numeros reais medidos em
        # 15/09: ruido 0.387-0.527, parafrase legitima 0.435-0.607. As duas
        # populacoes se sobrepoem, entao a saida gradua em vez de cortar.
        check("similaridade alta -> sem ressalva",
              api.faixa_de_confianca(0.78, False) == "alta")
        check("pao de queijo (0.425) -> confianca baixa",
              api.faixa_de_confianca(0.425, False) == "baixa")
        check("zona de sobreposicao (0.507) -> confianca media",
              api.faixa_de_confianca(0.507, False) == "media")
        check("termo raro COM cobertura sobe para alta (busca por identificador)",
              api.faixa_de_confianca(0.461, True) == "alta",
              "busca por identificador sairia marcada como duvidosa")

        # Raridade sem cobertura e o oposto de evidencia: o termo casa em
        # poucos trechos porque NAO existe no vault. Em 15/09 isso mandou
        # "podar roseiras no inverno" (sim 0.414) para a faixa alta.
        check("cobertura total: termo do dominio aparece inteiro",
              api.cobertura_literal("PMTiles", "MapLibre + PMTiles proprio") == 1.0)
        check("cobertura parcial: so um termo casou por acaso",
              api.cobertura_literal("podar roseiras no inverno",
                                    "roteiro executavel no inverno") < 0.6)
        check("pergunta vazia nao inventa cobertura",
              api.cobertura_literal("de o a", "qualquer texto") == 0.0)
        check("raridade sem cobertura NAO vira faixa alta",
              api.faixa_de_confianca(0.414, False) == "baixa",
              "termo ausente do vault sairia sem ressalva")

        # A regra de raridade, com numeros diretos - depender do tamanho do
        # fixture foi o que escondeu o erro na primeira tentativa.
        check("termo raro em corpus grande: 5 de 4500 e identificador",
              api.termo_e_raro(5, 4500))
        check("termo comum em corpus grande: 80 de 4500 e palavra",
              not api.termo_e_raro(80, 4500))
        check("fracao, nao contagem: 3 de 7 e palavra comum daquele vault",
              not api.termo_e_raro(3, 7))
        check("sem dado do literal nao inventa raridade",
              not api.termo_e_raro(None, 4500))

        # E o texto que o modelo realmente le, nas tres faixas.
        from vault_rag.store import SearchHit

        def saida(faixa, sim):
            h = SearchHit(chunk_id=1, path="a.md", heading_path="X", text="t",
                          start_line=1, score=0.03, vec_rank=0, fts_rank=0,
                          confianca=faixa, top_sim_global=sim)
            return api.format_hits([h], snippet_chars=20)

        check("faixa baixa manda tratar como nao respondido",
              "CONFIANCA BAIXA" in saida("baixa", 0.425)
              and "nao responde isso" in saida("baixa", 0.425))
        check("faixa media manda ler antes de assumir",
              "CONFIANCA MEDIA" in saida("media", 0.507)
              and "se sobrepoem" in saida("media", 0.507))
        check("faixa alta nao poluiu a saida com ressalva",
              "CONFIANCA" not in saida("alta", None),
              "ressalva em busca boa vira ruido e para de ser lida")
        check("saida vazia instrui a dizer que nao achou",
              "nao tem trecho relacionado" in api.format_hits([]))

        # Vault criado do zero: o esqueleto tem que nascer indexavel e com as
        # convencoes que o ranking usa, senao quem comeca sem notas nenhuma
        # cria uma estrutura que a busca nao sabe aproveitar.
        from vault_rag.perfil import descrever
        from vault_rag.semente import criar_vault
        from vault_rag.store import Store

        novo_dir = Path(tempfile.mkdtemp(prefix="vault-novo-")) / "Notas"
        novo_dir.mkdir(parents=True)
        criados = criar_vault(novo_dir)
        check("semente cria o esqueleto", len(criados) >= 3, str(criados))
        check("semente nao sobrescreve o que ja existe",
              criar_vault(novo_dir) == [], "rodar duas vezes duplicaria conteudo")

        cfg_novo = Config(vault=novo_dir, db_path=novo_dir.parent / "n.db", model="stub")
        rep_novo = index_vault(cfg_novo, verbose=False)
        check("vault novo indexa sem erro",
              rep_novo.indexed >= 3 and not rep_novo.errors, rep_novo.as_text())

        store_novo = Store(cfg_novo.db_path, cfg_novo.embed_dim)
        try:
            perfil = descrever(store_novo, "Notas")
            check("o perfil detecta o diario do vault novo",
                  "REGISTRO DATADO" in perfil and "99-Diario" in perfil,
                  perfil[:160])
            check("o perfil detecta os mapas de conteudo",
                  "MAPAS DE CONTEUDO" in perfil)
            # O perfil so pode falar do vault que leu. Se citasse qualquer
            # secao que nao esta neste indice, seria estrutura embutida no
            # codigo - e ai o projeto carregaria o vault de quem o escreveu.
            secoes_reais = {"(raiz)", "99-Diario", "Projetos", "Referencias"}
            citadas = {
                l.strip().split("  ")[0]
                for l in perfil.split("SECOES")[1].split("REGISTRO")[0].splitlines()
                if l.strip() and l.startswith("  ")
            }
            check("o perfil so cita secoes que existem neste vault",
                  citadas <= secoes_reais, f"citou a mais: {citadas - secoes_reais}")
        finally:
            store_novo.close()
        shutil.rmtree(novo_dir.parent, ignore_errors=True)

        for query, alvo in CASOS:
            hits = api.search(cfg, query, top_k=3)
            check(f"busca: {query!r}", any(alvo in h.path for h in hits),
                  str([h.path for h in hits]))

        check("query vazia nao devolve nada", api.search(cfg, "") == [])
        check("query so com stopwords nao devolve nada", api.search(cfg, "de da o a") == [])

        # --- metadados derivados do caminho ---
        from vault_rag.meta import note_date, note_kind

        check("note_kind: MOC e indice", note_kind("infra/00-MOC.md") == "indice")
        check("note_kind: 00- sozinho nao e indice",
              note_kind("infra/00-Padroes-Software.md") == "nota",
              note_kind("infra/00-Padroes-Software.md"))
        check("note_kind: pasta de diario", note_kind("x/99-Diario/a.md") == "diario")
        check("note_kind: modulos vira spec", note_kind("x/modulos/a.md") == "spec")
        check("note_date: le data do nome",
              note_date("x/2026-09-01-ronda.md") is not None)
        check("note_date: sem data devolve None", note_date("x/nota.md") is None)

        import sqlite3
        con = sqlite3.connect(cfg.db_path)
        kinds = dict(con.execute("SELECT path, note_kind FROM files"))
        check("indexou o note_kind", kinds.get("infra/00-MOC.md") == "indice", str(kinds))

        # --- backlinks ---
        bl = dict(con.execute("SELECT path, backlinks FROM files"))
        check("backlinks contados do MOC", bl.get("infra/incidente-aps.md", 0) >= 1, str(bl))
        check("nota sem citacao fica em zero", bl.get("infra/00-MOC.md", 0) == 0)

        # --- chunks curtos fundidos ---
        tamanhos = [r[0] for r in con.execute(
            "SELECT LENGTH(text) FROM chunks WHERE path='curtinhas.md'")]
        check("secoes curtas viraram um chunk so", len(tamanhos) == 1, str(tamanhos))

        # --- caminho indexado no FTS ---
        achou = api.search(cfg, "incidente aps", top_k=3)
        check("busca pelo nome do arquivo funciona",
              any("incidente-aps" in h.path for h in achou), str([h.path for h in achou]))

        # --- small-to-big ---
        hits = api.search(cfg, "reboot programado controlador", top_k=1, expand=True)
        check("expand devolve pelo menos o proprio chunk",
              bool(hits) and len(hits[0].context_text) >= len(hits[0].text))
        hits_sem = api.search(cfg, "reboot programado controlador", top_k=1, expand=False)
        check("sem expand nao preenche context_text",
              bool(hits_sem) and hits_sem[0].context_text == "")

        # --- boost ---
        hits = api.search(cfg, "access points", top_k=5, expand=False)
        moc = [h for h in hits if h.note_kind == "indice"]
        check("nota-indice e penalizada em pergunta factual",
              all(h.boost < 1.0 for h in moc) if moc else True,
              str([(h.path, h.boost) for h in moc]))
        check("o motivo da penalidade vai junto com o hit",
              all(any("factual" in nome for nome, _ in h.fatores) for h in moc),
              str([h.fatores for h in moc]))
        check("o produto dos fatores e o boost",
              all(abs(np.prod([x for _, x in h.fatores]) - h.boost) < 0.01 for h in hits),
              str([(h.boost, h.fatores) for h in hits]))

        maior = max(len(h.text) for h in api.search(cfg, "comparativo item preco", top_k=10)) \
            if api.search(cfg, "comparativo item preco", top_k=10) else 0
        check("tabela grande foi fatiada dentro do limite", 0 < maior <= cfg.hard_max_chars + 50,
              f"maior chunk {maior}")

        hits = api.search(cfg, "cadeia do PBS", top_k=3)
        check("cerca de codigo balanceada", all(h.text.count("```") % 2 == 0 for h in hits))

        nota = api.read_note(cfg, "infra/backup-nas", heading="Cadeia do PBS")
        check("read por wikilink + heading", "NFS" in nota.get("content", ""), str(nota)[:120])

        try:
            api.read_note(cfg, "../../etc/passwd")
            check("path traversal bloqueado", False, "deixou passar")
        except ValueError:
            check("path traversal bloqueado", True)

        # --- escrita ---
        from vault_rag.writer import WriteError, append_note, edit_note, write_note

        r = edit_note(cfg, "infra/incidente-aps.md", "as 05h00", "as 05h10")
        check("edit troca o trecho",
              "05h10" in (cfg.vault / "infra/incidente-aps.md").read_text(encoding="utf-8"))
        check("edit guarda a versao anterior", r["historico"] is not None)
        check("edit reindexa na hora", "reindexado" in r["indice"], r["indice"])
        check("busca acha o texto recem-escrito",
              any("incidente-aps" in h.path for h in api.search(cfg, "05h10", top_k=3)))

        def recusa(nome, fn):
            try:
                fn()
                check(nome, False, "deixou passar")
            except (WriteError, ValueError):
                check(nome, True)

        recusa("edit recusa trecho inexistente",
               lambda: edit_note(cfg, "infra/incidente-aps.md", "nao existe isso", "x"))
        recusa("write recusa sobrescrever sem flag",
               lambda: write_note(cfg, "infra/incidente-aps.md", "# outro\n"))
        recusa("recusa escrever na lixeira",
               lambda: write_note(cfg, "_to_delete/x.md", "# lixo\n"))
        recusa("recusa escrever fora do vault",
               lambda: write_note(cfg, "../fora.md", "# fora\n"))
        recusa("recusa gravar sobre nota alterada por fora",
               lambda: edit_note(cfg, "infra/incidente-aps.md", "UniFi", "Ubiquiti",
                                 expected_mtime=1.0))

        # alvo ambiguo
        write_note(cfg, "infra/dup.md", "# Dup\n\n## A\n\nmesma linha\n\n## B\n\nmesma linha\n")
        recusa("edit recusa alvo que aparece duas vezes",
               lambda: edit_note(cfg, "infra/dup.md", "mesma linha", "outra"))
        r = edit_note(cfg, "infra/dup.md", "mesma linha", "outra", replace_all=True)
        check("replace_all troca todas", "substituiu 2" in r["acao"], r["acao"])

        r = append_note(cfg, "infra/99-Diario/2026-09-14-novo.md", "# Novo\n\nCriado por append.")
        check("append cria nota inexistente",
              (cfg.vault / "infra/99-Diario/2026-09-14-novo.md").is_file())
        check("nota criada entra no indice",
              any("2026-09-14-novo" in h.path for h in api.search(cfg, "criado por append", top_k=3)))

        # historico nao polui a busca nem colide
        for antes, depois in (("Criado por append", "Versao 2"), ("Versao 2", "Versao 3")):
            append_note(cfg, "infra/99-Diario/2026-09-14-novo.md", depois)
        copias = list((cfg.vault / "_historico").rglob("*.md"))
        check("historico acumula sem sobrescrever", len(copias) >= 4, f"{len(copias)} copias")
        check("historico fica fora da busca",
              not any("_historico" in h.path for h in api.search(cfg, "criado por append", top_k=8)))

        # --- navegar, mover, remover ---
        from vault_rag.writer import delete_note, list_dir, move_note

        r = list_dir(cfg, "infra")
        check("list_dir enumera a pasta", any(n["nome"].endswith(".md") for n in r["notas"]), str(r))
        recusa("list_dir recusa pasta bloqueada", lambda: list_dir(cfg, "_historico"))

        write_note(cfg, "infra/alvo.md", "# Alvo\n\nConteudo que sera movido.\n")
        write_note(cfg, "infra/aponta.md", "# Aponta\n\nVeja [[infra/alvo]] e tambem [[alvo|apelido]].\n")
        r = move_note(cfg, "infra/alvo.md", "infra/sub/alvo-novo.md")
        check("move o arquivo", (cfg.vault / "infra/sub/alvo-novo.md").is_file())
        check("corrige os wikilinks", r["links_atualizados"] == 1, str(r))
        aponta = (cfg.vault / "infra/aponta.md").read_text(encoding="utf-8")
        check("link curto e completo viram o caminho novo",
              aponta.count("infra/sub/alvo-novo") == 2, aponta)
        check("indice acompanha o caminho novo",
              any("alvo-novo" in h.path for h in api.search(cfg, "conteudo que sera movido", top_k=3)))
        recusa("move recusa destino ocupado",
               lambda: move_note(cfg, "infra/aponta.md", "infra/sub/alvo-novo.md"))

        r = delete_note(cfg, "infra/sub/alvo-novo.md")
        check("delete tira do vault", not (cfg.vault / "infra/sub/alvo-novo.md").exists())
        check("delete guarda na lixeira", (cfg.vault / r["lixeira"]).is_file(), str(r))
        check("delete avisa de quem ainda cita", r["citada_por"] >= 1, str(r))
        check("delete tira do indice",
              not any("alvo-novo" in h.path for h in api.search(cfg, "conteudo que sera movido", top_k=5)))

        segunda = index_vault(cfg, verbose=False)
        check("segunda indexacao e incremental", segunda.indexed <= 3,
              f"reindexou {segunda.indexed}")

        # ---------------------------------------------------- reranker local
        # Sem Ollama de proposito: o que precisa de teste aqui e a decisao de
        # faixa e a reordenacao, nao a qualidade do modelo. Qualidade se mede
        # com ferramentas/medir_rerank.py, contra o vault de verdade.
        from vault_rag.store import SearchHit as _SH

        original_juiz = api.OllamaJudge

        class _JuizFalso:
            def __init__(self, notas):
                self.notas = list(notas)

            def __call__(self, *a, **k):
                return self

            def nota(self, query, texto):
                return self.notas.pop(0) if self.notas else None

        def _hits():
            return [
                _SH(chunk_id=i, path=f"n{i}.md", heading_path="h", text=f"t{i}",
                    start_line=1, score=1.0 - i * 0.1, vec_rank=i, fts_rank=i,
                    vec_score=0.45, confianca="media")
                for i in range(3)
            ]

        cfg.rerank_model = "juiz-falso"
        try:
            for nome, notas, faixa_esp, ordem_esp in [
                # A decisao e pela MEDIA, nao pelo maximo: com 5 trechos e um
                # juiz generoso, ate pergunta fora do dominio acha um trecho
                # que tira 6, e o maximo deixa de separar. Medido em 15/09.
                ("rerank promove pela media alta", [3, 4, 5], "alta", [5, 4, 3]),
                ("uma nota alta sozinha NAO promove", [8, 0, 0], "media", [8, 0, 0]),
                ("rerank rebaixa quando a media e baixa", [0, 0, 1], "baixa", [1, 0, 0]),
                ("media no meio da escala continua media", [2, 3, 3], "media", [3, 3, 2]),
                ("juiz mudo nao muda a faixa", [None, None, None], "media", [None] * 3),
                ("juiz parcial decide com o que respondeu", [None, 7, 2], "alta", [7, 2, None]),
            ]:
                api.OllamaJudge = _JuizFalso(notas)
                hits = _hits()
                faixa = api.aplicar_rerank(cfg, "pergunta", hits)
                check(nome, faixa == faixa_esp and [h.rerank for h in hits] == ordem_esp,
                      f"faixa={faixa} ordem={[h.rerank for h in hits]}")

            # Nota fora da escala e resposta invalida, nao nota alta.
            from vault_rag.rerank import OllamaJudge as _OJ
            juiz = _OJ.__new__(_OJ)
            juiz.max_chars = 600
            for bruto, esperado in [("7", 7), (" 10 ", 10), ("100", None),
                                    ("sim", None), ("", None), ("nota: 3", 3)]:
                juiz._gerar = (lambda b: (lambda *a, **k: b))(bruto)
                check(f"juiz interpreta {bruto!r} como {esperado}",
                      juiz.nota("q", "t") == esperado)
        finally:
            api.OllamaJudge = original_juiz
            cfg.rerank_model = ""

        # --- diagnostico ---
        # CLI e tela de saude leem a mesma lista. Ollama fora do ar e o caso
        # que mais acontece na pratica, e tem que aparecer como falta, sem
        # derrubar o resto da checagem.
        from vault_rag import ollama
        from vault_rag.diagnostico import diagnosticar, problemas

        sem_ollama = Config(vault=cfg.vault, db_path=cfg.db_path, model="stub",
                            ollama_url="http://127.0.0.1:9")
        grupos = {g.id: g for g in diagnosticar(sem_ollama, testar_busca=False)}
        check("diagnostico: Ollama fora do ar e falta",
              grupos["ollama"].itens[0].status == "falta" and grupos["ollama"].itens[0].dica)
        check("diagnostico: o resto continua sendo checado",
              {"config", "indice", "escrita"} <= set(grupos))
        check("diagnostico: so o Ollama conta como problema",
              len(problemas(list(grupos.values()))) == 1,
              str([i.rotulo for i in problemas(list(grupos.values()))]))
        check("modelo sem tag casa com :latest", ollama.mesmo_modelo("bge-m3", "bge-m3:latest"))
        check("tag diferente NAO casa", not ollama.mesmo_modelo("qwen2.5:3b", "qwen2.5:7b"))

        # --- medicoes ---
        from vault_rag import medicao

        s = medicao.sugerir_limiar([0.38, 0.41, 0.52], [0.45, 0.58, 0.61, 0.66])
        check("limiar: populacoes que se sobrepoem pedem escolha",
              s["sobrepoe"] and s["conservador"] == 0.525 and s["perdidas_no_conservador"] == 1,
              str(s))
        s = medicao.sugerir_limiar([0.30, 0.35], [0.50, 0.60])
        check("limiar: sem sobreposicao, o meio do vao",
              not s["sobrepoe"] and s["sugerido"] == 0.425, str(s))
        check("limiar: amostra vazia nao inventa numero", medicao.sugerir_limiar([], [0.5]) is None)

        arq = tmp / "perguntas.txt"
        arq.write_text("# comentario\nREESCREVA ESTA COMO PERGUNTA | x\n"
                       "como copio os arquivos | backup-nas\n\n", encoding="utf-8")
        check("perguntas: pula comentario e linha nao reescrita",
              medicao.ler_perguntas(arq) == [("como copio os arquivos", "backup-nas")])

        medida = medicao.medir_calibracao(cfg, amostra=4)
        check("calibracao sem perguntas mede titulos",
              medida["fonte"] == "titulos" and len(medida["fora"]) == len(medicao.FORA_DO_VAULT)
              and 0 < len(medida["dentro"]) <= 4, str({k: medida[k] for k in ("fonte",)}))
        textos, total = medicao.amostra_de_trechos(cfg, 6)
        niveis = medicao.medir_paralelismo(cfg, textos, [1, 2])
        check("paralelismo mede cada nivel pedido",
              [r["paralelo"] for r in niveis] == [1, 2] and niveis[0]["ganho"] == 1.0, str(niveis))

        # --- tarefas em segundo plano ---
        import threading
        import time as _time

        from vault_rag.tarefas import Tarefas

        def esperar(tarefa, limite=30):
            fim = _time.time() + limite
            while tarefa.estado == "rodando" and _time.time() < fim:
                _time.sleep(0.02)
            return tarefa

        tarefas = Tarefas()
        (cfg.vault / "infra/nova-nota.md").write_text("# Nova\n\nTexto novo.\n", encoding="utf-8")
        t = esperar(tarefas.iniciar("indexar", lambda tf: index_vault(
            cfg, verbose=False,
            progress=lambda rel, rep: tf.andamento(rep.processadas, rep.total, rel)).as_text()))
        check("tarefa de indexacao termina com andamento completo",
              t.estado == "ok" and t.total == 1 and t.feito == 1, str(t.como_dict()))

        solta = threading.Event()
        lenta = tarefas.iniciar("medir", lambda tf: solta.wait(5))
        check("segundo clique devolve a tarefa que ja roda",
              tarefas.iniciar("medir", lambda tf: None) is lenta)
        solta.set()
        esperar(lenta)

        def quebra(tf):
            raise RuntimeError("Ollama sumiu")
        import contextlib
        import io

        with contextlib.redirect_stderr(io.StringIO()):  # o traceback e esperado
            falhou = esperar(tarefas.iniciar("x", quebra))
        check("erro na tarefa chega a quem consulta", falhou.erro == "Ollama sumiu")

        # --- gravacao do config ---
        # O config.toml e comentado a mao, e os comentarios explicam de onde
        # veio cada numero. Gravar pela interface nao pode apagar isso.
        from vault_rag.config import salvar

        alvo = tmp / "config.toml"
        alvo.write_text('vault = "x"\nparallel = 2   # medido\n# rerank_model = "a"\n',
                        encoding="utf-8")
        salvar({"parallel": 4, "rerank_model": "b", "rrf_k": 50}, alvo)
        gravado = alvo.read_text(encoding="utf-8")
        check("config: troca o valor e mantem o comentario", "parallel = 4   # medido" in gravado)
        check("config: chave documentada e descomentada no lugar",
              gravado.splitlines()[2] == 'rerank_model = "b"', gravado)
        check("config: chave nova vai para o fim", gravado.rstrip().endswith("rrf_k = 50"))
        try:
            salvar({"vault": 'quebra"'.replace('"', "\n")}, alvo)
            check("config: valor que quebraria o TOML nao e gravado", False, "gravou")
        except Exception:
            check("config: valor que quebraria o TOML nao e gravado",
                  alvo.read_text(encoding="utf-8") == gravado)

        # --- config viva ---
        # O app de desktop abre ANTES de existir vault, justamente para a
        # pessoa escolher um. Sem vault, o processo tem que ficar de pe e as
        # ferramentas recusarem com mensagem, em vez de SystemExit no import.
        import os

        from vault_rag import contexto

        guardado = {k: os.environ.get(k) for k in ("VAULT_RAG_CONFIG", "VAULT_RAG_VAULT")}
        try:
            os.environ["VAULT_RAG_CONFIG"] = str(tmp / "nao-existe.toml")
            os.environ.pop("VAULT_RAG_VAULT", None)
            check("sem vault, o contexto devolve None em vez de sair",
                  contexto.recarregar() is None and "Vault" in contexto.motivo())
            try:
                contexto.config()
                check("sem vault, pedir a config e erro comum", False, "nao recusou")
            except contexto.NaoConfigurado:
                check("sem vault, pedir a config e erro comum", True)
            os.environ["VAULT_RAG_VAULT"] = str(cfg.vault)
            check("com vault, recarregar pega a config nova",
                  contexto.recarregar() is not None and contexto.config().vault == cfg.vault)
        finally:
            for k, v in guardado.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            contexto.recarregar()

        # --- API da interface ---
        import logging
        import warnings

        warnings.filterwarnings("ignore", message=".*httpx.*")
        logging.getLogger("httpx").setLevel(logging.WARNING)  # uma linha por requisicao
        from starlette.testclient import TestClient

        from vault_rag.server import criar_app

        config_web = tmp / "config-web.toml"
        config_web.write_text(
            f'vault = "{cfg.vault.as_posix()}"\ndb_path = "{cfg.db_path.as_posix()}"\n'
            f'model = "stub"\nollama_url = "http://127.0.0.1:9"\n',
            encoding="utf-8",
        )
        guardado = os.environ.get("VAULT_RAG_CONFIG")
        os.environ["VAULT_RAG_CONFIG"] = str(config_web)
        contexto.recarregar()
        try:
            app = criar_app(token="t0ken")
            web = TestClient(app, base_url="http://127.0.0.1:8765")
            H = {"Authorization": "Bearer t0ken"}

            # As tres travas: cada uma fecha um caminho diferente.
            check("web: Host de outro dominio e negado (DNS rebinding)",
                  TestClient(app, base_url="http://evil.example:8765")
                  .get("/api/estado", headers=H).status_code == 403)
            check("web: sem token e negado", web.get("/api/estado").status_code == 401)
            check("web: escrita vinda de outra origem e negada",
                  web.post("/api/indexar", headers={**H, "Origin": "http://evil.example"})
                  .status_code == 403)
            check("web: /saude responde sem token e se identifica",
                  web.get("/saude").json().get("app") == "vault-vector")

            e = web.get("/api/estado", headers=H).json()
            check("web: estado conta as notas", e["configurado"] and e["notas"] >= 7, str(e)[:120])

            b = web.get("/api/buscar", params={"q": "access points"}, headers=H).json()
            check("web: busca devolve hits com o boost decomposto",
                  b["hits"] and all("fatores" in h for h in b["hits"]), str(b)[:120])

            n = web.get("/api/nota", params={"caminho": "infra/backup-nas"}, headers=H).json()
            check("web: nota vem com trechos e quem cita",
                  n["path"] == "infra/backup-nas.md" and n["trechos"]
                  and "infra/00-MOC.md" in n["citada_por"], str(n)[:160])

            velho = web.post("/api/nota", headers=H, json={
                "caminho": n["path"], "conteudo": n["conteudo"] + "\nnovo\n", "mtime": n["mtime"] - 60})
            check("web: mtime velho vira 409 de conflito",
                  velho.status_code == 409 and velho.json()["codigo"] == "conflito")
            ok = web.post("/api/nota", headers=H, json={
                "caminho": n["path"], "conteudo": n["conteudo"] + "\nlinha nova\n", "mtime": n["mtime"]})
            versoes = ok.json()["nota"]["versoes"]
            check("web: gravar guarda a versao anterior", ok.status_code == 200 and versoes,
                  ok.text[:160])
            volta = web.post("/api/nota/restaurar", headers=H, json={
                "caminho": n["path"], "versao": versoes[0]["versao"],
                "mtime": ok.json()["nota"]["mtime"]})
            check("web: restaurar traz o texto de volta",
                  volta.status_code == 200 and volta.json()["nota"]["conteudo"] == n["conteudo"],
                  volta.text[:160])

            check("web: config recusa chave que nao se ajusta",
                  web.post("/api/config", headers=H, json={"valores": {"vault": "x"}})
                  .status_code == 400)
            r = web.post("/api/config", headers=H, json={"valores": {"rrf_k": 42}}).json()
            check("web: config gravada vale na hora",
                  r["valores"]["rrf_k"] == 42 and contexto.config().rrf_k == 42)
        finally:
            if guardado is None:
                os.environ.pop("VAULT_RAG_CONFIG", None)
            else:
                os.environ["VAULT_RAG_CONFIG"] = guardado
            contexto.recarregar()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if falhas:
        print(f"\n{len(falhas)} falha(s): {', '.join(falhas)}")
        return 1
    print("\ntudo certo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
