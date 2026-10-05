import { Activity, Cpu, FilePlus, FileText, Folder, Plug, Search, Settings2, SlidersHorizontal } from "lucide-react";
import { Fragment } from "react";
import type { Estado } from "../../api/tipos";
import { hrefDe, type Rota, type Tela } from "../../lib/rota";
import { AppMark, Button, NavItem } from "../ds";
import css from "./BarraLateral.module.css";

const ITENS: [Tela, typeof Search, string][] = [
  ["buscar", Search, "Buscar"],
  ["saude", Activity, "Saúde"],
  ["modelos", Cpu, "Modelos · Ollama"],
  ["ajustes", Settings2, "Ajustes"],
  ["calibrar", SlidersHorizontal, "Calibrar"],
  ["conectar", Plug, "Conectar ao Claude"],
];

interface Props {
  estado: Estado;
  rota: Rota;
  ocupado: boolean;
  aoNovaNota: () => void;
}

export function BarraLateral({ estado, rota, ocupado, aoNovaNota }: Props) {
  const secaoAtiva = rota.tela === "buscar" ? rota.params.get("secao") : null;
  const notaAberta = rota.tela === "nota" ? rota.params.get("caminho") : null;
  const ollamaOk = estado.ollama?.ok ?? false;

  return (
    <aside className={css.barra}>
      <a className={css.marca} href={hrefDe("buscar")} aria-label="vault-vector, ir para a busca">
        <AppMark size={28} active={ocupado} />
        <span className={css.nome}>
          vault<span className={css.hifen}>-</span>vector
        </span>
      </a>

      <Button variant="secondary" icon={FilePlus} full onClick={aoNovaNota} title="Nova nota (Ctrl+N)">
        Nova nota
      </Button>

      <nav className={css.lista} aria-label="Telas">
        {ITENS.map(([tela, Icone, rotulo]) => (
          <Fragment key={tela}>
            <NavItem
              icon={Icone}
              label={rotulo}
              href={hrefDe(tela)}
              active={rota.tela === tela && !(tela === "buscar" && secaoAtiva)}
            />
            {tela === "buscar" && notaAberta && (
              <div className={css.aninhado}>
                <NavItem
                  icon={FileText}
                  label={notaAberta.split("/").pop()?.replace(/\.md$/, "")}
                  href={window.location.hash}
                  active
                  title={notaAberta}
                />
              </div>
            )}
          </Fragment>
        ))}
      </nav>

      {!!estado.secoes?.length && (
        <nav className={css.lista} aria-label="Seções do vault">
          <div className={`rotulo ${css.titulo}`}>Seções</div>
          {estado.secoes.map((s) => (
            <NavItem
              key={s.nome}
              icon={Folder}
              label={s.nome}
              count={s.notas}
              href={hrefDe("buscar", { secao: s.nome })}
              active={secaoAtiva === s.nome}
            />
          ))}
        </nav>
      )}

      <div className={css.rodape}>
        <a className={css.servico} href={hrefDe("modelos")} title={ollamaOk ? `respondendo em ${estado.ollama?.ms} ms` : "Ollama não respondeu"}>
          <span className={`${css.ponto} ${ollamaOk ? css.pontoOk : css.pontoFora}`} />
          Ollama · {estado.modelo}
        </a>
        <span className={css.vault} title={estado.vault}>
          {estado.vault}
        </span>
      </div>
    </aside>
  );
}
