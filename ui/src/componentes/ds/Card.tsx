import type { CSSProperties, ReactNode } from "react";
import css from "./Card.module.css";

interface Props {
  padding?: number;
  selected?: boolean;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}

export function Card({ padding = 20, selected, className = "", style, children }: Props) {
  return (
    <div className={`${css.card} ${selected ? css.selected : ""} ${className}`} style={{ padding, ...style }}>
      {children}
    </div>
  );
}

/** Titulo, subtitulo e acao de um card, no padrao das telas. */
export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className={css.header}>
      <div className={css.textos}>
        <div className={css.titulo}>{title}</div>
        {subtitle && <div className={css.sub}>{subtitle}</div>}
      </div>
      {action}
    </div>
  );
}
