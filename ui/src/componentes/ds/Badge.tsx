import type { ReactNode } from "react";
import css from "./Badge.module.css";

export type Tone = "neutral" | "accent" | "alta" | "media" | "baixa";

interface Props {
  tone?: Tone;
  mono?: boolean;
  title?: string;
  children: ReactNode;
}

export function Badge({ tone = "neutral", mono, title, children }: Props) {
  return (
    <span className={`${css.badge} ${css[tone]} ${mono ? css.mono : ""}`} title={title}>
      {children}
    </span>
  );
}
