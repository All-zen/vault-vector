import { Cpu, Download, Gauge, PlugZap } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ErroApi } from "../api/cliente";
import type { Embedding, EstadoOllama, ModeloOllama, NivelParalelo, ResultadoIndexacao, ResultadoParalelismo } from "../api/tipos";
import { Badge, Button, Callout, Card, CardHeader, Input, ProgressBar, useToast } from "../componentes/ds";
import { CommandBlock, ConfidenceBadge, StatusRow, VectorStrip } from "../componentes/vault";
import { useApp } from "../lib/app";
import { useDados, useTarefa } from "../lib/dados";
import { bytes, numero, plural } from "../lib/formato";
import css from "./Modelos.module.css";

const SUGESTOES = ["bge-m3", "embeddinggemma", "nomic-embed-text", "qwen2.5:3b-instruct"];

/**
 * A mesma regra do ollama.mesmo_modelo: o config diz "bge-m3" e o Ollama
 * lista "bge-m3:latest". Comparar o texto cru marcaria o modelo em uso como
 * outro, e oferecer "trocar e reindexar tudo" para o mesmo modelo.
 */
export function mesmoModelo(pedido: string, instalado: string): boolean {
  if (!pedido) return false;
  if (pedido === instalado) return true;
  if (pedido.includes(":")) return instalado === `${pedido}:latest`;
  return instalado.split(":")[0] === pedido;
}

function cosseno(a: number[], b: number[]): number {
  // Os vetores chegam normalizados: o cosseno e o produto escalar.
  return a.reduce((s, x, i) => s + x * (b[i] ?? 0), 0);
}

function Conexao({ estado, aoTestar }: { estado: EstadoOllama; aoTestar: (url: string) => void }) {
  const { recarregarEstado } = useApp();
  const toast = useToast();
  const [url, setUrl] = useState(estado.config_url);
  const [testando, setTestando] = useState(false);
  useEffect(() => setUrl(estado.config_url), [estado.config_url]);

  return (
    <Card className={css.card}>
      <CardHeader title="Conexão" subtitle="Os embeddings saem do Ollama na sua máquina. Nada vai para a internet." />
      <div className={css.linha}>
        <Input label="ollama_url" mono value={url} onChange={(e) => setUrl(e.target.value)} className={css.flex} />
        <Button
          icon={PlugZap}
          loading={testando}
          onClick={async () => {
            setTestando(true);
            await aoTestar(url);
            setTestando(false);
          }}
        >
          Testar
        </Button>
        {url !== estado.config_url && estado.url === url && estado.ok && (
          <Button
            variant="primary"
            onClick={async () => {
              await api.gravarConfig({ ollama_url: url });
              toast("Endereço do Ollama salvo.");
              recarregarEstado();
            }}
          >
            Usar este endereço
          </Button>
        )}
      </div>
      <div>
        <StatusRow
          status={estado.ok ? "ok" : "falta"}
          label={estado.ok ? `Serviço respondendo · ${estado.ms} ms` : "O Ollama não respondeu"}
          detail={estado.ok ? `${estado.url}${estado.versao ? ` · versão ${estado.versao}` : ""}` : estado.erro}
          hint="abra o app do Ollama, ou rode 'ollama serve' num terminal"
        />
      </div>
    </Card>
  );
}

function Instalados({ estado, aoMudar }: { estado: EstadoOllama; aoMudar: () => void }) {
  const { recarregarEstado, setOcupado } = useApp();
  const toast = useToast();
  const emUso = estado.modelos.find((m) => m.tipo === "embedding" && mesmoModelo(estado.modelo, m.nome))?.nome ?? estado.modelo;
  const [escolhido, setEscolhido] = useState(emUso);
  useEffect(() => setEscolhido(emUso), [emUso]);

  const reindex = useTarefa<ResultadoIndexacao>((t) => {
    setOcupado(false);
    toast(t.estado === "ok" ? "Vault reindexado com o modelo novo." : `A reindexação falhou: ${t.erro}`, t.estado === "ok" ? "ok" : "erro");
    recarregarEstado();
    aoMudar();
  });

  const embeddings = estado.modelos.filter((m) => m.tipo === "embedding");
  const instrucao = estado.modelos.filter((m) => m.tipo === "instrucao");
  const alvo = embeddings.find((m) => m.nome === escolhido);
  const indiceDe = estado.indice_modelo;
  const trocando = !mesmoModelo(estado.modelo, escolhido);

  const usarModelo = async (m: ModeloOllama) => {
    await api.gravarConfig({ model: m.nome, ...(m.dims ? { embed_dim: m.dims } : {}) });
    setOcupado(true);
    // O index_vault ve que o modelo mudou e refaz tudo sozinho.
    await reindex.iniciar(() => api.indexar({ forcar: true }));
  };

  const juiz = async (nome: string) => {
    await api.gravarConfig({ rerank_model: nome });
    toast(nome ? `Juiz da faixa média: ${nome}` : "Juiz desligado. A busca volta a decidir só pela similaridade.");
    recarregarEstado();
    aoMudar();
  };

  const linha = (m: ModeloOllama, i: number) => {
    const ehEmbedding = m.tipo === "embedding";
    const marcado = ehEmbedding ? escolhido === m.nome : mesmoModelo(estado.juiz, m.nome);
    return (
      <label key={m.nome} className={`${css.modelo} ${marcado ? css.marcado : ""}`} style={{ animationDelay: `${i * 50}ms` }}>
        <input
          type={ehEmbedding ? "radio" : "checkbox"}
          name={ehEmbedding ? "embedding" : undefined}
          checked={marcado}
          onChange={() => (ehEmbedding ? setEscolhido(m.nome) : void juiz(marcado ? "" : m.nome))}
          className={css.marcador}
        />
        <span className={css.modeloNome}>
          <span>{m.nome}</span>
          <span className={css.modeloNota}>
            {ehEmbedding
              ? indiceDe && mesmoModelo(indiceDe, m.nome)
                ? "o índice atual foi feito com ele"
                : "embedding"
              : marcado
                ? "juiz da faixa média"
                : "modelo de instrução"}
            {m.parametros ? ` · ${m.parametros}` : ""}
            {m.quantizacao ? ` · ${m.quantizacao}` : ""}
          </span>
        </span>
        <Badge tone={ehEmbedding ? "accent" : "neutral"}>{ehEmbedding ? "embedding" : "instrução"}</Badge>
        <span className={css.mono}>{m.dims ? `${m.dims}d` : "—"}</span>
        <span className={css.mono}>
          {m.carregado && <i className={css.quente} title="carregado na memória" />}
          {bytes(m.bytes)}
        </span>
      </label>
    );
  };

  return (
    <Card className={css.card}>
      <CardHeader title="Modelos instalados" subtitle="O de embedding gera os vetores do índice. O de instrução, se marcado, julga a faixa média." />
      <div className={css.lista}>{[...embeddings, ...instrucao].map(linha)}</div>
      {!estado.modelos.length && <p className={css.vazio}>Nenhum modelo baixado ainda.</p>}

      {trocando && alvo && !reindex.rodando && (
        <Callout
          tone="media"
          title={`O índice foi feito com ${indiceDe ?? estado.modelo}; trocar para ${alvo.nome} exige reindexar tudo`}
          action={
            <div className={css.acoesAviso}>
              <Button size="sm" variant="primary" onClick={() => void usarModelo(alvo)}>
                Trocar e reindexar
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEscolhido(estado.modelo)}>
                Manter
              </Button>
            </div>
          }
        >
          Vetores de modelos diferentes não se comparam: a busca só volta a funcionar depois de refazer cada trecho.
        </Callout>
      )}
      {reindex.tarefa?.estado === "rodando" && (
        <ProgressBar
          value={reindex.tarefa.total ? reindex.tarefa.feito / reindex.tarefa.total : null}
          label={reindex.tarefa.mensagem || "Reindexando com o modelo novo"}
          detail={reindex.tarefa.total ? `${numero(reindex.tarefa.feito)} / ${plural(reindex.tarefa.total, "nota", "notas")}` : ""}
        />
      )}
      <Baixar aoBaixar={aoMudar} />
    </Card>
  );
}

function Baixar({ aoBaixar }: { aoBaixar: () => void }) {
  const toast = useToast();
  const [nome, setNome] = useState("");
  const pull = useTarefa<{ modelo: string }>((t) => {
    toast(t.estado === "ok" ? `${t.resultado?.modelo} baixado.` : `O download falhou: ${t.erro}`, t.estado === "ok" ? "ok" : "erro");
    aoBaixar();
  });
  const t = pull.tarefa;

  return (
    <div className={css.baixar}>
      <form
        className={css.linha}
        onSubmit={(e) => {
          e.preventDefault();
          if (nome.trim()) void pull.iniciar(() => api.baixarModelo(nome.trim()));
        }}
      >
        <Input
          label="Baixar modelo"
          mono
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          placeholder="nome no ollama.com/library"
          className={css.flex}
        />
        <Button type="submit" icon={Download} loading={pull.rodando} disabled={!nome.trim()}>
          Baixar
        </Button>
      </form>
      <div className={css.sugestoes}>
        {SUGESTOES.map((s) => (
          <button key={s} type="button" className={css.sugestao} onClick={() => setNome(s)}>
            {s}
          </button>
        ))}
      </div>
      {t?.estado === "rodando" && (
        <ProgressBar
          value={t.total ? t.feito / t.total : null}
          label={`ollama pull ${nome} · ${t.mensagem}`}
          detail={t.total ? `${bytes(t.feito)} / ${bytes(t.total)}` : ""}
        />
      )}
      {pull.erro && <Callout tone="baixa">{pull.erro.message}</Callout>}
    </div>
  );
}

function VerEmbedding({ modelo, limiares }: { modelo: string; limiares: { duvidoso: number; confiavel: number } }) {
  const [a, setA] = useState("quando o backup parou de rodar");
  const [b, setB] = useState("o job de cópia noturna falhou sem avisar");
  const [vetores, setVetores] = useState<[Embedding, Embedding | null] | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState("");

  const embeddar = async () => {
    setCarregando(true);
    setErro("");
    try {
      const va = await api.embeddar(a);
      const vb = b.trim() ? await api.embeddar(b) : null;
      setVetores([va, vb]);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : String(e));
    } finally {
      setCarregando(false);
    }
  };

  const sim = vetores?.[1] ? cosseno(vetores[0].valores, vetores[1].valores) : null;
  const faixa = sim == null ? null : sim >= limiares.confiavel ? "alta" : sim >= limiares.duvidoso ? "media" : "baixa";

  return (
    <Card className={css.card}>
      <CardHeader
        title="Ver um embedding"
        subtitle={`O que o ${modelo} faz com um texto: uma lista de números. Textos de sentido parecido viram listas parecidas.`}
      />
      <form
        className={css.pares}
        onSubmit={(e) => {
          e.preventDefault();
          void embeddar();
        }}
      >
        <Input label="Texto" value={a} onChange={(e) => setA(e.target.value)} />
        <Input label="Comparar com (opcional)" value={b} onChange={(e) => setB(e.target.value)} />
        <Button type="submit" variant="primary" icon={Cpu} loading={carregando} disabled={!a.trim()}>
          Embeddar
        </Button>
      </form>
      {erro && <Callout tone="baixa">{erro}</Callout>}
      {vetores && (
        <div className={css.vetores}>
          {vetores.map(
            (v, i) =>
              v && (
                <div key={i} className={css.vetor}>
                  <VectorStrip key={v.valores.slice(0, 4).join()} values={v.valores} columns={64} cell={7} />
                  <div className={css.legendaVetor}>
                    <span>{numero(v.dims)} dimensões</span>
                    <span>{v.ms} ms</span>
                    <span>norma original {v.norma.toLocaleString("pt-BR")}</span>
                    <span style={{ color: "var(--vv-400)" }}>■ positivo</span>
                    <span style={{ color: "var(--baixa-fg)" }}>■ negativo</span>
                  </div>
                </div>
              ),
          )}
          {sim != null && faixa && (
            <div className={css.comparacao}>
              <ConfidenceBadge faixa={faixa} sim={sim} animate />
              <span>
                cosseno entre os dois, contra os limiares do vault ({limiares.duvidoso.toFixed(2)} e {limiares.confiavel.toFixed(2)}).
                É esse número que decide a faixa de uma busca.
              </span>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function Desempenho() {
  const { recarregarEstado } = useApp();
  const toast = useToast();
  const medicao = useTarefa<ResultadoParalelismo, NivelParalelo>();
  const t = medicao.tarefa;
  const niveis = t?.resultado?.resultados ?? t?.parciais ?? [];
  const maior = Math.max(1, ...niveis.map((n) => n.taxa));
  const r = t?.resultado;

  return (
    <Card className={css.card}>
      <CardHeader
        title="Desempenho"
        subtitle="Trechos por segundo em cada nível de paralelismo, com trechos reais do vault. O número certo depende da máquina."
        action={
          <Button icon={Gauge} loading={medicao.rodando} onClick={() => void medicao.iniciar(() => api.medirParalelismo())}>
            Medir
          </Button>
        }
      />
      {t?.estado === "rodando" && !niveis.length && <ProgressBar value={null} label={t.mensagem || "Aquecendo o modelo"} />}
      {niveis.length > 0 && (
        <div className={css.barras}>
          {[1, 2, 3, 4].map((p) => {
            const n = niveis.find((x) => x.paralelo === p);
            const melhor = r?.melhor.paralelo === p;
            return (
              <div key={p} className={css.barra}>
                <span className={melhor ? css.melhor : ""}>parallel = {p}</span>
                <span className={css.trilho}>
                  <i className={melhor ? css.iMelhor : ""} style={{ width: n ? `${(n.taxa / maior) * 100}%` : "0%" }} />
                </span>
                <span className={css.taxa}>{n ? `${n.taxa.toLocaleString("pt-BR")} /s` : "…"}</span>
              </div>
            );
          })}
        </div>
      )}
      {r && (
        <div className={css.conclusao}>
          {r.inutil ? (
            <p>
              O paralelismo quase não mudou nada (ganho de {r.melhor.ganho.toLocaleString("pt-BR")}×). Ou o{" "}
              <code>OLLAMA_NUM_PARALLEL</code> ainda está em 1, ou os núcleos físicos já saturaram — aí o caminho é um modelo
              menor.
            </p>
          ) : (
            <p>
              Melhor: <code>parallel = {r.melhor.paralelo}</code>, {r.melhor.taxa.toLocaleString("pt-BR")} trechos/s. As{" "}
              {numero(r.total_notas)} notas levariam uns {Math.max(1, Math.round((r.total_notas * 11) / r.melhor.taxa / 60))} min
              para indexar do zero.
            </p>
          )}
          {!r.inutil && r.melhor.paralelo !== r.parallel_atual && (
            <Button
              size="sm"
              onClick={async () => {
                await api.gravarConfig({ parallel: r.melhor.paralelo });
                toast(`parallel = ${r.melhor.paralelo} salvo no config.toml.`);
                recarregarEstado();
              }}
            >
              Usar parallel = {r.melhor.paralelo}
            </Button>
          )}
        </div>
      )}
      {medicao.erro && <Callout tone="baixa">{medicao.erro.message}</Callout>}
      {t?.estado === "erro" && <Callout tone="baixa" title="A medição falhou">{t.erro}</Callout>}
    </Card>
  );
}

export function Modelos() {
  const [url, setUrl] = useState<string | undefined>(undefined);
  const { dados: estado, erro, recarregar } = useDados(() => api.ollama(url), [url]);
  const { dados: busca } = useDados(() => api.config(), []);
  const limiares = {
    duvidoso: Number(busca?.valores.sim_duvidoso ?? 0.43),
    confiavel: Number(busca?.valores.sim_confiavel ?? 0.6),
  };

  return (
    <div className="tela-conteudo" style={{ maxWidth: 960 }}>
      <div className="tela-titulo">
        <h1>Modelos · Ollama</h1>
        <p>Qual modelo gera os vetores, qual julga a faixa média, e quanto a sua máquina aguenta.</p>
      </div>
      {erro && (
        <Callout tone="baixa" title="Não consegui consultar o Ollama">
          {erro.message}
        </Callout>
      )}
      {estado && (
        <>
          <Conexao
            estado={estado}
            aoTestar={(u) => {
              setUrl(u);
              recarregar();
            }}
          />
          {estado.ok && (
            <>
              <Instalados estado={estado} aoMudar={recarregar} />
              <VerEmbedding modelo={estado.modelo} limiares={limiares} />
              <Desempenho />
            </>
          )}
        </>
      )}
      <CommandBlock command="vault-vector bench" comment="a mesma medição no terminal" />
    </div>
  );
}
