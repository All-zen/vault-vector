import { FileCode, FileText, RefreshCw, RotateCcw, Save } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api/cliente";
import type { Config, ResultadoIndexacao, ValoresConfig } from "../api/tipos";
import { Badge, Button, Callout, Card, ProgressBar, Select, Slider, Switch, useToast } from "../componentes/ds";
import { ChunkPreview } from "../componentes/vault";
import { useApp } from "../lib/app";
import { useDados, useTarefa } from "../lib/dados";
import { numero, plural } from "../lib/formato";
import { hrefDe } from "../lib/rota";
import css from "./Ajustes.module.css";

type Grupo = "recorte" | "busca" | "juiz";

interface Campo {
  k: string;
  grupo: Grupo;
  rotulo: string;
  desc: ReactNode | ((v: number) => ReactNode);
  min: number;
  max: number;
  passo: number;
  casas?: number;
}

// Cada variavel do config.toml com o que ela muda na resposta. Os textos
// carregam o motivo medido de cada padrao, como os comentarios do config.
const CAMPOS: Campo[] = [
  { k: "target_chars", grupo: "recorte", rotulo: "Tamanho alvo do trecho", min: 600, max: 6000, passo: 100,
    desc: "Menor: busca mais precisa, mas cada trecho carrega menos contexto. Maior: mais contexto, embedding mais diluído." },
  { k: "hard_max_chars", grupo: "recorte", rotulo: "Teto duro", min: 2000, max: 12000, passo: 250,
    desc: "Só acima disso tabela e código são divididos — e tabela grande repete o cabeçalho em cada pedaço." },
  { k: "min_chars", grupo: "recorte", rotulo: "Mínimo", min: 0, max: 2000, passo: 50,
    desc: "Trecho menor que isso é fundido com o anterior. Evita trecho que é só um título." },
  { k: "candidates", grupo: "busca", rotulo: "Candidatos de cada lado", min: 10, max: 100, passo: 5,
    desc: "Quantos resultados cada ranker traz antes da fusão. Mais acha coisa escondida e custa um pouco mais." },
  { k: "rrf_k", grupo: "busca", rotulo: "Constante do RRF", min: 10, max: 120, passo: 5,
    desc: "Score = 1/(k + posição). k baixo: o topo de cada ranker domina. k alto: as posições se aproximam e a concordância entre os dois pesa mais." },
  { k: "max_per_file", grupo: "busca", rotulo: "Máximo por nota", min: 1, max: 6, passo: 1,
    desc: "Impede que uma nota longa ocupe todos os resultados." },
  { k: "expand_chars", grupo: "busca", rotulo: "Expansão small-to-big", min: 1000, max: 8000, passo: 250,
    desc: "Busca pelo trecho pequeno e devolve a seção inteira até este teto. Mais = o Claude lê mais contexto." },
  { k: "min_score", grupo: "busca", rotulo: "Piso de recall", min: 0, max: 0.6, passo: 0.01, casas: 2,
    desc: "Corta só o que nem candidato é. Não é filtro de qualidade — para isso existem as faixas de confiança." },
  { k: "rerank_top", grupo: "juiz", rotulo: "Trechos julgados", min: 1, max: 10, passo: 1,
    desc: (v) => `Em CPU, cada um custa 0,3–1,7 s. Agora: até ~${(v * 1.7).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} s a mais na faixa média.` },
  { k: "rerank_chars", grupo: "juiz", rotulo: "Corte enviado ao juiz", min: 200, max: 1200, passo: 50,
    desc: "Medido: 350 rebaixou uma resposta certa de 6 para 3; 600 manteve a nota sem custo perceptível." },
  { k: "rerank_promove", grupo: "juiz", rotulo: "Média que promove para alta", min: 0, max: 10, passo: 0.1, casas: 1,
    desc: "Decide pela média das notas, não pelo máximo: com cinco tentativas, até ruído acha um trecho que tira 6." },
  { k: "rerank_rebaixa", grupo: "juiz", rotulo: "Média que rebaixa para baixa", min: 0, max: 10, passo: 0.1, casas: 1,
    desc: "Entre as duas, a faixa continua média: nem a similaridade nem o juiz decidiram." },
];

const RECORTE = ["target_chars", "hard_max_chars", "min_chars"];

const formatar = (c: Campo) => (v: number) =>
  c.casas ? v.toLocaleString("pt-BR", { minimumFractionDigits: c.casas, maximumFractionDigits: c.casas }) : numero(v);

function Linha({ campo, valor, padrao, onChange }: { campo: Campo; valor: number; padrao: number; onChange: (v: number) => void }) {
  return (
    <div className={css.linha}>
      <div className={css.textos}>
        <div className={css.nome}>
          <span className={css.rotulo}>{campo.rotulo}</span>
          <code className={css.chave}>{campo.k}</code>
          {RECORTE.includes(campo.k) && <Badge tone="media">refaz os trechos</Badge>}
          {valor !== padrao && (
            <button type="button" className={css.padrao} onClick={() => onChange(padrao)} title="Voltar ao padrão">
              padrão {formatar(campo)(padrao)}
            </button>
          )}
        </div>
        <div className={css.desc}>{typeof campo.desc === "function" ? campo.desc(valor) : campo.desc}</div>
      </div>
      <div className={css.controle}>
        <Slider aria-label={campo.rotulo} value={valor} min={campo.min} max={campo.max} step={campo.passo} onChange={onChange} format={formatar(campo)} />
      </div>
    </div>
  );
}

/**
 * Peso de cada posicao no RRF, relativo ao primeiro lugar. Normalizar pelo
 * primeiro mostra a forma da curva: com k alto ela quase nao cai (posicoes
 * pesam parecido), com k baixo o topo de cada ranker domina.
 */
function BarrasRrf({ k }: { k: number }) {
  const primeiro = 1 / (k + 1);
  return (
    <div className={css.rrf} aria-hidden>
      {Array.from({ length: 20 }, (_, i) => {
        const v = 1 / (k + i + 1);
        return (
          <span
            key={i}
            title={`posição ${i + 1}: ${v.toFixed(4)} (${Math.round((v / primeiro) * 100)}% do primeiro)`}
            style={{ height: `${(v / primeiro) * 100}%` }}
            className={i < 3 ? css.topo : ""}
          />
        );
      })}
    </div>
  );
}

function PreviaRecorte({ valores }: { valores: ValoresConfig }) {
  const { dados: notas } = useDados(() => api.notas(undefined, 200), []);
  const [caminho, setCaminho] = useState("");
  const parametros = { target_chars: valores.target_chars, hard_max_chars: valores.hard_max_chars, min_chars: valores.min_chars };
  const [pedido, setPedido] = useState(parametros);

  // Espera o slider parar antes de pedir de novo: arrastar dispararia uma
  // requisicao por pixel.
  const chave = JSON.stringify(parametros);
  useEffect(() => {
    const id = window.setTimeout(() => setPedido(JSON.parse(chave)), 250);
    return () => window.clearTimeout(id);
  }, [chave]);

  const { dados: recorte } = useDados(() => api.recorte({ ...pedido, caminho }), [JSON.stringify(pedido), caminho]);
  if (!recorte) return null;

  return (
    <div className={css.previa}>
      <div className={css.previaTopo}>
        <FileText size={14} />
        <Select
          size="sm"
          aria-label="Nota da prévia"
          value={recorte.caminho}
          onChange={setCaminho}
          options={(notas ?? []).map((n) => n.path).concat(notas?.some((n) => n.path === recorte.caminho) ? [] : [recorte.caminho])}
          className={css.notaPrevia}
        />
        <span className={css.previaInfo}>
          {numero(recorte.chars)} chars · {plural(recorte.trechos.length, "trecho", "trechos")} · prévia ao vivo
        </span>
      </div>
      <ChunkPreview trechos={recorte.trechos} target={Number(valores.target_chars)} />
    </div>
  );
}

function ArquivoConfig({ config, valores }: { config: Config; valores: ValoresConfig }) {
  const chaves = CAMPOS.map((c) => c.k).concat("rerank_model");
  const mudadas = chaves.filter((k) => valores[k] !== config.valores[k]);
  return (
    <Card padding={0} className={css.arquivo}>
      <div className={css.arquivoTopo}>
        <FileCode size={14} />
        <span className={css.arquivoNome} title={config.arquivo}>
          config.toml
        </span>
        <span className={css.arquivoInfo}>{plural(mudadas.length, "alteração", "alterações")}</span>
      </div>
      <pre className={css.toml}>
        {chaves.map((k) => {
          const v = valores[k];
          const mudou = mudadas.includes(k);
          const texto = typeof v === "string" ? `"${v}"` : String(v);
          return (
            <div key={k} className={mudou ? css.mudou : ""}>
              <span className={css.marca}>{mudou ? "~ " : "  "}</span>
              {k} = {texto}
            </div>
          );
        })}
      </pre>
    </Card>
  );
}

/** O que so existe no app de desktop: abrir com o Windows. */
function CartaoApp() {
  const toast = useToast();
  const { dados: sistema, recarregar } = useDados(() => api.sistema(), []);
  if (!sistema?.desktop) return null;
  return (
    <Card>
      <section className={css.secao}>
        <h2>App</h2>
        <p>
          Fechar a janela só esconde o vault-vector: ele continua na bandeja, perto do relógio, servindo o Claude. Sair é pelo
          menu do ícone.
          {sistema.atalho && (
            <>
              {" "}
              De qualquer programa, <kbd>{sistema.atalho}</kbd> traz a janela com o foco na busca.
            </>
          )}
        </p>
        {sistema.autostart.suportado ? (
          <Switch
            checked={sistema.autostart.ligado}
            onChange={async (ligado) => {
              try {
                await api.autostart(ligado);
                toast(ligado ? "Abre com o Windows, escondido na bandeja." : "Não abre mais com o Windows.");
              } catch (e) {
                toast(e instanceof Error ? e.message : String(e), "erro");
              }
              recarregar();
            }}
            label="Abrir com o Windows"
            description="Sobe escondido no logon, só com o ícone da bandeja. Fica em Gerenciador de Tarefas › Inicializar."
          />
        ) : (
          <p>Abrir com o sistema só existe no Windows, por enquanto.</p>
        )}
      </section>
    </Card>
  );
}

export function Ajustes() {
  const { recarregarEstado, setOcupado } = useApp();
  const toast = useToast();
  const { dados: config, recarregar } = useDados(() => api.config(), []);
  const [valores, setValores] = useState<ValoresConfig | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [refazer, setRefazer] = useState(false);
  const juizSugerido = useMemo(() => String(config?.valores.rerank_model || "qwen2.5:3b-instruct"), [config]);
  const [ultimoJuiz, setUltimoJuiz] = useState(juizSugerido);

  useEffect(() => {
    if (config) setValores(config.valores);
  }, [config]);
  useEffect(() => setUltimoJuiz(juizSugerido), [juizSugerido]);

  const reindex = useTarefa<ResultadoIndexacao>((t) => {
    setOcupado(false);
    setRefazer(false);
    toast(
      t.estado === "ok" ? `Trechos refeitos. ${plural(t.resultado?.trechos ?? 0, "trecho gravado", "trechos gravados")}.` : `Falhou: ${t.erro}`,
      t.estado === "ok" ? "ok" : "erro",
    );
    recarregarEstado();
  });

  if (!config || !valores) return null;

  const mudadas = Object.keys(valores).filter((k) => valores[k] !== config.valores[k]);
  const recorteMudou = mudadas.some((k) => RECORTE.includes(k));
  const juizLigado = Boolean(valores.rerank_model);
  const set = (k: string) => (v: number | string) => setValores({ ...valores, [k]: v });

  const salvar = async () => {
    setSalvando(true);
    try {
      const r = await api.gravarConfig(Object.fromEntries(mudadas.map((k) => [k, valores[k]!])));
      toast(r.reindexar ? "config.toml salvo. Falta refazer os trechos." : "config.toml salvo. Vale na próxima busca.");
      if (r.reindexar) setRefazer(true);
      recarregar();
      recarregarEstado();
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "erro");
    } finally {
      setSalvando(false);
    }
  };

  const grupo = (g: Grupo) =>
    CAMPOS.filter((c) => c.grupo === g).map((c) => (
      <div key={c.k}>
        <Linha campo={c} valor={Number(valores[c.k])} padrao={Number(config.padroes[c.k])} onChange={set(c.k)} />
        {c.k === "rrf_k" && <BarrasRrf k={Number(valores.rrf_k)} />}
      </div>
    ));

  return (
    <div className={css.tela}>
      <div className={css.principal}>
        <div className="tela-titulo">
          <h1>Ajustes</h1>
          <p>
            Cada variável do <code>config.toml</code>, com o que ela muda na resposta. Os padrões foram medidos num vault real de
            ~500 notas; os limiares de confiança ficam na tela <a href={hrefDe("calibrar")}>Calibrar</a>.
          </p>
        </div>

        <CartaoApp />

        <Card>
          <section className={css.secao}>
            <h2>Recorte em trechos</h2>
            <p>Como cada nota vira pedaços indexados. Títulos são fronteira; tabela e bloco de código nunca são partidos no meio.</p>
            {grupo("recorte")}
            <PreviaRecorte valores={valores} />
          </section>
        </Card>

        <Card>
          <section className={css.secao}>
            <h2>Busca</h2>
            <p>O lado semântico e o literal são ranqueados separados e fundidos por Reciprocal Rank Fusion.</p>
            {grupo("busca")}
          </section>
        </Card>

        <Card>
          <section className={css.secao}>
            <h2>Juiz local</h2>
            <p>Modelo de instrução que lê pergunta e trecho juntos. Só roda na faixa média, onde a similaridade não decide.</p>
            <div className={css.interruptor}>
              <Switch
                checked={juizLigado}
                onChange={(on) => {
                  if (!on) setUltimoJuiz(String(valores.rerank_model || ultimoJuiz));
                  set("rerank_model")(on ? ultimoJuiz : "");
                }}
                label={juizLigado ? `Juiz ligado · ${valores.rerank_model}` : "Juiz desligado"}
                description="Desligado, a busca decide só pela similaridade, como antes do reranker."
              />
            </div>
            <div className={juizLigado ? "" : css.apagado}>{grupo("juiz")}</div>
          </section>
        </Card>
      </div>

      <aside className={css.lateral}>
        <ArquivoConfig config={config} valores={valores} />
        {recorteMudou && (
          <Callout tone="media" title="O recorte mudou">
            Ao salvar, os trechos precisam ser refeitos. Trecho com o mesmo texto reaproveita o vetor.
          </Callout>
        )}
        {refazer && !reindex.rodando && (
          <Callout
            tone="media"
            title="Falta refazer os trechos"
            action={
              <Button
                size="sm"
                variant="primary"
                icon={RefreshCw}
                onClick={() => {
                  setOcupado(true);
                  void reindex.iniciar(() => api.indexar({ refazer_trechos: true }));
                }}
              >
                Refazer
              </Button>
            }
          >
            Até lá, a busca usa os trechos cortados do jeito antigo.
          </Callout>
        )}
        {reindex.tarefa?.estado === "rodando" && (
          <ProgressBar
            value={reindex.tarefa.total ? reindex.tarefa.feito / reindex.tarefa.total : null}
            label="Refazendo os trechos"
            detail={reindex.tarefa.total ? `${reindex.tarefa.feito} / ${reindex.tarefa.total}` : ""}
          />
        )}
        <div className={css.botoes}>
          <Button variant="primary" icon={Save} disabled={!mudadas.length} loading={salvando} onClick={salvar} full>
            Salvar
          </Button>
          <Button variant="ghost" icon={RotateCcw} disabled={!mudadas.length} onClick={() => setValores(config.valores)}>
            Desfazer
          </Button>
        </div>
      </aside>
    </div>
  );
}
