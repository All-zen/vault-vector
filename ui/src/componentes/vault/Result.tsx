import { ChevronDown, FileText } from "lucide-react";
import { useEffect, useState, type MouseEvent, type ReactNode } from "react";
import { Badge, type Tone } from "../ds";
import css from "./Result.module.css";

export interface Sinal {
  label: string;
  tone?: Tone;
}

interface ResultCardProps {
  rank: number;
  path: string;
  line?: number;
  heading: string;
  snippet?: string;
  date?: string;
  age?: string;
  kind?: string;
  signals?: Sinal[];
  href: string;
  details?: ReactNode;
}

/**
 * Um resultado da busca. O titulo e um link de verdade (teclado, abrir em
 * outra aba), e o cartao inteiro tambem responde ao clique.
 */
export function ResultCard({ rank, path, line, heading, snippet, date, age, kind, signals = [], href, details }: ResultCardProps) {
  const [aberto, setAberto] = useState(false);
  const abrir = (e: MouseEvent) => {
    // Selecionar texto do trecho nao pode virar navegacao.
    if (window.getSelection()?.toString()) return;
    if ((e.target as HTMLElement).closest("a, button, [data-detalhes]")) return;
    window.location.hash = href;
  };

  return (
    <article className={css.cartao} style={{ animationDelay: `${(rank - 1) * 70}ms` }} onClick={abrir}>
      <span className={css.rank}>{String(rank).padStart(2, "0")}</span>
      <div className={css.corpo}>
        <div className={css.caminho}>
          <FileText size={13} />
          <span className={css.caminhoTexto}>{path}</span>
          {line ? <span className={css.linha}>L{line}</span> : null}
        </div>
        <a className={css.titulo} href={href}>
          {heading}
        </a>
        {snippet && <div className={css.trecho}>{snippet}</div>}
        <div className={css.selos}>
          {date && (
            <Badge mono>
              {date}
              {age ? ` · ${age}` : ""}
            </Badge>
          )}
          {kind && kind !== "nota" && <Badge>{kind}</Badge>}
          {signals.map((s) => (
            <Badge key={s.label} mono tone={s.tone}>
              {s.label}
            </Badge>
          ))}
          {details && (
            <button
              type="button"
              className={`${css.detalhesBotao} ${aberto ? css.detalhesAberto : ""}`}
              aria-expanded={aberto}
              onClick={() => setAberto(!aberto)}
            >
              <ChevronDown size={12} className={css.seta} />
              Como subiu
            </button>
          )}
        </div>
        {details && (
          <div className={`${css.gaveta} ${aberto ? css.gavetaAberta : ""}`} data-detalhes>
            <div className={css.gavetaDentro}>{aberto && <div className={css.detalhes}>{details}</div>}</div>
          </div>
        )}
      </div>
    </article>
  );
}

interface BreakdownProps {
  /** Posicao base 1 em cada ranker; null = o ranker nao trouxe este trecho. */
  vecRank: number | null;
  ftsRank: number | null;
  rrfK: number;
  factors: [string, number][];
}

/**
 * Como o score foi montado: RRF dos dois rankers vezes os fatores de boost.
 *
 * score = 1/(k + pos_semantico) + 1/(k + pos_literal), vezes cada fator. E a
 * conta do store.py, nao uma ilustracao: o total bate com o score do hit.
 */
export function ScoreBreakdown({ vecRank, ftsRank, rrfK, factors }: BreakdownProps) {
  const [visivel, setVisivel] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setVisivel(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const sem = vecRank != null ? 1 / (rrfK + vecRank) : 0;
  const lit = ftsRank != null ? 1 / (rrfK + ftsRank) : 0;
  const boost = factors.reduce((a, [, x]) => a * x, 1);
  const base = sem + lit;
  const total = base * boost;
  // O maximo possivel e primeiro lugar nos dois lados, com folga para boost.
  const escala = (2 / (rrfK + 1)) * 1.45;
  const largura = (v: number) => `${visivel ? (Math.max(0, v) / escala) * 100 : 0}%`;
  const f4 = (v: number) => v.toFixed(4);

  return (
    <div className={css.breakdown}>
      <div className={css.barras} role="img" aria-label={`score ${f4(total)}`}>
        <span style={{ width: largura(sem), background: "var(--vv-500)" }} />
        <span style={{ width: largura(lit), background: "var(--ink-2)", transitionDelay: "150ms" }} />
        <span
          style={{
            width: largura(total - base),
            background: total >= base ? "var(--alta-fg)" : "transparent",
            transitionDelay: "300ms",
          }}
        />
      </div>
      <div className={css.formula}>
        <span className={css.fSem}>{vecRank != null ? `1/(${rrfK}+${vecRank})` : "—"}</span>
        {" + "}
        <span className={css.fLit}>{ftsRank != null ? `1/(${rrfK}+${ftsRank})` : "—"}</span>
        {` = ${f4(base)}`}
        {factors.length > 0 && (
          <>
            {" × "}
            <span className={boost >= 1 ? css.fMais : css.fMenos}>{boost.toFixed(3)}</span>
            {" = "}
            <b>{f4(total)}</b>
          </>
        )}
      </div>
      {factors.length > 0 && (
        <div className={css.fatores}>
          {factors.map(([nome, x]) => (
            <span key={nome} className={x >= 1 ? css.fMais : css.fMenos}>
              {nome} ×{x.toFixed(3)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
