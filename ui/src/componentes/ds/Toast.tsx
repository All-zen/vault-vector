import { CircleAlert, CircleCheck, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import css from "./Toast.module.css";

export type ToastTone = "ok" | "erro" | "info";

interface Aviso {
  id: number;
  tone: ToastTone;
  conteudo: ReactNode;
}

type Avisar = (conteudo: ReactNode, tone?: ToastTone) => void;

const Contexto = createContext<Avisar>(() => {});

/** toast("Nota salva.") de qualquer lugar abaixo do ToastProvider. */
export function useToast(): Avisar {
  return useContext(Contexto);
}

const ICONES = { ok: CircleCheck, erro: CircleAlert, info: Info };

export function ToastProvider({ children }: { children: ReactNode }) {
  const [aviso, setAviso] = useState<Aviso | null>(null);

  const avisar = useCallback<Avisar>((conteudo, tone = "ok") => {
    setAviso({ id: Date.now(), tone, conteudo });
  }, []);

  useEffect(() => {
    if (!aviso) return;
    // Erro fica mais tempo: e o que a pessoa precisa ler ate o fim.
    const id = window.setTimeout(() => setAviso(null), aviso.tone === "erro" ? 7000 : 3600);
    return () => window.clearTimeout(id);
  }, [aviso]);

  const Icone = aviso ? ICONES[aviso.tone] : null;
  return (
    <Contexto.Provider value={avisar}>
      {children}
      <div className={css.regiao} aria-live="polite">
        {aviso && Icone && (
          <div key={aviso.id} role="status" className={`${css.toast} ${css[aviso.tone]}`}>
            <Icone size={16} className={css.icone} />
            <span className={css.texto}>{aviso.conteudo}</span>
            <button type="button" aria-label="Fechar" className={css.fechar} onClick={() => setAviso(null)}>
              <X size={14} />
            </button>
          </div>
        )}
      </div>
    </Contexto.Provider>
  );
}
