import { CircleAlert, CircleCheck, CircleHelp, Info, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import css from "./Callout.module.css";

type CalloutTone = "info" | "alta" | "media" | "baixa";

const ICONES: Record<CalloutTone, LucideIcon> = {
  info: Info,
  alta: CircleCheck,
  media: CircleHelp,
  baixa: CircleAlert,
};

interface Props {
  tone?: CalloutTone;
  title?: ReactNode;
  action?: ReactNode;
  children?: ReactNode;
}

export function Callout({ tone = "info", title, action, children }: Props) {
  const Icone = ICONES[tone];
  return (
    <div role="note" className={`${css.callout} ${css[tone]}`}>
      <Icone size={18} className={css.icone} />
      <div className={css.corpo}>
        {title && <div className={css.titulo}>{title}</div>}
        {children && <div className={css.texto}>{children}</div>}
      </div>
      {action}
    </div>
  );
}
