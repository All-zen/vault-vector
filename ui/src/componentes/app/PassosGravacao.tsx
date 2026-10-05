import { Check, History, RefreshCw, Save, ShieldCheck, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import css from "./PassosGravacao.module.css";

interface Resultado {
  historico: string | null;
  indice: string;
}

interface Props {
  /** null antes de salvar: a lista explica o que vai acontecer. */
  gravando: boolean;
  resultado: Resultado | null;
  caminho: string;
}

/**
 * As garantias do writer.py, na ordem em que acontecem a cada gravacao.
 *
 * Antes de salvar, a lista diz o que vai acontecer; durante, acende passo
 * a passo; depois, mostra o que de fato aconteceu - o arquivo exato no
 * historico e quantos trechos foram reindexados.
 */
export function PassosGravacao({ gravando, resultado, caminho }: Props) {
  const [passo, setPasso] = useState(-1);

  useEffect(() => {
    if (!gravando) return;
    setPasso(0);
    const id = window.setInterval(() => setPasso((p) => Math.min(p + 1, 2)), 220);
    return () => window.clearInterval(id);
  }, [gravando]);

  useEffect(() => {
    if (resultado) setPasso(4);
  }, [resultado]);

  const nome = caminho.split("/").pop();
  const passos: [LucideIcon, string, string][] = [
    [ShieldCheck, "Confere se ninguém editou", "o mtime precisa ser o mesmo de quando você abriu"],
    [History, "Copia a versão atual", resultado?.historico ?? (resultado ? "nota nova, nada a copiar" : "para _historico/, antes de mexer")],
    [Save, "Grava a nota", nome ?? caminho],
    [RefreshCw, "Reindexa só esta nota", resultado?.indice ?? "trecho com texto igual reaproveita o vetor"],
  ];

  return (
    <ol className={css.passos}>
      {passos.map(([Icone, rotulo, detalhe], i) => {
        const estado = passo > i ? "feito" : passo === i ? "ativo" : "parado";
        return (
          <li key={rotulo} className={css[estado]}>
            <span className={css.bolinha}>{estado === "feito" ? <Check size={12} /> : <Icone size={12} />}</span>
            <span className={css.textos}>
              <span className={css.rotulo}>{rotulo}</span>
              <span className={css.detalhe}>{detalhe}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
