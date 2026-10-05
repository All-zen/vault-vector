"""Linha de comando do vault-rag."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import unicodedata
from pathlib import Path

from . import api
from .config import load_config
from .indexer import index_vault


def cmd_index(args) -> int:
    cfg = load_config({"model": args.model, "ollama_url": args.ollama})
    print(f"Vault: {cfg.vault}\nIndice: {cfg.db_path}\nModelo: {cfg.model} @ {cfg.ollama_url}\n")
    report = index_vault(cfg, force=args.force, verbose=not args.quiet)
    print("\n" + report.as_text())
    if report.errors and report.indexed:
        print(
            f"\nConcluiu com {len(report.errors)} erro(s). O que entrou esta salvo — "
            "rode 'vault-rag index' de novo para pegar so o que faltou."
        )
    elif report.errors:
        print("\nA indexacao falhou. Veja a mensagem acima.")
    return 1 if report.errors else 0


def cmd_search(args) -> int:
    cfg = load_config({"model": args.model, "ollama_url": args.ollama})
    started = time.time()
    hits = api.search(
        cfg,
        args.query,
        top_k=args.top_k,
        section=args.section,
        lexical_only=args.lexical,
        max_per_file=args.max_per_file,
        expand=not args.no_expand,
    )
    if args.json:
        print(json.dumps([h.__dict__ for h in hits], ensure_ascii=False, indent=2))
    else:
        print(api.format_hits(hits, snippet_chars=args.snippet))
        print(f"\n_{len(hits)} resultado(s) em {time.time() - started:.2f}s_", file=sys.stderr)
    return 0


def cmd_read(args) -> int:
    cfg = load_config()
    result = api.read_note(cfg, args.path, args.heading)
    if "error" in result:
        print(result["error"], file=sys.stderr)
        return 1
    print(result["content"])
    return 0


def cmd_stats(args) -> int:
    cfg = load_config()
    info = api.index_status(cfg)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def _terminal(texto: str) -> str:
    """Tira acento e travessao do que vai para o terminal.

    O texto dos diagnosticos esta em portugues correto porque a interface
    mostra igual. No terminal, saida redirecionada sai em cp1252 e o
    PowerShell le em outra codificacao: "memória" vira "mem�ria".
    """
    texto = texto.replace("—", "-").replace("–", "-")
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def cmd_doctor(args) -> int:
    """Checa tudo que a busca precisa e diz o que fazer quando algo falta."""
    from .diagnostico import diagnosticar, problemas

    try:
        cfg = load_config()
    except SystemExit as exc:
        print("== configuracao ==")
        print(f"  FALTA  config\n          -> {exc}")
        return 1

    grupos = diagnosticar(cfg)
    marca = {"ok": "ok   ", "aviso": "aviso", "falta": "FALTA"}
    for i, grupo in enumerate(grupos):
        print(("\n" if i else "") + _terminal(f"== {grupo.nome} =="))
        for item in grupo.itens:
            detalhe = f"  ({item.detalhe})" if item.detalhe else ""
            print(_terminal(f"  {marca[item.status]}  {item.rotulo}{detalhe}"))
            if item.dica:
                print(_terminal(f"          -> {item.dica}"))

    print()
    faltas = problemas(grupos)
    if faltas:
        print(f"{len(faltas)} item(ns) precisam de atencao (veja as setas acima).")
        return 1
    print("Tudo pronto.")
    return 0


def cmd_bench(args) -> int:
    """Mede a taxa real de embedding em varios niveis de paralelismo.

    Existe porque o numero certo depende da maquina e das variaveis do
    Ollama, e chutar custa mais tempo do que medir.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor

    from .chunker import chunk_markdown
    from .embed import OllamaEmbedder
    from .indexer import iter_notes

    cfg = load_config({"model": args.model, "ollama_url": args.ollama})
    embedder = OllamaEmbedder(
        cfg.ollama_url, cfg.model, cfg.request_timeout, cfg.batch_size,
        num_thread=args.num_thread or cfg.num_thread,
    )
    embedder.check()

    textos: list[str] = []
    total_notas = 0
    for path, rel in iter_notes(cfg):
        total_notas += 1
        if len(textos) < args.samples:
            note = chunk_markdown(
                path.read_text(encoding="utf-8", errors="replace"),
                target_chars=cfg.target_chars,
                hard_max_chars=cfg.hard_max_chars,
                min_chars=cfg.min_chars,
            )
            textos += [c.text for c in note.chunks]
    textos = textos[: args.samples]
    if not textos:
        print("Nenhuma nota para medir.", file=sys.stderr)
        return 1

    media = sum(len(t) for t in textos) // len(textos)
    print(f"Modelo: {cfg.model} @ {cfg.ollama_url}")
    print(f"Amostra: {len(textos)} trechos reais do vault (media {media} chars)")
    if args.num_thread or cfg.num_thread:
        print(f"num_thread forcado: {args.num_thread or cfg.num_thread}")
    print("Aquecendo...", file=sys.stderr)
    embedder.embed(textos[:2])

    niveis = [int(x) for x in args.levels.split(",") if x.strip()]
    import math

    print(f"\n{'paralelo':>9s} {'chamadas':>9s} {'tempo':>8s} {'trechos/s':>11s} {'ganho':>7s}")
    print("-" * 50)
    base = None
    melhor = (0.0, 1)
    for nivel in niveis:
        inicio = time.time()
        if nivel <= 1:
            embedder.embed(textos)
        else:
            fatias = [textos[i::nivel] for i in range(nivel)]
            with ThreadPoolExecutor(max_workers=nivel) as pool:
                list(pool.map(embedder.embed, fatias))
        dt = time.time() - inicio
        taxa = len(textos) / dt
        if base is None:
            base = dt
        ganho = base / dt
        if taxa > melhor[0]:
            melhor = (taxa, nivel)
        if nivel <= 1:
            chamadas = math.ceil(len(textos) / cfg.batch_size)
        else:
            chamadas = sum(
                math.ceil(len(textos[i::nivel]) / cfg.batch_size) for i in range(nivel)
            )
        print(f"{nivel:>9d} {chamadas:>9d} {dt:>7.1f}s {taxa:>10.1f} {ganho:>6.1f}x")

    taxa, nivel = melhor
    print("-" * 50)
    print(f"\nMelhor: parallel = {nivel}  ({taxa:.1f} trechos/s)")
    chunks_estimados = total_notas * 11
    print(
        f"Nesse ritmo, as ~{total_notas} notas do vault (~{chunks_estimados} trechos) "
        f"levam ~{chunks_estimados / taxa / 60:.0f} min."
    )
    if nivel == 1 or (base and base / (len(textos) / taxa) < 1.3):
        print(
            "\nO paralelismo quase nao mudou nada. Duas causas possiveis:\n"
            "  1. OLLAMA_NUM_PARALLEL ainda esta em 1 (o default). Confira com:\n"
            "       [Environment]::GetEnvironmentVariable('OLLAMA_NUM_PARALLEL','User')\n"
            "     Se estiver certo, o Ollama precisa ser REINICIADO para ler a\n"
            "     variavel: sai pelo icone da bandeja e abre de novo.\n"
            "  2. Os nucleos fisicos ja estao saturados. A CPU 'sobrando' no\n"
            "     Gerenciador costuma ser hyperthread, que rende pouco em\n"
            "     multiplicacao de matriz. Nesse caso nao ha o que soltar:\n"
            "     o caminho e trocar por um modelo menor (embeddinggemma)."
        )
    else:
        print(f"\nPonha 'parallel = {nivel}' no config.toml e garanta que")
        print(f"OLLAMA_NUM_PARALLEL esteja em {nivel} ou mais.")
    return 0


def cmd_serve(args) -> int:
    from .server import main as serve_main
    from .server import serve_http, token_do_projeto

    if args.http:
        token = "" if args.sem_token else token_do_projeto(criar=True)
        serve_http(args.host, args.port, token)
    else:
        serve_main()
    return 0


def cmd_token(args) -> int:
    """Mostra (ou cria) o token do modo HTTP, e o bloco de config pronto."""
    from .server import token_do_projeto

    token = token_do_projeto(criar=True)
    if args.quiet:
        print(token)
        return 0
    # Tudo em stdout: o PowerShell trata escrita em stderr de comando nativo
    # como erro terminante quando ErrorActionPreference esta em Stop.
    print(
        f'  "vault-rag": {{\n'
        f'    "type": "http",\n'
        f'    "url": "http://127.0.0.1:{args.port}/mcp/",\n'
        f'    "headers": {{ "Authorization": "Bearer {token}" }}\n'
        f"  }}"
    )
    return 0


def cmd_calibrar(args) -> int:
    """Mede onde esta o piso que separa 'o vault responde' de 'nao responde'.

    O score do resultado e RRF: ele diz que os dois rankers concordaram, nao
    que o trecho responde a pergunta. Quando uma palavra da pergunta existe no
    vault com OUTRO sentido, os dois concordam com forca e o resultado errado
    sobe ao topo com score alto. A similaridade de cosseno crua e a unica
    medida de relevancia absoluta no pipeline, e este comando descobre onde
    ela separa as duas populacoes NESTE vault - em vez de herdar um numero
    chutado.
    """
    from .embed import EmbeddingError, OllamaEmbedder
    from .store import Store

    cfg = load_config({"model": args.model, "ollama_url": args.ollama})

    # Perguntas que o vault comprovadamente NAO responde. Escolhidas para nao
    # compartilhar vocabulario com o dominio dele - e duas de proposito que
    # compartilham ("receita", "rede"), porque sao esses os casos que enganam.
    fora = [
        "receita de pao de queijo mineiro",
        "route reflector do BGP",
        "como podar roseiras no inverno",
        "escalacao do Gremio na final de 1983",
        "dosagem de paracetamol para crianca",
        "conjugacao de verbo irregular em alemao",
        "preco do quilo do camarao rosa",
        "regra do roque no xadrez",
        "como trocar a correia dentada do carro",
        "rede de protecao para varanda de apartamento",
    ]

    store = Store(cfg.db_path, cfg.embed_dim)
    try:
        rows = store.conn.execute(
            "SELECT title FROM files WHERE n_chunks > 0 AND title != ''"
            " ORDER BY RANDOM() LIMIT ?",
            (args.amostra,),
        ).fetchall()
        dentro = [r["title"] for r in rows]
        if not dentro:
            print("Indice vazio. Rode 'vault-rag index' primeiro.", file=sys.stderr)
            return 1

        embedder = OllamaEmbedder(
            cfg.ollama_url, cfg.model, cfg.request_timeout, cfg.batch_size
        )

        def medir(perguntas, rotulo):
            valores = []
            for i, q in enumerate(perguntas, 1):
                try:
                    vec = embedder.embed_one(q)
                except EmbeddingError as exc:
                    print(f"  falhou em {q!r}: {exc}", file=sys.stderr)
                    continue
                s = store.similaridade_maxima(vec)
                valores.append((s, q))
                if not args.quiet:
                    print(f"  {rotulo} {i:>2}/{len(perguntas)}  {s:.4f}  {q[:58]}")
            return valores

        print(f"Indice: {cfg.db_path}\nModelo: {cfg.model}\n")
        print(f"A. {len(fora)} perguntas que o vault NAO responde")
        sem = medir(fora, "sem")
        print(f"\nB. {len(dentro)} titulos de notas reais (tem resposta por construcao)")
        com = medir(dentro, "com")

        if not sem or not com:
            print("\nAmostra insuficiente.", file=sys.stderr)
            return 1

        sem_v = sorted(s for s, _ in sem)
        com_v = sorted(s for s, _ in com)
        teto_sem = sem_v[-1]
        piso_com = com_v[0]
        p10_com = com_v[max(0, len(com_v) // 10)]

        print("\n" + "=" * 66)
        print(f"  sem resposta : min {sem_v[0]:.4f}  mediana {sem_v[len(sem_v)//2]:.4f}  MAX {teto_sem:.4f}")
        print(f"  com resposta : MIN {piso_com:.4f}  mediana {com_v[len(com_v)//2]:.4f}  max {com_v[-1]:.4f}")
        print("=" * 66)

        if teto_sem < piso_com:
            sugerido = (teto_sem + piso_com) / 2
            print(f"\n  As duas populacoes NAO se sobrepoem.")
            print(f"  Piso sugerido: min_score = {sugerido:.3f}")
            print(f"  (hoje esta em {cfg.min_score} - por isso nada e filtrado)")
        else:
            # Sobreposicao: escolher o piso e trocar falso positivo por falso
            # negativo. Prefiro o teto do ruido, que erra para o lado de nao
            # responder - resposta errada com confianca e o pior dos dois.
            print(f"\n  As populacoes se sobrepoem entre {piso_com:.4f} e {teto_sem:.4f}.")
            print(f"  Piso conservador (corta todo o ruido, perde algumas boas):")
            print(f"    min_score = {teto_sem + 0.005:.3f}")
            print(f"  Piso equilibrado (mantem 90% das boas):")
            print(f"    min_score = {p10_com:.3f}")
            n_perdidas = sum(1 for s in com_v if s < teto_sem + 0.005)
            print(f"\n  No conservador, {n_perdidas} de {len(com_v)} perguntas boas")
            print(f"  ficariam sem resposta. Vale se responder errado custa mais.")

        print(f"\n  Depois de escolher, edite min_score no config.toml.")
        piores = sorted(sem, reverse=True)[:3]
        print(f"\n  As 3 perguntas sem resposta que mais enganaram:")
        for s, q in piores:
            print(f"    {s:.4f}  {q}")
        print()
        return 0
    finally:
        store.close()


def _gerar_modelo_perguntas(cfg, quantas: int) -> str:
    """Monta um arquivo de perguntas para a pessoa parafrasear.

    As perguntas NAO podem vir embutidas no codigo: precisam falar de assuntos
    que existem NESTE vault, e so quem o escreveu sabe reescrever um titulo com
    outras palavras. Gerar a partir dos titulos reais e o mais longe que da
    para automatizar sem inventar.
    """
    from .store import Store

    store = Store(cfg.db_path, cfg.embed_dim)
    try:
        linhas = store.conn.execute(
            "SELECT path, title FROM files WHERE n_chunks > 2 AND title != ''"
            " ORDER BY RANDOM() LIMIT ?",
            (quantas,),
        ).fetchall()
    finally:
        store.close()

    out = [
        "# Perguntas para medir a confianca da busca neste vault.",
        "#",
        "# Formato:  pergunta | pedaco-do-caminho-da-nota-que-deveria-responder",
        "#",
        "# COMO USAR: abaixo estao titulos reais de notas suas. Reescreva cada um",
        "# como PERGUNTA, usando palavras que a nota NAO usa - e isso que testa se",
        "# a busca aguenta vocabulario diferente do seu. Titulo copiado igual nao",
        "# mede nada, porque casa por palavra.",
        "#",
        "# Exemplo: para uma nota intitulada 'Backup semanal do servidor de',",
        "# 'arquivos', uma boa pergunta parafraseada seria",
        "#   com que frequencia os documentos sao copiados | backup-semanal",
        "",
    ]
    for r in linhas:
        caminho = r["path"].rsplit("/", 1)[-1].replace(".md", "")
        out.append(f"# nota: {r['title']}")
        out.append(f"REESCREVA ESTA COMO PERGUNTA | {caminho}")
        out.append("")
    return "\n".join(out)


def cmd_testar_confianca(args) -> int:
    """Matriz de confusao das faixas: legitimas x ruido, em cada faixa.

    Substitui o antigo 'testar-piso', que media se um corte binario recusava
    pergunta boa. Nao ha mais corte: o resultado sai sempre e a saida gradua a
    confianca. O que importa medir mudou junto.

    Dois erros graves, e eles tem custos diferentes:
      - LEGITIMA em faixa baixa: o sistema desencoraja uma resposta correta.
      - RUIDO em faixa alta: o sistema entrega lixo sem ressalva. Pior.
    Legitima em faixa media nao e erro - e o sistema declarando que ali nao
    sabe distinguir, que e a verdade medida.
    """
    cfg = load_config({"model": args.model, "ollama_url": args.ollama})

    if args.gerar_modelo:
        destino = Path(args.gerar_modelo)
        destino.write_text(_gerar_modelo_perguntas(cfg, args.amostra), encoding="utf-8")
        print(f"Modelo escrito em {destino}")
        print("Reescreva cada titulo como pergunta, com palavras que a nota NAO usa.")
        print(f"Depois rode: vault-rag testar-confianca --perguntas {destino}")
        return 0

    if not args.perguntas:
        print("Este teste precisa de perguntas sobre o SEU vault - nao da para")
        print("embutir perguntas genericas, porque elas tem que falar de assuntos")
        print("que existem aqui dentro.\n")
        print("Gere um modelo com titulos reais das suas notas:")
        print("  vault-rag testar-confianca --gerar-modelo perguntas.txt")
        return 1

    caminho = Path(args.perguntas)
    if not caminho.is_file():
        print(f"arquivo nao encontrado: {caminho}", file=sys.stderr)
        return 1
    perguntas = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        pergunta, _, alvo = linha.partition("|")
        if pergunta.strip().startswith("REESCREVA"):
            continue
        perguntas.append((pergunta.strip(), alvo.strip()))
    if not perguntas:
        print("Nenhuma pergunta no arquivo - as linhas REESCREVA ainda nao foram",
              file=sys.stderr)
        print("preenchidas.", file=sys.stderr)
        return 1

    ruido = [
        "receita de pao de queijo mineiro",
        "route reflector do BGP",
        "como podar roseiras no inverno",
        "escalacao do Gremio na final de 1983",
        "dosagem de paracetamol para crianca",
        "preco do quilo do camarao rosa",
        "regra do roque no xadrez",
        "rede de protecao para varanda de apartamento",
    ]

    def avaliar(pergunta, alvo=None):
        hits = api.search(cfg, pergunta, top_k=args.top_k, expand=False)
        if not hits:
            return "vazio", None, None
        faixa = hits[0].confianca or "alta"
        # MAIOR similaridade entre os hits, nao a do primeiro: o reranker
        # reordena, e ler hits[0] faria a coluna mudar de valor entre rodadas
        # sem que nada tivesse mudado no indice.
        sim = max((h.vec_score for h in hits if h.vec_score is not None), default=None)
        if sim is None:
            sim = hits[0].top_sim_global
        pos = None
        if alvo:
            for i, h in enumerate(hits, 1):
                if alvo.lower() in h.path.lower():
                    pos = i
                    break
        return faixa, sim, pos

    juiz = (f"juiz {cfg.rerank_model} na faixa media, top {cfg.rerank_top}"
            if cfg.rerank_model else "sem juiz (so similaridade)")
    print(f"confiavel >= {cfg.sim_confiavel} · duvidoso < {cfg.sim_duvidoso}"
          f" · {juiz}\n")

    contagem = {"legitima": {}, "ruido": {}}
    graves = []

    print("A. Perguntas que o vault RESPONDE, com vocabulario diferente do das notas")
    for pergunta, alvo in perguntas:
        faixa, sim, pos = avaliar(pergunta, alvo)
        contagem["legitima"][faixa] = contagem["legitima"].get(faixa, 0) + 1
        sim_txt = f"{sim:.3f}" if sim is not None else "  -  "
        alvo_txt = f"alvo #{pos}" if pos else "alvo fora"
        marca = "  <-- GRAVE" if (faixa == "baixa" and pos) else ""
        print(f"  {faixa:<6} sim {sim_txt}  {alvo_txt:<10} {pergunta[:44]}{marca}")
        if faixa == "baixa" and pos:
            graves.append(("legitima em faixa baixa", pergunta))

    print("\nB. Perguntas que o vault NAO responde")
    for pergunta in ruido:
        faixa, sim, _ = avaliar(pergunta)
        contagem["ruido"][faixa] = contagem["ruido"].get(faixa, 0) + 1
        sim_txt = f"{sim:.3f}" if sim is not None else "  -  "
        marca = "  <-- GRAVE" if faixa == "alta" else ""
        print(f"  {faixa:<6} sim {sim_txt}  {' ' * 11}{pergunta[:44]}{marca}")
        if faixa == "alta":
            graves.append(("ruido em faixa alta", pergunta))

    print("\n" + "=" * 70)
    print(f"  {'':<12} {'alta':>6} {'media':>6} {'baixa':>6} {'vazio':>6}")
    for grupo in ("legitima", "ruido"):
        c = contagem[grupo]
        print(f"  {grupo:<12} {c.get('alta',0):>6} {c.get('media',0):>6}"
              f" {c.get('baixa',0):>6} {c.get('vazio',0):>6}")
    print("=" * 70)

    if graves:
        print(f"\n  {len(graves)} erro(s) grave(s):")
        for tipo, q in graves:
            print(f"    {tipo}: {q}")
        print("\n  Ruido em faixa alta e o pior: entrega sem ressalva o que nao")
        print("  responde. Se aparecer, suba sim_confiavel no config.toml.")
        print("  Legitima em faixa baixa desencoraja resposta correta: baixe")
        print("  sim_duvidoso. Se os dois aparecerem ao mesmo tempo, as faixas")
        print("  nao os separam e so o reranking resolve.")
    else:
        print("\n  Nenhum erro grave. Legitima em faixa media e esperado: ali as")
        print("  duas populacoes se sobrepoem e o sistema declara que nao sabe.")
    print()
    return 0 if not graves else 2


def _rotulo_notas(n: int) -> str:
    return f"{n} nota" if n == 1 else f"{n} notas"


def cmd_init(args) -> int:
    """Instala do zero, perguntando o minimo: vault, modelo, indice, clientes.

    Existe porque a alternativa e a pessoa editar um TOML antes de a ferramenta
    servir para alguma coisa, e ai a primeira impressao do projeto e trabalho
    de configuracao em vez de busca funcionando.
    """
    import shutil
    import urllib.error
    import urllib.request

    raiz = Path(__file__).resolve().parent.parent
    destino_cfg = raiz / "config.toml"

    def perguntar(texto, padrao=""):
        if args.sim:
            return padrao
        sufixo = f" [{padrao}]" if padrao else ""
        resposta = input(f"{texto}{sufixo}: ").strip()
        return resposta or padrao

    print("\n=== vault-vector: instalacao ===\n")

    # 1. o vault - ou um novo, para quem nao tem nada
    vault = args.vault or ""
    criar_do_zero = args.criar

    if not vault and not criar_do_zero:
        candidatos = []
        for base in (Path.home(), Path.home() / "Documents", Path.home() / "Documentos"):
            if not base.is_dir():
                continue
            try:
                for d in base.iterdir():
                    if d.is_dir() and (d / ".obsidian").is_dir():
                        candidatos.append(d)
            except OSError:
                continue

        if candidatos:
            print("Vaults do Obsidian encontrados:")
            for i, c in enumerate(candidatos, 1):
                print(f"  {i}. {c}")
            print(f"  {len(candidatos) + 1}. Comecar do zero, com um vault novo")
            escolha = perguntar("Numero, ou caminho de uma pasta", "1")
            if escolha.isdigit():
                n = int(escolha)
                if n == len(candidatos) + 1:
                    criar_do_zero = True
                elif 1 <= n <= len(candidatos):
                    vault = str(candidatos[n - 1])
                else:
                    print("Numero fora da lista.", file=sys.stderr)
                    return 1
            else:
                vault = escolha
        else:
            print("Nenhum vault do Obsidian encontrado por aqui.")
            print("  1. Comecar do zero (crio a pasta e a estrutura inicial)")
            print("  2. Apontar uma pasta de notas que ja existe")
            if perguntar("Numero", "1") == "2":
                vault = perguntar("Caminho da pasta")
            else:
                criar_do_zero = True

    if criar_do_zero:
        padrao = str(Path.home() / "Notas")
        if not vault:
            vault = perguntar("Onde criar o vault", padrao)
        alvo = Path(vault).expanduser()
        if alvo.exists() and any(alvo.iterdir()):
            print(f"  !   {alvo} ja existe e nao esta vazia.")
            if not args.sim and perguntar("Usar assim mesmo? (s/N)", "n").lower() != "s":
                return 1
        alvo.mkdir(parents=True, exist_ok=True)
        from .semente import criar_vault

        criados = criar_vault(alvo)
        vault = str(alvo)
        if criados:
            print(f"\n  ok  vault criado em {alvo}")
            for c in criados:
                print(f"      {c}")
            print("\n      A estrutura ja segue as convencoes que a busca usa:")
            print("      diario com data no nome, MOC por secao, titulos como")
            print("      fronteira de trecho. Abra a pasta no Obsidian se quiser")
            print("      editar com conforto - e uma pasta de markdown comum.")
        else:
            print(f"  ok  usando {alvo} (ja tinha as notas do esqueleto)")

    if not vault or not Path(vault).is_dir():
        print(f"Pasta nao encontrada: {vault!r}", file=sys.stderr)
        return 1
    n_md = sum(1 for _ in Path(vault).rglob("*.md"))
    print(f"\n  ok  {_rotulo_notas(n_md)} .md em {vault}\n")

    # 2. Ollama e o modelo
    url = args.ollama or "http://127.0.0.1:11434"
    modelo = args.model or "bge-m3"
    ollama_ok = False
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=5) as r:
            tags = json.loads(r.read())
        instalados = [m.get("name", "") for m in tags.get("models", [])]
        ollama_ok = True
        print(f"  ok  Ollama respondendo em {url}")
        if not any(m.split(":")[0] == modelo.split(":")[0] for m in instalados):
            ollama_ok = False
            print(f"  !   modelo '{modelo}' nao esta baixado")
            print(f"      rode: ollama pull {modelo}")
            if not args.sim and perguntar("Continuar assim mesmo? (s/N)", "n").lower() != "s":
                return 1
        else:
            print(f"  ok  modelo '{modelo}' disponivel")
    except (urllib.error.URLError, OSError, TimeoutError):
        print(f"  !   Ollama nao respondeu em {url}")
        print("      instale em https://ollama.com/download e rode 'ollama serve'")
        if not args.sim and perguntar("Continuar assim mesmo? (s/N)", "n").lower() != "s":
            return 1

    # 3. config
    if destino_cfg.exists() and not args.forcar:
        print(f"\n  !   {destino_cfg.name} ja existe - nao sobrescrevi.")
        print("      use --forcar para recriar.")
    else:
        exemplo = raiz / "config.exemplo.toml"
        if exemplo.is_file():
            conteudo = exemplo.read_text(encoding="utf-8")
        else:
            conteudo = 'vault = "CAMINHO"\nmodel = "bge-m3"\n'
        conteudo = conteudo.replace("CAMINHO_DO_SEU_VAULT", vault.replace("\\", "/"))
        conteudo = conteudo.replace('vault = "CAMINHO"', f'vault = "{vault}"')
        destino_cfg.write_text(conteudo, encoding="utf-8")
        print(f"\n  ok  {destino_cfg.name} escrito")

    # 4. indice
    if not ollama_ok:
        print("\n  -   indexacao pulada: sem Ollama nao ha como gerar embedding.")
        print(f"      Resolva o aviso acima e rode: vault-vector index")
    elif args.sim or perguntar("\nIndexar agora? (S/n)", "s").lower() != "n":
        cfg = load_config({"model": args.model, "ollama_url": args.ollama})
        quantas = _rotulo_notas(n_md)
        print(f"\nIndexando {quantas}. Em CPU isso leva minutos, nao segundos.\n")
        try:
            report = index_vault(cfg, verbose=True)
        except KeyboardInterrupt:
            print("\n\nInterrompido. O que ja entrou esta salvo - rode")
            print("'vault-vector index' para continuar de onde parou.")
            return 1
        except Exception as exc:
            # Traceback na primeira execucao e a pior primeira impressao
            # possivel, e quase sempre e Ollama fora do ar ou modelo ausente.
            print(f"\n  !   a indexacao falhou: {exc}")
            print("      O config ja foi escrito; corrija e rode 'vault-vector index'.")
            return 1
        print("\n" + report.as_text())
        if report.errors:
            print("\nAlgumas notas falharam. O que entrou esta salvo; rode")
            print("'vault-vector index' de novo para pegar o resto.")

    # 5. clientes
    print("\n=== Conectar ao Claude ===\n")
    exe = shutil.which("claude")
    if exe:
        print("Claude Code encontrado. Para registrar:")
    else:
        print("Para o Claude Code (se voce usa):")
    py = Path(sys.executable)
    print(f"  claude mcp add --scope user --transport stdio vault-vector -- "
          f"{py} -m vault_rag.server")
    print("\nPara o Claude Desktop, em claude_desktop_config.json:")
    print(json.dumps(
        {"mcpServers": {"vault-vector": {
            "command": str(py), "args": ["-m", "vault_rag.server"]}}},
        indent=2, ensure_ascii=False))
    print("\nPronto. Teste com:  vault-vector search \"algo que voce anotou\"\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vault-vector",
        description="Busca semantica hibrida local sobre um vault Obsidian.",
    )
    parser.add_argument("--model", help="modelo de embedding do Ollama")
    parser.add_argument("--ollama", help="URL do Ollama (ex.: http://127.0.0.1:11434)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="instala do zero: vault, modelo, indice, clientes")
    p.add_argument("--vault", help="caminho da pasta de notas (pula a pergunta)")
    p.add_argument("--criar", action="store_true",
                   help="cria um vault novo com a estrutura inicial")
    p.add_argument("--sim", action="store_true", help="aceita os padroes sem perguntar")
    p.add_argument("--forcar", action="store_true", help="recria o config.toml")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("index", help="indexa o vault (incremental por padrao)")
    p.add_argument("--force", action="store_true", help="reindexa tudo do zero")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("search", help="busca no indice")
    p.add_argument("query")
    p.add_argument("-k", "--top-k", type=int, default=6)
    p.add_argument("-s", "--section", help="limita a uma pasta raiz")
    p.add_argument("--lexical", action="store_true", help="so busca literal, sem embeddings")
    p.add_argument("--max-per-file", type=int, default=2, help="limite de trechos por nota (0 = sem limite)")
    p.add_argument("--no-expand", action="store_true", help="mostra so o chunk, sem a secao em volta")
    p.add_argument("--snippet", type=int, default=900)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("read", help="le uma nota do vault")
    p.add_argument("path")
    p.add_argument("--heading")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("stats", help="estado do indice")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("doctor", help="checa Ollama, indice, busca e escrita")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("bench", help="mede a taxa de embedding em varios paralelismos")
    p.add_argument("--samples", type=int, default=96, help="quantos trechos medir")
    p.add_argument("--levels", default="1,2,4,8", help="niveis a testar, separados por virgula")
    p.add_argument("--num-thread", type=int, default=0, help="forca num_thread do modelo")
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("serve", help="roda o MCP server (stdio por padrao)")
    p.add_argument("--http", action="store_true", help="modo HTTP: um processo serve todos os clientes")
    p.add_argument("--host", default="127.0.0.1", help="so mude se souber o que esta fazendo")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--sem-token", action="store_true", help="desliga a exigencia de token")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser(
        "servico",
        help="igual a 'serve --http', mas e o que a tarefa agendada chama: "
        "escreve tudo em servico.log em vez de exigir console",
    )
    p.set_defaults(func=lambda a: main_servico())

    p = sub.add_parser(
        "calibrar",
        help="mede o piso de similaridade que separa 'achei' de 'nao achei'",
    )
    p.add_argument("--amostra", type=int, default=30, help="quantos titulos reais usar")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_calibrar)

    p = sub.add_parser(
        "testar-confianca",
        help="matriz de confusao das faixas: pergunta legitima x ruido",
    )
    p.add_argument("--perguntas", help="arquivo com 'pergunta | trecho-do-caminho' por linha")
    p.add_argument("--gerar-modelo", metavar="ARQUIVO",
                   help="cria um modelo de perguntas a partir de notas suas")
    p.add_argument("--amostra", type=int, default=8, help="quantas notas no modelo")
    p.add_argument("--top-k", type=int, default=8)
    p.set_defaults(func=cmd_testar_confianca)

    p = sub.add_parser("token", help="mostra o token do modo HTTP e o bloco de config")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_token)

    return parser


def abrir_log_do_servico():
    """Troca stdout/stderr por um arquivo, e devolve o caminho.

    Um gui-script no Windows roda sob pythonw.exe, e la sys.stdout e
    sys.stderr sao None -- nao ha console para onde escrever. O uvicorn monta
    o logging com DefaultFormatter, que pergunta sys.stdout.isatty() para
    decidir se colore a saida, e isso estoura ValueError antes de a porta
    sequer abrir. O processo subia, morria em menos de um segundo e nao
    deixava rastro nenhum, justamente por nao ter para onde escrever o erro.
    Apontar os dois para um arquivo resolve as duas coisas de uma vez.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    log = raiz / "servico.log"
    try:
        # Um servico que roda meses nao pode virar um log de gigabytes.
        if log.is_file() and log.stat().st_size > 2_000_000:
            log.replace(raiz / "servico.log.anterior")
        fluxo = open(log, "a", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        # Sem lugar para escrever, o que importa e o servico subir mesmo assim.
        fluxo = open(os.devnull, "w", encoding="utf-8")
        log = None
    sys.stdout = fluxo
    sys.stderr = fluxo
    return log


def main_servico() -> int:
    """Entry point do servico HTTP, sem janela de console no Windows."""
    # O log precisa existir ANTES do import: server.py carrega o config e monta
    # o objeto MCP inteiro na hora do import, e um erro ali morreria sem deixar
    # rastro nenhum -- que foi exatamente o buraco que esta linha fecha.
    caminho = abrir_log_do_servico()
    print(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')}  subindo (pid {os.getpid()}) =====")
    print(f"executavel: {sys.executable}")
    print(f"pasta atual: {os.getcwd()}")
    sys.stdout.flush()
    try:
        from .server import serve_http, token_do_projeto

        porta = int(os.environ.get("VAULT_RAG_PORT", "8765"))
        serve_http("127.0.0.1", porta, token_do_projeto(criar=True))
    except BaseException:
        import traceback

        traceback.print_exc()
        sys.stdout.flush()
        return 1
    finally:
        if caminho:
            sys.stdout.flush()
    return 0


def main() -> int:
    args = build_parser().parse_args()
    for attr in ("model", "ollama"):
        if not hasattr(args, attr):
            setattr(args, attr, None)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
