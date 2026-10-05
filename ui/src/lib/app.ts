import { createContext, useContext } from "react";
import type { Estado } from "../api/tipos";

export interface ContextoApp {
  estado: Estado;
  /** Rele /api/estado: depois de indexar, trocar modelo, criar nota. */
  recarregarEstado: () => void;
  /** Liga a animacao da marca na barra lateral enquanto algo trabalha. */
  setOcupado: (ocupado: boolean) => void;
  abrirNovaNota: (secao?: string) => void;
}

export const AppContexto = createContext<ContextoApp | null>(null);

export function useApp(): ContextoApp {
  const ctx = useContext(AppContexto);
  if (!ctx) throw new Error("useApp fora do AppContexto");
  return ctx;
}
