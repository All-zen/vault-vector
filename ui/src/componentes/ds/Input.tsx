import type { LucideIcon } from "lucide-react";
import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";
import css from "./Input.module.css";

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  label?: ReactNode;
  hint?: ReactNode;
  icon?: LucideIcon;
  size?: "sm" | "md" | "lg";
  mono?: boolean;
  invalid?: boolean;
  trailing?: ReactNode;
}

export function Input({ label, hint, icon: Icone, size = "md", mono, invalid, trailing, className = "", style, ...resto }: Props) {
  return (
    <label className={`${css.campo} ${className}`} style={style}>
      {label && <span className={css.rotulo}>{label}</span>}
      <span className={`${css.caixa} ${css[size]} ${invalid ? css.invalido : ""} ${resto.disabled ? css.desligado : ""}`}>
        {Icone && <Icone size={size === "lg" ? 20 : 16} className={css.icone} />}
        <input className={`${css.input} ${mono ? css.mono : ""}`} aria-invalid={invalid || undefined} {...resto} />
        {trailing}
      </span>
      {hint && <span className={`${css.dica} ${invalid ? css.dicaErro : ""}`}>{hint}</span>}
    </label>
  );
}

interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: ReactNode;
}

export function TextArea({ label, className = "", ...resto }: TextAreaProps) {
  return (
    <label className={css.campo}>
      {label && <span className={css.rotulo}>{label}</span>}
      <textarea className={`${css.textarea} ${className}`} {...resto} />
    </label>
  );
}
