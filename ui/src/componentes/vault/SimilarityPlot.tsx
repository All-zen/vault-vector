import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import css from "./SimilarityPlot.module.css";

export interface Ponto {
  sim: number;
  label: string;
}

interface Props {
  dentro: Ponto[];
  fora: Ponto[];
  duvidoso: number;
  confiavel: number;
  onChange?: (limiares: { duvidoso: number; confiavel: number }) => void;
}

type Faixa = "alta" | "media" | "baixa";

/**
 * Cada ponto e uma pergunta medida no vault. As duas linhas sao os cortes
 * do config; arrastar mostra quais perguntas mudariam de faixa.
 *
 * A escala acompanha os dados em vez de ficar fixa: num vault em que tudo
 * mede entre 0,30 e 0,45, uma escala de 0 a 1 juntaria os pontos num bolo.
 */
export function SimilarityPlot({ dentro, fora, duvidoso, confiavel, onChange }: Props) {
  const area = useRef<HTMLDivElement>(null);
  const [arrastando, setArrastando] = useState<"lo" | "hi" | null>(null);

  // A escala sai dos pontos e da faixa padrao, nunca das alcas: se as
  // alcas entrassem na conta, a regua andaria embaixo do cursor no arraste.
  const todos = [...dentro, ...fora].map((p) => p.sim).concat(0.43, 0.6);
  const min = Math.floor((Math.min(...todos) - 0.03) * 20) / 20;
  const max = Math.ceil((Math.max(...todos) + 0.03) * 20) / 20;
  const x = (v: number) => ((v - min) / (max - min)) * 100;
  const faixa = (v: number): Faixa => (v >= confiavel ? "alta" : v >= duvidoso ? "media" : "baixa");

  const mover = (qual: "lo" | "hi", v: number) => {
    if (!onChange) return;
    const r = Math.round(v * 100) / 100;
    if (qual === "lo") onChange({ duvidoso: Math.max(min, Math.min(r, confiavel - 0.02)), confiavel });
    else onChange({ duvidoso, confiavel: Math.min(max, Math.max(r, duvidoso + 0.02)) });
  };

  useEffect(() => {
    if (!arrastando) return;
    const mv = (e: PointerEvent) => {
      const r = area.current?.getBoundingClientRect();
      if (r) mover(arrastando, min + ((e.clientX - r.left) / r.width) * (max - min));
    };
    const solta = () => setArrastando(null);
    window.addEventListener("pointermove", mv);
    window.addEventListener("pointerup", solta);
    return () => {
      window.removeEventListener("pointermove", mv);
      window.removeEventListener("pointerup", solta);
    };
  });

  const teclado = (qual: "lo" | "hi", atual: number) => (e: KeyboardEvent) => {
    const passo = e.shiftKey ? 0.05 : 0.01;
    if (e.key === "ArrowLeft" || e.key === "ArrowDown") mover(qual, atual - passo);
    else if (e.key === "ArrowRight" || e.key === "ArrowUp") mover(qual, atual + passo);
    else return;
    e.preventDefault();
  };

  const linha = (pontos: Ponto[], tipo: "dentro" | "fora", atraso: number) =>
    pontos.map((p, i) => (
      <span
        key={`${tipo}-${p.label}`}
        title={`${p.label}\nsimilaridade ${p.sim.toFixed(3)}`}
        className={`${css.ponto} ${css[tipo]} ${css[faixa(p.sim)]}`}
        style={{ left: `${x(p.sim)}%`, animationDelay: `${(atraso + i) * 45}ms` }}
      />
    ));

  const alca = (qual: "lo" | "hi", valor: number, nome: string) => (
    <div
      role="slider"
      tabIndex={onChange ? 0 : -1}
      aria-label={nome}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={valor}
      aria-valuetext={valor.toFixed(2)}
      className={`${css.alca} ${css[qual]} ${arrastando === qual ? css.arrastando : ""}`}
      style={{ left: `${x(valor)}%`, cursor: onChange ? "ew-resize" : "default" }}
      onPointerDown={(e) => {
        e.preventDefault();
        if (onChange) setArrastando(qual);
      }}
      onKeyDown={teclado(qual, valor)}
    >
      <span />
    </div>
  );

  return (
    <div className={css.grafico}>
      <span />
      <div className={css.valores}>
        <span className={css.vLo} style={{ left: `${x(duvidoso)}%` }}>{duvidoso.toFixed(2)}</span>
        <span className={css.vHi} style={{ left: `${x(confiavel)}%` }}>{confiavel.toFixed(2)}</span>
      </div>

      <div className={css.rotulos}>
        <span>com resposta</span>
        <span>sem resposta</span>
      </div>
      <div ref={area} className={css.area}>
        <div className={css.zonas}>
          <span className={css.zBaixa} style={{ width: `${x(duvidoso)}%` }} />
          <span className={css.zMedia} style={{ width: `${x(confiavel) - x(duvidoso)}%` }} />
          <span className={css.zAlta} />
        </div>
        <div className={css.metadeCima}>{linha(dentro, "dentro", 0)}</div>
        <div className={css.metadeBaixo}>{linha(fora, "fora", dentro.length)}</div>
        {alca("lo", duvidoso, "sim_duvidoso: abaixo disso, confiança baixa")}
        {alca("hi", confiavel, "sim_confiavel: acima disso, confiança alta")}
      </div>

      <span />
      <div className={css.eixo}>
        <span>{min.toFixed(2)}</span>
        <span>similaridade de cosseno</span>
        <span>{max.toFixed(2)}</span>
      </div>
    </div>
  );
}
