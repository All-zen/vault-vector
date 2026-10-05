import { hrefNota } from "./rota";

const WIKILINK = /(!?)\[\[([^\]|#]+)(#[^\]|]*)?(?:\|([^\]]+))?\]\]/g;

/**
 * Troca [[alvo|rotulo]] por link markdown que abre a nota no app.
 *
 * O react-markdown nao conhece wikilink, e o vault inteiro e costurado por
 * eles. Embed de imagem (![[x.png]]) vira so o nome: o app nao serve anexo.
 */
export function wikilinksParaLinks(texto: string): string {
  return texto.replace(WIKILINK, (_m, embed: string, alvo: string, ancora = "", rotulo?: string) => {
    const nome = (rotulo ?? alvo.split("/").pop() ?? alvo).trim();
    if (embed) return `\`${alvo.trim()}\``;
    const destino = hrefNota(alvo.trim()) + (ancora ? encodeURIComponent(ancora) : "");
    return `[${nome.replace(/[[\]]/g, "")}](${destino})`;
  });
}

/** Frontmatter YAML no topo da nota: some da leitura, continua no arquivo. */
export function semFrontmatter(texto: string): string {
  return texto.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, "");
}

/**
 * Texto corrido de um trecho, para a previa do resultado.
 *
 * O trecho indexado comeca pelo titulo e carrega a sintaxe markdown; na
 * previa de tres linhas isso so ocupa espaco.
 */
export function previa(texto: string): string {
  return texto
    .split("\n")
    .filter((l) => !/^\s*#{1,6}\s/.test(l) && !/^\s*\|?\s*:?-{3,}/.test(l) && !/^```/.test(l))
    .join(" ")
    .replace(WIKILINK, (_m, _e, alvo: string, _a, rotulo?: string) => rotulo ?? alvo.split("/").pop() ?? alvo)
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[*_`>|]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}
