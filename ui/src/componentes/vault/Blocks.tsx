import { Check, CircleCheck, CircleX, Copy, TriangleAlert } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { StatusItem } from "../../api/tipos";
import css from "./Blocks.module.css";

interface CommandProps {
  command: string;
  comment?: string;
}

/** O mesmo que a tela faz, no terminal. Copiavel. */
export function CommandBlock({ command, comment }: CommandProps) {
  const [copiado, setCopiado] = useState(false);
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopiado(true);
      window.setTimeout(() => setCopiado(false), 1400);
    } catch {
      // Sem permissao de area de transferencia: o texto continua selecionavel.
    }
  };
  return (
    <div className={css.terminal}>
      <span className={css.prompt} aria-hidden>
        &gt;
      </span>
      <span className={css.comando}>
        {command}
        {comment && <span className={css.comentario}>{"   # " + comment}</span>}
      </span>
      <button type="button" className={`${css.copiar} ${copiado ? css.copiado : ""}`} onClick={copiar} aria-label="Copiar comando">
        {copiado ? <Check size={14} /> : <Copy size={14} />}
      </button>
    </div>
  );
}

export interface MetaItem {
  k: string;
  v: ReactNode;
  hint?: string;
  wide?: boolean;
  mono?: boolean;
}

/** Pares chave/valor com os nomes de campo do indice, como estao no SQLite. */
export function MetaList({ items, columns = 2 }: { items: MetaItem[]; columns?: number }) {
  return (
    <dl className={css.meta} style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
      {items.map((it, i) => (
        <div
          key={it.k}
          title={it.hint}
          className={css.metaItem}
          style={{ gridColumn: it.wide ? "1 / -1" : undefined, animationDelay: `${i * 35}ms` }}
        >
          <dt>{it.k}</dt>
          <dd className={it.mono === false ? css.sans : undefined}>{it.v}</dd>
        </div>
      ))}
    </dl>
  );
}

const STATUS = {
  ok: { Icone: CircleCheck, tag: "ok" },
  aviso: { Icone: TriangleAlert, tag: "aviso" },
  falta: { Icone: CircleX, tag: "falta" },
};

interface StatusProps {
  status: StatusItem;
  label: ReactNode;
  detail?: ReactNode;
  hint?: ReactNode;
  action?: ReactNode;
  index?: number;
}

/** Uma linha do diagnostico: o que foi checado, e o que fazer se faltou. */
export function StatusRow({ status, label, detail, hint, action, index = 0 }: StatusProps) {
  const { Icone, tag } = STATUS[status];
  return (
    <div className={`${css.status} ${css[status]}`} style={{ animationDelay: `${index * 60}ms` }}>
      <Icone size={18} className={css.statusIcone} />
      <div className={css.statusTextos}>
        <div className={css.statusRotulo}>{label}</div>
        {detail && <div className={css.statusDetalhe}>{detail}</div>}
        {hint && status !== "ok" && (
          <div className={css.statusDica}>
            <span aria-hidden>→</span>
            <span>{hint}</span>
          </div>
        )}
      </div>
      {action ?? <span className={css.statusTag}>{tag}</span>}
    </div>
  );
}
