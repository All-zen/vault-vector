import { Check, ChevronsUpDown } from "lucide-react";
import type { ReactNode } from "react";
import css from "./Forms.module.css";

// Select, Checkbox, Switch e Slider: controles pequenos, sempre sobre o
// elemento nativo. Teclado, leitor de tela e foco vem de graca.

interface SelectProps {
  value: string;
  onChange: (valor: string) => void;
  options: (string | { value: string; label: string })[];
  label?: ReactNode;
  size?: "sm" | "md";
  "aria-label"?: string;
  className?: string;
}

export function Select({ value, onChange, options, label, size = "md", className = "", ...aria }: SelectProps) {
  return (
    <label className={`${css.campo} ${className}`}>
      {label && <span className={css.rotulo}>{label}</span>}
      <span className={css.selectCaixa}>
        <select
          className={`${css.select} ${size === "sm" ? css.selectSm : ""}`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          {...aria}
        >
          {options.map((o) => {
            const v = typeof o === "string" ? o : o.value;
            return (
              <option key={v} value={v}>
                {typeof o === "string" ? o : o.label}
              </option>
            );
          })}
        </select>
        <ChevronsUpDown size={14} className={css.seta} />
      </span>
    </label>
  );
}

interface CheckboxProps {
  checked: boolean;
  onChange: (marcado: boolean) => void;
  label: ReactNode;
  disabled?: boolean;
}

export function Checkbox({ checked, onChange, label, disabled }: CheckboxProps) {
  return (
    <label className={`${css.linha} ${disabled ? css.desligado : ""}`}>
      <input
        type="checkbox"
        className={css.nativo}
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className={css.quadrado} aria-hidden>
        {checked && <Check size={12} strokeWidth={3} />}
      </span>
      <span className={css.texto}>{label}</span>
    </label>
  );
}

interface SwitchProps {
  checked: boolean;
  onChange: (ligado: boolean) => void;
  label?: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
}

export function Switch({ checked, onChange, label, description, disabled }: SwitchProps) {
  return (
    <label className={`${css.switchLinha} ${disabled ? css.desligado : ""}`}>
      <input
        type="checkbox"
        role="switch"
        className={css.nativo}
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className={css.trilho} aria-hidden>
        <span className={css.botao} />
      </span>
      {(label || description) && (
        <span className={css.textos}>
          {label && <span className={css.switchRotulo}>{label}</span>}
          {description && <span className={css.descricao}>{description}</span>}
        </span>
      )}
    </label>
  );
}

interface SliderProps {
  value: number;
  onChange: (valor: number) => void;
  min: number;
  max: number;
  step: number;
  label?: ReactNode;
  format?: (v: number) => string;
  "aria-label"?: string;
}

export function Slider({ value, onChange, min, max, step, label, format, ...aria }: SliderProps) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <label className={css.slider}>
      {label && (
        <span className={css.sliderTopo}>
          <span className={css.rotulo}>{label}</span>
          <span className={css.sliderValor}>{format ? format(value) : value}</span>
        </span>
      )}
      <span className={css.sliderLinha}>
        <input
          type="range"
          className={css.range}
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          style={{ background: `linear-gradient(to right, var(--accent) ${pct}%, var(--paper-3) ${pct}%)` }}
          {...aria}
        />
        {!label && <span className={css.sliderValor}>{format ? format(value) : value}</span>}
      </span>
    </label>
  );
}
