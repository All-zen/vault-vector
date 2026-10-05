import { useCallback, useEffect, useRef, useState } from "react";
import { api, ErroApi } from "../api/cliente";
import type { Tarefa } from "../api/tipos";

export interface Dados<T> {
  dados: T | null;
  erro: ErroApi | null;
  carregando: boolean;
  recarregar: () => void;
}

/** Carrega uma vez e de novo quando as dependencias mudam. */
export function useDados<T>(buscar: () => Promise<T>, deps: unknown[]): Dados<T> {
  const [dados, setDados] = useState<T | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [rodada, setRodada] = useState(0);

  useEffect(() => {
    let vivo = true;
    setCarregando(true);
    buscar()
      .then((d) => {
        if (!vivo) return;
        setDados(d);
        setErro(null);
      })
      .catch((e) => vivo && setErro(e instanceof ErroApi ? e : new ErroApi(0, String(e))))
      .finally(() => vivo && setCarregando(false));
    return () => {
      vivo = false;
    };
    // buscar muda a cada render; quem decide quando recarregar sao as deps.
  }, [...deps, rodada]);

  const recarregar = useCallback(() => setRodada((n) => n + 1), []);
  return { dados, erro, carregando, recarregar };
}

/**
 * Dispara uma tarefa do servidor e acompanha ate terminar.
 *
 * O servidor devolve o id na hora; daqui em diante e consulta a cada meio
 * segundo. Sair da tela para a consulta, mas nao a tarefa: ela segue
 * rodando no servidor, e voltar a disparar devolve a mesma.
 */
export function useTarefa<R, P = unknown>(aoTerminar?: (t: Tarefa<R, P>) => void) {
  const [tarefa, setTarefa] = useState<Tarefa<R, P> | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const callback = useRef(aoTerminar);
  useEffect(() => {
    callback.current = aoTerminar;
  });

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const acompanhar = useCallback((id: string) => {
    const passo = async () => {
      try {
        const t = await api.tarefa<R, P>(id);
        setTarefa(t);
        if (t.estado === "rodando") {
          timer.current = window.setTimeout(passo, 500);
        } else {
          callback.current?.(t);
        }
      } catch (e) {
        setErro(e instanceof ErroApi ? e : new ErroApi(0, String(e)));
      }
    };
    void passo();
  }, []);

  const iniciar = useCallback(
    async (disparar: () => Promise<Tarefa<R, P>>) => {
      setErro(null);
      try {
        const t = await disparar();
        setTarefa(t);
        acompanhar(t.id);
      } catch (e) {
        setErro(e instanceof ErroApi ? e : new ErroApi(0, String(e)));
      }
    },
    [acompanhar],
  );

  const rodando = tarefa?.estado === "rodando";
  return { tarefa, erro, rodando, iniciar, limpar: () => setTarefa(null) };
}
