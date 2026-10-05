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

export interface SecaoMd {
  /** Linha (base 1) onde a secao comeca no arquivo, como o start_line do indice. */
  linha: number;
  texto: string;
}

/**
 * Corta a nota nos titulos, guardando a linha de cada pedaco.
 *
 * E o que deixa a tela destacar a secao que a busca achou: o indice sabe
 * a linha do trecho, e a linha cai dentro de exatamente uma secao. Titulo
 * dentro de bloco de codigo nao conta - "# comentario" em shell nao e secao.
 */
export function secoes(texto: string): SecaoMd[] {
  const linhas = texto.split("\n");
  const saida: SecaoMd[] = [];
  let atual: string[] = [];
  let inicio = 1;
  let cerca = false;
  linhas.forEach((l, i) => {
    if (/^\s*(```|~~~)/.test(l)) cerca = !cerca;
    if (!cerca && /^#{1,6}\s/.test(l) && atual.some((x) => x.trim())) {
      saida.push({ linha: inicio, texto: atual.join("\n") });
      atual = [];
      inicio = i + 1;
    }
    atual.push(l);
  });
  if (atual.some((x) => x.trim())) saida.push({ linha: inicio, texto: atual.join("\n") });
  return saida;
}

/** A secao que contem a linha pedida. */
export function secaoDaLinha(lista: SecaoMd[], linha: number): number {
  let achada = -1;
  lista.forEach((s, i) => {
    if (s.linha <= linha) achada = i;
  });
  return achada;
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
    // Pipe so some em linha de tabela: no meio do texto ele pode ser
    // conteudo ("o || true no fim da linha").
    .map((l) => (/^\s*\|/.test(l) ? l.replace(/\|/g, " ") : l))
    .join(" ")
    .replace(WIKILINK, (_m, _e, alvo: string, _a, rotulo?: string) => rotulo ?? alvo.split("/").pop() ?? alvo)
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/(^|\s)[-*>]\s/g, "$1")
    .replace(/[*_`]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}
