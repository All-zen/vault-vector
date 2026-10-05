// Ponte com o app de desktop. Dentro da janela do pywebview existe
// window.pywebview.api, com o que so o processo nativo sabe fazer - abrir
// o seletor de pasta do sistema, por exemplo. No navegador ela nao existe,
// e a interface cai para digitar o caminho.

interface PonteDesktop {
  escolher_pasta(): Promise<string | null>;
}

declare global {
  interface Window {
    pywebview?: { api: PonteDesktop };
  }
}

export function ponteDesktop(): PonteDesktop | null {
  return window.pywebview?.api ?? null;
}
