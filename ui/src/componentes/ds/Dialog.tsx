import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { IconButton } from "./Button";
import css from "./Dialog.module.css";

interface Props {
  open: boolean;
  title: ReactNode;
  description?: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
  width?: number;
  children?: ReactNode;
}

/**
 * Modal sobre o <dialog> nativo: foco preso dentro, Esc fecha e o resto da
 * pagina fica inerte sem nenhuma biblioteca.
 */
export function Dialog({ open, title, description, footer, onClose, width = 460, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={css.dialog}
      style={{ width }}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      // Clique no fundo escuro (fora da caixa) fecha.
      onClick={(e) => e.target === ref.current && onClose()}
    >
      {open && (
        <div className={css.caixa}>
          <div className={css.topo}>
            <div className={css.textos}>
              <div className={css.titulo}>{title}</div>
              {description && <div className={css.descricao}>{description}</div>}
            </div>
            <IconButton icon={X} label="Fechar" size="sm" onClick={onClose} />
          </div>
          {children && <div className={css.corpo}>{children}</div>}
          {footer && <div className={css.rodape}>{footer}</div>}
        </div>
      )}
    </dialog>
  );
}
