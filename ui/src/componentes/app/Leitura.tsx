import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { wikilinksParaLinks } from "../../lib/markdown";
import css from "./Leitura.module.css";

const componentes: Components = {
  a({ href = "", children, node: _node, ...resto }) {
    // Link de outra nota fica no app; link para fora abre no navegador do
    // sistema (a janela do app nao e um navegador).
    const externo = /^https?:/i.test(href);
    return (
      <a href={href} {...resto} {...(externo ? { target: "_blank", rel: "noreferrer" } : {})}>
        {children}
      </a>
    );
  },
  table({ children, node: _node, ...resto }) {
    // Tabela larga rola sozinha em vez de empurrar a coluna de leitura.
    return (
      <div className={css.tabela}>
        <table {...resto}>{children}</table>
      </div>
    );
  },
};

/** Markdown da nota, com wikilink virando link para a nota no app. */
export function Leitura({ texto }: { texto: string }) {
  return (
    <div className={css.leitura}>
      <Markdown remarkPlugins={[remarkGfm]} components={componentes}>
        {wikilinksParaLinks(texto)}
      </Markdown>
    </div>
  );
}
