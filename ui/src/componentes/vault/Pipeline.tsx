import { Check, Cpu, Gauge, Merge, MessageSquare, Scale, TextSearch, Waypoints, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import type { Busca, Faixa } from "../../api/tipos";
import css from "./Pipeline.module.css";

type Estado = "parado" | "ativo" | "feito" | "pulado";

interface NoProps {
  icon: LucideIcon;
  label: string;
  detail: string;
  estado: Estado;
  tone?: Faixa;
}

function No({ icon: Icone, label, detail, estado, tone }: NoProps) {
  const feitoComTom = estado === "feito" && tone;
  return (
    <div className={`${css.no} ${css[estado]} ${feitoComTom ? css[tone] : ""}`}>
      {estado === "feito" && !tone ? <Check size={14} className={css.icone} /> : <Icone size={14} className={css.icone} />}
      <span className={css.textos}>
        <span className={css.rotulo}>{label}</span>
        <span className={css.detalhe}>{detail}</span>
      </span>
    </div>
  );
}

function Fio({ estado }: { estado: Estado }) {
  return <span className={`${css.fio} ${css[`fio_${estado}`]}`} aria-hidden />;
}

const FAIXA_TEXTO: Record<Faixa, string> = { alta: "alta", media: "média", baixa: "baixa" };
const ULTIMO = 6;

interface Props {
  /** Muda a cada busca nova, para a animacao recomecar. */
  chave: string;
  rodando: boolean;
  resultado: Busca | null;
  modelo: string;
}

/**
 * As etapas da busca hibrida, acesas conforme a requisicao anda.
 *
 * Enquanto a resposta nao chega, a animacao avanca sozinha ate a faixa e
 * espera. Quando chega, fecha o resto depressa: o pipeline nunca segura o
 * resultado na tela so para terminar de animar.
 */
export function SearchPipeline({ chave, rodando, resultado, modelo }: Props) {
  const [passo, setPasso] = useState(rodando ? 0 : ULTIMO);

  useEffect(() => {
    if (!rodando) return;
    setPasso(0);
    const id = window.setInterval(() => setPasso((p) => Math.min(p + 1, 4)), 130);
    return () => window.clearInterval(id);
  }, [rodando, chave]);

  useEffect(() => {
    if (!resultado) return;
    const id = window.setInterval(() => {
      setPasso((p) => {
        if (p >= ULTIMO) window.clearInterval(id);
        return Math.min(p + 1, ULTIMO);
      });
    }, 70);
    return () => window.clearInterval(id);
  }, [resultado]);

  const r = resultado;
  const estado = (n: number): Estado => (passo > n ? "feito" : passo === n ? "ativo" : "parado");
  const fio = (n: number): Estado => (passo > n + 1 ? "feito" : passo === n + 1 ? "ativo" : "parado");
  const juizRodou = !!r && r.julgados > 0;
  const semVetor = !!r && !r.semantico;

  return (
    <div className={css.pipeline}>
      <No icon={MessageSquare} label="Pergunta" detail="texto livre" estado={estado(0)} />
      <Fio estado={fio(0)} />
      <No
        icon={Cpu}
        label="Embedding"
        detail={semVetor ? "Ollama fora · só literal" : modelo}
        estado={estado(1)}
        tone={semVetor ? "baixa" : undefined}
      />
      <Fio estado={fio(1)} />
      <div className={css.par}>
        <No
          icon={Waypoints}
          label="Semântico"
          detail={r ? `cosseno · ${r.candidatos} cand.` : "cosseno"}
          estado={semVetor && passo > 2 ? "pulado" : estado(2)}
        />
        <No
          icon={TextSearch}
          label="Literal"
          detail={r ? `FTS5 · ${r.fts_total ?? 0} casam` : "FTS5"}
          estado={estado(2)}
        />
      </div>
      <Fio estado={fio(2)} />
      <No icon={Merge} label="Fusão RRF" detail={r ? `k = ${r.rrf_k}` : "1/(k+pos)"} estado={estado(3)} />
      <Fio estado={fio(3)} />
      <No
        icon={Scale}
        label="Juiz local"
        detail={juizRodou ? `${r.julgados} trechos · ${r.juiz?.toFixed(1)}/10` : r ? "não precisou" : "só na faixa média"}
        estado={r && !juizRodou && passo > 4 ? "pulado" : estado(4)}
      />
      <Fio estado={fio(4)} />
      <No
        icon={Gauge}
        label="Faixa"
        detail={passo >= ULTIMO && r?.faixa ? `${FAIXA_TEXTO[r.faixa]} · ${r.sim?.toFixed(3) ?? "—"}` : "similaridade"}
        estado={estado(5)}
        tone={passo >= ULTIMO && r?.faixa ? r.faixa : undefined}
      />
    </div>
  );
}
