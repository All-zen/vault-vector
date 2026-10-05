import { numero } from "../../lib/formato";
import { previa } from "../../lib/markdown";
import css from "./Visuals.module.css";

interface IndexGridProps {
  /** Notas no disco. */
  total: number;
  /** Posicoes (na ordem alfabetica do vault) das notas que mudaram. */
  pending: number[];
  /** 0 a 1 durante uma reindexacao; as pendentes acendem na ordem. */
  progress?: number;
  maxCells?: number;
}

/**
 * Mapa do indice: cada celula e uma nota (ou um grupo, em vault grande).
 *
 * A ordem e a mesma em que a indexacao percorre o vault, entao as celulas
 * acendem na sequencia real do trabalho.
 */
export function IndexGrid({ total, pending, progress = 0, maxCells = 360 }: IndexGridProps) {
  const porCelula = Math.max(1, Math.ceil(total / maxCells));
  const celulas = Math.max(1, Math.ceil(total / porCelula));
  const pendentes = new Map<number, number>();
  pending.forEach((pos, ordem) => {
    const c = Math.floor(pos / porCelula);
    if (!pendentes.has(c)) pendentes.set(c, ordem);
  });
  const feitas = Math.round(progress * pending.length);

  return (
    <div className={css.mapa}>
      <div className={css.grade} role="img" aria-label={`${numero(total)} notas, ${pending.length} pendentes`}>
        {Array.from({ length: celulas }, (_, i) => {
          const ordem = pendentes.get(i);
          const pendente = ordem !== undefined;
          const refeita = pendente && ordem < feitas;
          return (
            <span
              key={i}
              className={`${css.celula} ${pendente && !refeita ? css.pendente : ""} ${refeita ? css.refeita : ""}`}
            />
          );
        })}
      </div>
      <span className={css.escala}>{porCelula === 1 ? "1 célula = 1 nota" : `1 célula ≈ ${porCelula} notas`}</span>
    </div>
  );
}

interface VectorStripProps {
  values: number[];
  columns?: number;
  cell?: number;
}

/** Um embedding desenhado: cada quadrado e uma dimensao, a cor e o sinal. */
export function VectorStrip({ values, columns = 64, cell = 8 }: VectorStripProps) {
  const maior = values.reduce((m, v) => Math.max(m, Math.abs(v)), 0) || 1;
  return (
    <div className={css.vetor} style={{ gridTemplateColumns: `repeat(${columns}, ${cell}px)` }} role="img" aria-label={`vetor de ${values.length} dimensões`}>
      {values.map((v, i) => {
        const a = 0.12 + (Math.abs(v) / maior) * 0.88;
        return (
          <span
            key={i}
            style={{
              width: cell,
              height: cell,
              background: v >= 0 ? `rgba(95, 220, 205, ${a})` : `rgba(243, 126, 102, ${a})`,
              animationDelay: `${(i % columns) * 9 + Math.floor(i / columns) * 4}ms`,
            }}
          />
        );
      })}
    </div>
  );
}

const CORES = ["var(--vv-400)", "var(--alta-fg)", "var(--media-fg)", "#9aa7ff", "var(--baixa-fg)", "#c79bf2"];

interface Trecho {
  ord: number;
  heading: string;
  linha: number;
  chars: number;
  inicio: string;
}

/** Como uma nota real fica cortada com os parametros de recorte atuais. */
export function ChunkPreview({ trechos, target }: { trechos: Trecho[]; target: number }) {
  return (
    <div className={css.recorte}>
      <div className={css.faixa}>
        {trechos.map((t, i) => (
          <span key={`${t.ord}-${t.chars}`} style={{ flex: t.chars, background: CORES[i % CORES.length] }} />
        ))}
      </div>
      {trechos.map((t, i) => {
        const cor = CORES[i % CORES.length];
        return (
          <div key={`${t.ord}-${t.chars}-${t.linha}`} className={css.trecho}>
            <div className={css.trechoTopo} style={{ color: cor }}>
              <span className={css.quadrado} style={{ background: cor }} />
              trecho {i + 1}
              <span className={css.apagado}>
                · {numero(t.chars)} chars · L{t.linha}
              </span>
              <span className={css.ocupacao} title={`${Math.round((t.chars / target) * 100)}% do tamanho alvo`}>
                <i style={{ width: `${Math.min(100, (t.chars / target) * 100)}%`, background: t.chars > target ? "var(--media-fg)" : cor }} />
              </span>
            </div>
            {t.heading && <div className={css.trilha}>{t.heading.split(" > ").join(" › ")}</div>}
            <div className={css.inicio}>{previa(t.inicio)}</div>
          </div>
        );
      })}
    </div>
  );
}
