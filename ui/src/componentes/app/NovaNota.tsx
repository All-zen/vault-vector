import { useEffect, useState } from "react";
import { api, ErroApi } from "../../api/cliente";
import type { Secao } from "../../api/tipos";
import { navegar } from "../../lib/rota";
import { Button, Dialog, Input, Select, useToast } from "../ds";

interface Props {
  aberto: boolean;
  secaoInicial?: string;
  secoes: Secao[];
  aoFechar: () => void;
  aoCriar: () => void;
}

/** "Projetos/Ideia nova" -> "Projetos/Ideia-nova.md": o nome vira caminho. */
export function caminhoDaNota(secao: string, titulo: string): string {
  const nome = titulo
    .trim()
    .replace(/[\\/:*?"<>|#^[\]]+/g, "")
    .replace(/\s+/g, "-");
  return `${secao ? `${secao}/` : ""}${nome}.md`;
}

function hoje(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function NovaNota({ aberto, secaoInicial, secoes, aoFechar, aoCriar }: Props) {
  const toast = useToast();
  const [secao, setSecao] = useState(secaoInicial ?? "");
  const [titulo, setTitulo] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    if (!aberto) return;
    setSecao(secaoInicial ?? "");
    setTitulo("");
    setErro("");
  }, [aberto, secaoInicial]);

  // Diario segue a convencao que o ranking entende: data no nome do arquivo.
  const diario = /diario|daily/i.test(secao);
  const tituloFinal = diario && titulo && !/^\d{4}-\d{2}-\d{2}/.test(titulo) ? `${hoje()} ${titulo}` : titulo;
  const caminho = titulo.trim() ? caminhoDaNota(secao, tituloFinal) : "";

  const criar = async () => {
    if (!caminho) return;
    setSalvando(true);
    setErro("");
    try {
      const r = await api.gravarNota(caminho, `# ${tituloFinal.trim()}\n\n`, null, true);
      toast(`Nota criada: ${r.path}`);
      aoCriar();
      aoFechar();
      navegar("nota", { caminho: r.path, editar: "1" });
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : String(e));
    } finally {
      setSalvando(false);
    }
  };

  return (
    <Dialog
      open={aberto}
      onClose={aoFechar}
      title="Nova nota"
      description="Abre direto no editor. O índice é atualizado assim que você salvar."
      footer={
        <>
          <Button variant="ghost" onClick={aoFechar}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={criar} disabled={!caminho} loading={salvando}>
            Criar
          </Button>
        </>
      }
    >
      <form
        style={{ display: "flex", flexDirection: "column", gap: 14 }}
        onSubmit={(e) => {
          e.preventDefault();
          void criar();
        }}
      >
        <Select
          label="Seção"
          value={secao}
          onChange={setSecao}
          options={[{ value: "", label: "(raiz do vault)" }, ...secoes.map((s) => s.nome)]}
        />
        <Input
          label="Título"
          autoFocus
          value={titulo}
          onChange={(e) => setTitulo(e.target.value)}
          placeholder={diario ? "o que aconteceu" : "Decisão sobre o backup"}
          invalid={!!erro}
          hint={erro || (caminho ? <code>{caminho}</code> : diario ? "a data de hoje entra no nome" : " ")}
        />
      </form>
    </Dialog>
  );
}
