import type { LucideIcon } from "lucide-react";
import { LoaderCircle } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import css from "./Button.module.css";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const ICONE: Record<Size, number> = { sm: 15, md: 16, lg: 17 };

interface Props extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  variant?: Variant;
  size?: Size;
  icon?: LucideIcon;
  iconRight?: LucideIcon;
  /** Troca o icone por um spinner e bloqueia o clique repetido. */
  loading?: boolean;
  full?: boolean;
  children?: ReactNode;
}

export function Button({
  variant = "secondary",
  size = "md",
  icon: Icone,
  iconRight: IconeDireita,
  loading,
  full,
  disabled,
  className = "",
  type = "button",
  children,
  ...resto
}: Props) {
  const tam = ICONE[size];
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`${css.botao} ${css[variant]} ${css[size]} ${full ? css.full : ""} ${className}`}
      {...resto}
    >
      {loading ? <LoaderCircle size={tam} className={css.girando} /> : Icone && <Icone size={tam} />}
      {children}
      {IconeDireita && <IconeDireita size={tam} />}
    </button>
  );
}

interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  icon: LucideIcon;
  /** Obrigatorio: e o nome acessivel e a dica do botao. */
  label: string;
  size?: "sm" | "md";
  active?: boolean;
}

export function IconButton({ icon: Icone, label, size = "md", active, className = "", type = "button", ...resto }: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      aria-pressed={active}
      className={`${css.icone} ${size === "sm" ? css.iconeSm : ""} ${active ? css.ativo : ""} ${className}`}
      {...resto}
    >
      <Icone size={size === "sm" ? 15 : 18} />
    </button>
  );
}
