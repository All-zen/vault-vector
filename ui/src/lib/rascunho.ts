// Rascunho da edicao, guardado no navegador a cada tecla.
//
// Trocar de tela pela barra lateral desmonta o editor sem perguntar nada.
// Em vez de prender a pessoa com "tem certeza?", o texto fica guardado e
// volta na proxima vez que ela abrir a mesma nota.
//
// localStorage pode estar cheio ou bloqueado: tudo aqui falha calado, e o
// pior caso e o comportamento de antes, sem rascunho.

export interface Rascunho {
  texto: string;
  /** mtime da nota quando a edicao comecou: e o que a gravacao vai conferir. */
  mtime: number;
  quando: number;
}

const chave = (caminho: string) => `vv-rascunho:${caminho}`;

export function lerRascunho(caminho: string): Rascunho | null {
  try {
    const bruto = localStorage.getItem(chave(caminho));
    return bruto ? (JSON.parse(bruto) as Rascunho) : null;
  } catch {
    return null;
  }
}

export function guardarRascunho(caminho: string, texto: string, mtime: number): void {
  try {
    localStorage.setItem(chave(caminho), JSON.stringify({ texto, mtime, quando: Date.now() }));
  } catch {
    // sem espaco ou sem permissao: segue sem rascunho
  }
}

export function apagarRascunho(caminho: string): void {
  try {
    localStorage.removeItem(chave(caminho));
  } catch {
    // idem
  }
}
