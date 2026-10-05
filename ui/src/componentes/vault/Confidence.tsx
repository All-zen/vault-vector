import { CircleAlert, CircleCheck, CircleHelp } from "lucide-react";
import { useEffect, useState } from "react";
import type { Faixa } from "../../api/tipos";
import css from "./Confidence.module.css";

const FAIXAS = {
  alta: { rotulo: "Confiança alta", curto: "alta", Icone: CircleCheck },
  media: { rotulo: "Confiança média", curto: "média", Icone: CircleHelp },
  baixa: { rotulo: "Confiança baixa", curto: "baixa", Icone: CircleAlert },
};

interface BadgeProps {
  faixa: Faixa;
  sim?: number | null;
  size?: "sm" | "md";
  compact?: boolean;
  animate?: boolean;
}

/** A faixa de confianca de uma busca: alta, media ou baixa. */
export function ConfidenceBadge({ faixa, sim, size = "md", compact, animate }: BadgeProps) {
  const { rotulo, curto, Icone } = FAIXAS[faixa];
  return (
    <span className={`${css.selo} ${css[faixa]} ${size === "sm" ? css.sm : ""} ${animate ? css.animar : ""}`}>
      <Icone size={size === "sm" ? 13 : 15} />
      {compact ? curto : rotulo}
      {sim != null && <span className={css.sim}>{sim.toFixed(3)}</span>}
    </span>
  );
}

interface MeterProps {
  value: number | null;
  duvidoso: number;
  confiavel: number;
  min?: number;
  max?: number;
}

/**
 * Onde a melhor similaridade caiu, contra as duas linhas de corte.
 *
 * A regua mostra as tres zonas com os limiares do config, nao fixos: se a
 * pessoa calibrou o vault dela, o medidor acompanha.
 */
export function ScoreMeter({ value, duvidoso, confiavel, min = 0.3, max = 0.8 }: MeterProps) {
  const [mostrado, setMostrado] = useState(min);
  useEffect(() => {
    const id = requestAnimationFrame(() => setMostrado(value ?? min));
    return () => cancelAnimationFrame(id);
  }, [value, min]);

  const pos = (v: number) => ((Math.max(min, Math.min(max, v)) - min) / (max - min)) * 100;
  const zona: Faixa = value == null ? "baixa" : value >= confiavel ? "alta" : value >= duvidoso ? "media" : "baixa";
  return (
    <div className={css.medidor}>
      <div className={css.regua}>
        <div className={css.zonas}>
          <span className={css.zBaixa} style={{ width: `${pos(duvidoso)}%` }} />
          <span className={css.zMedia} style={{ width: `${pos(confiavel) - pos(duvidoso)}%` }} />
          <span className={css.zAlta} />
        </div>
        {value != null && (
          <span className={`${css.agulha} ${css[`agulha_${zona}`]}`} style={{ left: `${pos(mostrado)}%` }} />
        )}
      </div>
      <div className={css.escala}>
        <span style={{ left: 0 }}>{min.toFixed(2)}</span>
        <span className={css.eMedia} style={{ left: `${pos(duvidoso)}%` }}>{duvidoso.toFixed(2)}</span>
        <span className={css.eAlta} style={{ left: `${pos(confiavel)}%` }}>{confiavel.toFixed(2)}</span>
        <span style={{ right: 0 }}>{max.toFixed(2)}</span>
      </div>
    </div>
  );
}
