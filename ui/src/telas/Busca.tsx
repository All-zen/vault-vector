import { Clock, CornerDownLeft, FileText, Search } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { api, ErroApi } from "../api/cliente";
import type { Busca as Resultado, Hit } from "../api/tipos";
import { Badge, Button, Callout, Input, Select } from "../componentes/ds";
import {
  CommandBlock,
  ConfidenceBadge,
  MetaList,
  ResultCard,
  ScoreBreakdown,
  ScoreMeter,
  SearchPipeline,
  type Sinal,
} from "../componentes/vault";
import { useApp } from "../lib/app";
import { useDados } from "../lib/dados";
import { data, dataDoNome, dataHora, decimal, idade, numero, tipoNota } from "../lib/formato";
import { previa } from "../lib/markdown";
import { hrefNota, navegar } from "../lib/rota";
import css from "./Busca.module.css";

const trilha = (h: string) => h.split(" > ").join(" › ");

function sinais(h: Hit): Sinal[] {
  const s: Sinal[] = [];
  if (h.vec_rank != null) {
    // A similaridade crua vai junto: o score do RRF diz so que os rankers
    // concordaram; este numero e o que diz se tem a ver com a pergunta.
    s.push({ label: `semântico #${h.vec_rank + 1}${h.vec_score != null ? ` · sim ${h.vec_score.toFixed(3)}` : ""}`, tone: "accent" });
  }
  if (h.fts_rank != null) s.push({ label: `literal #${h.fts_rank + 1}` });
  if (h.rerank != null) s.push({ label: `juiz ${h.rerank}/10`, tone: h.rerank >= 6 ? "alta" : h.rerank <= 2 ? "baixa" : "media" });
  return s;
}

function DetalhesDoHit({ h, rrfK }: { h: Hit; rrfK: number }) {
  return (
    <div className={css.detalhes}>
      <div className={css.colunaScore}>
        <div className="rotulo">Como o score foi montado</div>
        <ScoreBreakdown
          vecRank={h.vec_rank != null ? h.vec_rank + 1 : null}
          ftsRank={h.fts_rank != null ? h.fts_rank + 1 : null}
          rrfK={rrfK}
          factors={h.fatores}
        />
      </div>
      <MetaList
        items={[
          { k: "section", v: h.secao || "(raiz)" },
          { k: "note_kind", v: h.tipo },
          { k: "note_ts", v: h.data ? `${dataDoNome(h.data)} (do nome)` : "—", hint: "data do evento, tirada do nome do arquivo" },
          { k: "mtime", v: dataHora(h.mtime), hint: "última edição; pesa 1/3 no frescor" },
          { k: "vec_score", v: decimal(h.vec_score) },
          { k: "rerank", v: h.rerank != null ? `${h.rerank}/10` : "não julgado" },
          { k: "backlinks", v: h.backlinks },
          { k: "chunk_id · linha", v: `${h.chunk_id} · L${h.linha}` },
          { k: "heading_path", v: trilha(h.heading), wide: true },
        ]}
      />
    </div>
  );
}

function Aviso({ r }: { r: Resultado }) {
  if (!r.hits.length) {
    return (
      <Callout tone="baixa" title="Nada no vault sobre isso">
        Nenhum trecho passou nem pelo lado literal nem pelo semântico. Vale tentar com outras palavras, ou anotar a resposta
        quando descobrir.
      </Callout>
    );
  }
  if (!r.semantico) {
    return (
      <Callout tone="media" title="Só busca literal: o Ollama não respondeu">
        Sem o embedding da pergunta, a busca caiu para palavra exata e não dá para medir confiança. Veja a tela de Modelos.
      </Callout>
    );
  }
  const juiz = r.juiz != null ? ` · juiz ${r.juiz.toFixed(1)}/10` : "";
  if (r.faixa === "media") {
    return (
      <Callout tone="media" title={`Confiança média · sim ${decimal(r.sim)}${juiz}`}>
        {r.juiz != null
          ? "Nem a similaridade nem o juiz local decidiram. Leia o trecho e decida se ele responde, em vez de assumir que sim por ter vindo no topo."
          : "Esta faixa tem tanto pergunta legítima escrita com outras palavras quanto pergunta que o vault não responde. Leia o trecho antes de confiar."}
      </Callout>
    );
  }
  if (r.faixa === "baixa") {
    // O motivo muda conforme o literal casou ou nao: com casamento, a
    // palavra existe no vault com outro sentido; sem, o que aparece e so o
    // menos distante de um vault que nao fala disso.
    const literal = r.hits.some((h) => h.fts_rank != null);
    return (
      <Callout tone="baixa" title={`Confiança baixa · sim ${decimal(r.sim)}${juiz}`}>
        {literal
          ? "Nenhum trecho tem relação de sentido com a pergunta. O que segue casou por palavra literal, e quase sempre a palavra existe no vault com outro sentido."
          : "Nenhum trecho tem relação de sentido com a pergunta, e nenhuma palavra dela aparece no vault. O que segue são só os trechos menos distantes."}{" "}
        Trate como “o vault não responde isso”.
      </Callout>
    );
  }
  return null;
}

function Recentes({ secao }: { secao?: string }) {
  const { dados: notas } = useDados(() => api.notas(secao, 12), [secao]);
  if (!notas?.length) return null;
  return (
    <section className={css.recentes}>
      <div className="rotulo">{secao ? `Em ${secao}` : "Editadas por último"}</div>
      <ul className={css.lista}>
        {notas.map((n, i) => (
          <li key={n.path} style={{ animationDelay: `${i * 30}ms` }}>
            <a href={hrefNota(n.path)} className={css.linhaNota}>
              <FileText size={15} className={css.iconeNota} />
              <span className={css.tituloNota}>{n.title || n.path}</span>
              <span className={css.caminhoNota}>{n.path}</span>
              {n.note_kind !== "nota" && <Badge>{tipoNota(n.note_kind)}</Badge>}
              <span className={css.quando} title={dataHora(n.mtime)}>
                <Clock size={12} /> {idade(n.mtime)}
              </span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Busca({ params }: { params: URLSearchParams }) {
  const { estado, setOcupado } = useApp();
  const consulta = params.get("q") ?? "";
  const secao = params.get("secao") ?? "";
  const [texto, setTexto] = useState(consulta);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [rodando, setRodando] = useState(false);

  useEffect(() => setTexto(consulta), [consulta]);

  // A busca mora na URL: voltar da nota para ca refaz a mesma busca, e o
  // botao de voltar do navegador anda entre buscas.
  useEffect(() => {
    if (!consulta) {
      setResultado(null);
      return;
    }
    let vivo = true;
    setRodando(true);
    setOcupado(true);
    setErro(null);
    setResultado(null);
    api
      .buscar(consulta, secao || undefined)
      .then((r) => vivo && setResultado(r))
      .catch((e) => vivo && setErro(e instanceof ErroApi ? e : new ErroApi(0, String(e))))
      .finally(() => {
        if (vivo) setRodando(false);
        setOcupado(false);
      });
    return () => {
      vivo = false;
    };
  }, [consulta, secao, setOcupado]);

  const enviar = (e?: FormEvent, q = texto) => {
    e?.preventDefault();
    if (q.trim()) navegar("buscar", { q: q.trim(), secao: secao || undefined });
  };

  const secoes = estado.secoes ?? [];
  const r = resultado;

  return (
    <div className="tela-conteudo" style={{ maxWidth: "var(--content-max)" }}>
      <div className="tela-titulo">
        <h1>{secao ? secao : "Pergunte ao vault"}</h1>
        <p>
          Pergunta conceitual ou identificador exato — hostname, IP, código de erro. Os dois funcionam, porque a busca funde
          o lado semântico com o literal.
        </p>
      </div>

      <form className={css.barra} onSubmit={enviar} role="search">
        <Input
          id="busca"
          size="lg"
          icon={Search}
          autoFocus
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="o que eu decidi sobre o backup?"
          aria-label="Pergunta"
          className={css.campo}
          trailing={<kbd className={css.atalho}>Ctrl K</kbd>}
        />
        <Select
          aria-label="Seção"
          value={secao}
          onChange={(s) => navegar("buscar", { q: consulta || undefined, secao: s || undefined })}
          options={[{ value: "", label: "Todas as seções" }, ...secoes.map((s) => s.nome)]}
          className={css.secao}
        />
        <Button type="submit" variant="primary" size="lg" disabled={!texto.trim()} loading={rodando}>
          Buscar
        </Button>
      </form>

      {consulta && (
        <div className={css.pipeline}>
          <SearchPipeline chave={consulta + secao} rodando={rodando} resultado={r} modelo={estado.modelo ?? ""} />
        </div>
      )}

      {erro && (
        <Callout tone="baixa" title="A busca falhou">
          {erro.message}
        </Callout>
      )}

      {r && (
        <>
          <div className={css.resumo}>
            {r.faixa ? <ConfidenceBadge faixa={r.faixa} sim={r.sim} animate /> : <Badge tone="media">sem faixa</Badge>}
            <ScoreMeter value={r.sim} duvidoso={r.limiares.duvidoso} confiavel={r.limiares.confiavel} />
            <span className={css.tempo}>
              {numero(r.hits.length)} trechos · {r.segundos.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} s
            </span>
          </div>
          <div className={css.aviso}>
            <Aviso r={r} />
          </div>
          <div className={css.resultados}>
            {r.hits.map((h, i) => (
              <ResultCard
                key={h.chunk_id}
                rank={i + 1}
                path={h.path}
                line={h.linha}
                heading={trilha(h.heading)}
                snippet={previa(h.trecho)}
                date={h.data ? dataDoNome(h.data) : data(h.mtime)}
                age={idade(h.data ?? h.mtime)}
                kind={tipoNota(h.tipo)}
                signals={sinais(h)}
                href={hrefNota(h.path, h.linha)}
                details={<DetalhesDoHit h={h} rrfK={r.rrf_k} />}
              />
            ))}
          </div>
          <CommandBlock
            command={`vault-vector search "${r.consulta}"${secao ? ` --section ${secao}` : ""}`}
            comment="a mesma busca no terminal"
          />
        </>
      )}

      {!consulta && (
        <>
          <div className={css.dica}>
            <CornerDownLeft size={14} />
            Enter busca. Abrir um resultado leva para a nota inteira, com o trecho marcado.
          </div>
          <Recentes secao={secao || undefined} />
        </>
      )}
    </div>
  );
}
