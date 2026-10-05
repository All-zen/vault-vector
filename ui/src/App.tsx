import { Component, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api/cliente";
import { BarraLateral } from "./componentes/app/BarraLateral";
import { NovaNota } from "./componentes/app/NovaNota";
import { AppMark, Button, Callout, ToastProvider } from "./componentes/ds";
import { AppContexto, type ContextoApp } from "./lib/app";
import { useDados } from "./lib/dados";
import { navegar, useRota, type Rota } from "./lib/rota";
import { Ajustes } from "./telas/Ajustes";
import { Busca } from "./telas/Busca";
import { Calibrar } from "./telas/Calibrar";
import { Conectar } from "./telas/Conectar";
import { Modelos } from "./telas/Modelos";
import { Nota } from "./telas/Nota";
import { PrimeiroUso } from "./telas/PrimeiroUso";
import { Saude } from "./telas/Saude";
import css from "./App.module.css";

/** Uma tela por rota. Sem default: rota nova sem tela nao compila. */
function Telas({ rota }: { rota: Rota }) {
  switch (rota.tela) {
    case "buscar":
      return <Busca params={rota.params} />;
    case "nota":
      return <Nota params={rota.params} />;
    case "saude":
      return <Saude />;
    case "modelos":
      return <Modelos />;
    case "ajustes":
      return <Ajustes />;
    case "calibrar":
      return <Calibrar />;
    case "conectar":
      return <Conectar />;
  }
}

function Carregando() {
  return (
    <div className={css.centro}>
      <AppMark size={56} active />
    </div>
  );
}

function Shell() {
  const rota = useRota();
  const { dados: estado, erro, recarregar } = useDados(() => api.estado(), []);
  const [ocupado, setOcupado] = useState(false);
  const [novaNota, setNovaNota] = useState<{ secao?: string } | null>(null);
  // Decidido uma vez, na primeira carga: depois de escolher o vault o
  // estado ja diz "configurado", mas o passo a passo ainda tem dois passos.
  const [boasVindas, setBoasVindas] = useState<boolean | null>(null);
  useEffect(() => {
    if (estado && boasVindas === null) setBoasVindas(!estado.configurado || !estado.ultima_indexacao);
  }, [estado, boasVindas]);

  const abrirNovaNota = useCallback((secao?: string) => setNovaNota({ secao }), []);

  // Atalhos do app inteiro. Ctrl+K e o atalho de busca que todo mundo ja
  // tenta primeiro; Ctrl+N cria nota de qualquer tela.
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      if (e.key === "k") {
        e.preventDefault();
        if (rota.tela !== "buscar") navegar("buscar");
        window.setTimeout(() => document.querySelector<HTMLInputElement>("#busca")?.focus(), 0);
      } else if (e.key === "n") {
        e.preventDefault();
        abrirNovaNota(rota.params.get("secao") ?? undefined);
      }
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [rota, abrirNovaNota]);

  const contexto = useMemo<ContextoApp | null>(
    () => (estado ? { estado, recarregarEstado: recarregar, setOcupado, abrirNovaNota } : null),
    [estado, recarregar, abrirNovaNota],
  );

  if (erro && !estado) {
    return (
      <div className={css.centro}>
        <div className={css.falhou}>
          <Callout tone="baixa" title="Não consegui falar com o vault-vector">
            {erro.message}
          </Callout>
          <Button onClick={recarregar}>
            Tentar de novo
          </Button>
        </div>
      </div>
    );
  }
  if (!estado || !contexto) return <Carregando />;
  // Na primeira carga o efeito acima ainda nao rodou: decidir aqui mesmo,
  // senao a casca do app pisca e a busca pede notas de um vault que nao ha.
  if (boasVindas ?? (!estado.configurado || !estado.ultima_indexacao)) {
    return (
      <PrimeiroUso
        aoConcluir={() => {
          setBoasVindas(false);
          recarregar();
        }}
      />
    );
  }

  return (
    <AppContexto.Provider value={contexto}>
      <div className={css.app}>
        <BarraLateral estado={estado} rota={rota} ocupado={ocupado} aoNovaNota={() => abrirNovaNota()} />
        <main className={css.principal}>
          <div key={rota.tela} className={css.tela}>
            <Telas rota={rota} />
          </div>
        </main>
      </div>
      <NovaNota
        aberto={novaNota !== null}
        secaoInicial={novaNota?.secao}
        secoes={estado.secoes ?? []}
        aoFechar={() => setNovaNota(null)}
        aoCriar={recarregar}
      />
    </AppContexto.Provider>
  );
}

/** Erro de render nao pode deixar a janela em branco sem explicacao. */
class Protecao extends Component<{ children: ReactNode }, { erro: Error | null }> {
  state = { erro: null as Error | null };

  static getDerivedStateFromError(erro: Error) {
    return { erro };
  }

  render() {
    if (!this.state.erro) return this.props.children;
    return (
      <div className={css.centro}>
        <div className={css.falhou}>
          <Callout tone="baixa" title="Algo quebrou nesta tela">
            <code>{this.state.erro.message}</code>
          </Callout>
          <Button
            onClick={() => {
              this.setState({ erro: null });
              navegar("buscar");
            }}
          >
            Voltar para a busca
          </Button>
        </div>
      </div>
    );
  }
}

export function App() {
  return (
    <Protecao>
      <ToastProvider>
        <Shell />
      </ToastProvider>
    </Protecao>
  );
}
