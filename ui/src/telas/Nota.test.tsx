import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ErroApi } from "../api/cliente";
import type { Gravacao, Nota as NotaDados } from "../api/tipos";
import { ToastProvider } from "../componentes/ds";
import { AppContexto } from "../lib/app";
import { Nota } from "./Nota";

vi.mock("../api/cliente", async (original) => {
  const real = await original<typeof import("../api/cliente")>();
  return { ...real, api: { nota: vi.fn(), gravarNota: vi.fn() } };
});

const nota: NotaDados = {
  path: "Homelab/Backup.md",
  titulo: "Backup",
  conteudo: "# Backup\n\nRegra 3-2-1.\n",
  mtime: 1000,
  bytes: 30,
  secao: "Homelab",
  tipo: "nota",
  data: null,
  indexada: true,
  desatualizada: false,
  trechos: [],
  citada_por: [],
  versoes: [],
};

function Moldura({ children }: { children: ReactNode }) {
  const ctx = {
    estado: { versao: "t", desktop: false, configurado: true },
    recarregarEstado: () => {},
    setOcupado: () => {},
    abrirNovaNota: () => {},
  };
  return (
    <AppContexto.Provider value={ctx}>
      <ToastProvider>{children}</ToastProvider>
    </AppContexto.Provider>
  );
}

const abrir = () =>
  render(
    <Moldura>
      <Nota params={new URLSearchParams({ caminho: nota.path })} />
    </Moldura>,
  );

beforeEach(() => {
  localStorage.clear();
  vi.mocked(api.nota).mockResolvedValue(nota);
  // jsdom nao implementa <dialog>.showModal nem scrollIntoView.
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.removeAttribute("open");
  };
  Element.prototype.scrollIntoView ??= () => {};
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("tela de nota", () => {
  it("salva com o mtime de quando a edicao comecou", async () => {
    vi.mocked(api.gravarNota).mockResolvedValue({ path: nota.path, acao: "sobrescreveu", historico: "_historico/x.md", indice: "1 trecho(s)", nota } as Gravacao);
    abrir();
    fireEvent.click(await screen.findByRole("button", { name: /editar/i }));
    fireEvent.change(screen.getByLabelText(/conteúdo da nota/i), { target: { value: "# Backup\n\nRegra 3-2-1, testada.\n" } });
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));
    await waitFor(() =>
      expect(api.gravarNota).toHaveBeenCalledWith(nota.path, "# Backup\n\nRegra 3-2-1, testada.\n", 1000),
    );
  });

  it("conflito de edicao abre a escolha em vez de erro solto", async () => {
    vi.mocked(api.gravarNota).mockRejectedValue(new ErroApi(409, "a nota mudou no disco", "conflito"));
    abrir();
    fireEvent.click(await screen.findByRole("button", { name: /editar/i }));
    fireEvent.change(screen.getByLabelText(/conteúdo da nota/i), { target: { value: "outro texto" } });
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));
    expect(await screen.findByText("A nota mudou no disco")).toBeTruthy();
    expect(screen.getByRole("button", { name: /gravar a minha por cima/i })).toBeTruthy();
  });

  it("edicao abandonada vira rascunho oferecido na volta", async () => {
    abrir();
    fireEvent.click(await screen.findByRole("button", { name: /editar/i }));
    fireEvent.change(screen.getByLabelText(/conteúdo da nota/i), { target: { value: "meio escrito" } });
    cleanup(); // sair da tela pela barra lateral desmonta o editor

    abrir();
    expect(await screen.findByText("Há uma edição não salva desta nota")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /continuar/i }));
    expect((screen.getByLabelText(/conteúdo da nota/i) as HTMLTextAreaElement).value).toBe("meio escrito");
  });
});
