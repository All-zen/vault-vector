import { useCallback, useEffect, useState } from "react";

// Roteamento por hash: '#/nota?caminho=X'. Nao precisa de rota no servidor
// (o Python so serve '/'), e o historico do navegador funciona igual -
// voltar da nota para a busca e o botao de voltar mesmo.

export type Tela =
  | "buscar"
  | "nota"
  | "saude"
  | "modelos"
  | "ajustes"
  | "calibrar"
  | "conectar";

const TELAS: Tela[] = ["buscar", "nota", "saude", "modelos", "ajustes", "calibrar", "conectar"];

export interface Rota {
  tela: Tela;
  params: URLSearchParams;
}

export function lerRota(hash: string): Rota {
  const [caminho = "", busca = ""] = hash.replace(/^#\/?/, "").split("?");
  const tela = TELAS.includes(caminho as Tela) ? (caminho as Tela) : "buscar";
  return { tela, params: new URLSearchParams(busca) };
}

export function hrefDe(tela: Tela, params: Record<string, string | undefined> = {}): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
  const s = q.toString();
  return `#/${tela}${s ? `?${s}` : ""}`;
}

export function hrefNota(caminho: string, linha?: number): string {
  return hrefDe("nota", { caminho, linha: linha ? String(linha) : undefined });
}

export function navegar(tela: Tela, params: Record<string, string | undefined> = {}): void {
  window.location.hash = hrefDe(tela, params);
}

export function useRota(): Rota {
  const [rota, setRota] = useState(() => lerRota(window.location.hash));
  const atualizar = useCallback(() => setRota(lerRota(window.location.hash)), []);
  useEffect(() => {
    window.addEventListener("hashchange", atualizar);
    return () => window.removeEventListener("hashchange", atualizar);
  }, [atualizar]);
  return rota;
}
