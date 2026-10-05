import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import css from "./Navigation.module.css";

interface NavItemProps {
  icon?: LucideIcon;
  label: ReactNode;
  href: string;
  active?: boolean;
  count?: number | string;
  title?: string;
}

/** Item da barra lateral. E link de verdade: abre em rota, funciona com o voltar. */
export function NavItem({ icon: Icone, label, href, active, count, title }: NavItemProps) {
  return (
    <a href={href} title={title} aria-current={active ? "page" : undefined} className={`${css.item} ${active ? css.ativo : ""}`}>
      {Icone && <Icone size={16} className={css.icone} />}
      <span className={css.rotulo}>{label}</span>
      {count != null && <span className={css.contagem}>{count}</span>}
    </a>
  );
}

interface Aba {
  id: string;
  label: ReactNode;
  count?: number;
}

interface TabsProps {
  items: Aba[];
  value: string;
  onChange: (id: string) => void;
}

export function Tabs({ items, value, onChange }: TabsProps) {
  return (
    <div role="tablist" className={css.abas}>
      {items.map((it) => (
        <button
          key={it.id}
          type="button"
          role="tab"
          aria-selected={it.id === value}
          className={`${css.aba} ${it.id === value ? css.abaAtiva : ""}`}
          onClick={() => onChange(it.id)}
        >
          {it.label}
          {it.count != null && <span className={css.contagem}>{it.count}</span>}
        </button>
      ))}
    </div>
  );
}
