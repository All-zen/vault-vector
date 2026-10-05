import type { ReactNode } from "react";
import css from "./ProgressBar.module.css";

interface Props {
  /** 0 a 1. null = andamento desconhecido: a barra corre sem chegar a lugar nenhum. */
  value: number | null;
  label?: ReactNode;
  detail?: ReactNode;
}

export function ProgressBar({ value, label, detail }: Props) {
  const v = value == null ? null : Math.max(0, Math.min(1, value));
  return (
    <div className={css.progresso}>
      {(label || detail) && (
        <div className={css.legenda}>
          <span className={css.rotulo}>{label}</span>
          <span className={css.detalhe}>{detail}</span>
        </div>
      )}
      <div
        className={css.trilho}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={v == null ? undefined : Math.round(v * 100)}
      >
        <div
          className={`${css.barra} ${v == null ? css.indeterminada : ""} ${v != null && v > 0 && v < 1 ? css.brilho : ""}`}
          style={v == null ? undefined : { width: `${v * 100}%` }}
        />
      </div>
    </div>
  );
}
