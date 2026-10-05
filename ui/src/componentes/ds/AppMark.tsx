import { useEffect, useState } from "react";
import css from "./AppMark.module.css";

interface Props {
  size?: number;
  /** Fundo arredondado atras do V. Sem ele, so os tracos. */
  tile?: boolean;
  /** Redesenha a marca toda vez que vira true: o app esta trabalhando. */
  active?: boolean;
}

/** O V do vetor: dois tracos que convergem num ponto. */
export function AppMark({ size = 32, tile = true, active = false }: Props) {
  const [rodada, setRodada] = useState(0);
  useEffect(() => {
    if (active) setRodada((n) => n + 1);
  }, [active]);

  const desenho = active ? css.desenho : undefined;
  return (
    <svg key={rodada} width={size} height={size} viewBox="0 0 512 512" role="img" aria-label="vault-vector" className={css.marca}>
      {tile && (
        <>
          <rect width="512" height="512" rx="116" fill="#121415" />
          <rect x="2" y="2" width="508" height="508" rx="114" fill="none" stroke="#262b2d" strokeWidth="4" />
        </>
      )}
      <path className={desenho} d="M140 140 L256 366" stroke="#2bb3a6" strokeWidth="50" strokeLinecap="round" fill="none" />
      <path
        className={desenho}
        style={{ animationDelay: "90ms" }}
        d="M372 140 L256 366"
        stroke="#eef1ef"
        strokeWidth="50"
        strokeLinecap="round"
        fill="none"
      />
      <circle className={active ? css.ponto : undefined} cx="256" cy="366" r="46" fill="#5fdccd" stroke="#121415" strokeWidth="16" />
    </svg>
  );
}
