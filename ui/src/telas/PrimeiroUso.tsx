import { ArrowRight, Check, Download, FolderOpen, FolderPlus, RefreshCw } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { api, ErroApi } from "../api/cliente";
import type { ResultadoIndexacao, VaultEncontrado } from "../api/tipos";
import { AppMark, Button, Callout, Card, Input, ProgressBar, Switch } from "../componentes/ds";
import { StatusRow } from "../componentes/vault";
import { useDados, useTarefa } from "../lib/dados";
import { ponteDesktop } from "../lib/desktop";
import { numero, plural } from "../lib/formato";
import { mesmoModelo } from "./Modelos";
import css from "./PrimeiroUso.module.css";

type Passo = "vault" | "ollama" | "indice";

function Etapas({ atual, pronto }: { atual: Passo; pronto: boolean }) {
  const passos: [Passo, string][] = [
    ["vault", "Notas"],
    ["ollama", "Modelo"],
    ["indice", "Índice"],
  ];
  const i = pronto ? passos.length : passos.findIndex(([p]) => p === atual);
  return (
    <ol className={css.etapas}>
      {passos.map(([p, rotulo], j) => (
        <li key={p} className={j < i ? css.feita : j === i ? css.atual : ""}>
          <span>{j < i ? <Check size={12} /> : j + 1}</span>
          {rotulo}
        </li>
      ))}
    </ol>
  );
}

function Opcao({ ativa, onClick, icone, titulo, detalhe }: { ativa: boolean; onClick: () => void; icone: ReactNode; titulo: ReactNode; detalhe: ReactNode }) {
  return (
    <button type="button" className={`${css.opcao} ${ativa ? css.opcaoAtiva : ""}`} onClick={onClick} aria-pressed={ativa}>
      <span className={css.opcaoIcone}>{icone}</span>
      <span className={css.opcaoTextos}>
        <span className={css.opcaoTitulo}>{titulo}</span>
        <span className={css.opcaoDetalhe}>{detalhe}</span>
      </span>
    </button>
  );
}

function PassoVault({ aoEscolher }: { aoEscolher: () => void }) {
  const { dados } = useDados(() => api.vaults(), []);
  const [escolha, setEscolha] = useState<{ caminho: string; criar: boolean } | null>(null);
  const [outra, setOutra] = useState("");
  const [modo, setModo] = useState<"achado" | "outra" | "nova">("achado");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    if (!dados || escolha) return;
    const primeiro = dados.atual ?? dados.encontrados[0]?.caminho;
    if (primeiro) setEscolha({ caminho: primeiro, criar: false });
    else {
      setModo("nova");
      setEscolha({ caminho: dados.sugestao_nova, criar: true });
    }
  }, [dados]);

  const procurar = async () => {
    const ponte = ponteDesktop();
    if (!ponte) return;
    const pasta = await ponte.escolher_pasta();
    if (pasta) {
      setOutra(pasta);
      setModo("outra");
      setEscolha({ caminho: pasta, criar: false });
    }
  };

  const confirmar = async () => {
    if (!escolha?.caminho.trim()) return;
    setSalvando(true);
    setErro("");
    try {
      await api.escolherVault(escolha.caminho.trim(), escolha.criar);
      aoEscolher();
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : String(e));
    } finally {
      setSalvando(false);
    }
  };

  if (!dados) return <ProgressBar value={null} label="Procurando vaults do Obsidian…" />;

  const encontrados: VaultEncontrado[] = dados.encontrados;
  return (
    <>
      <div className={css.titulo}>
        <h1>Onde estão as suas notas?</h1>
        <p>Uma pasta de markdown. Pode ser um vault do Obsidian, uma pasta qualquer, ou nenhuma ainda.</p>
      </div>
      <div className={css.opcoes}>
        {encontrados.map((v) => (
          <Opcao
            key={v.caminho}
            ativa={modo === "achado" && escolha?.caminho === v.caminho}
            onClick={() => {
              setModo("achado");
              setEscolha({ caminho: v.caminho, criar: false });
            }}
            icone={<FolderOpen size={18} />}
            titulo={v.nome}
            detalhe={`${v.caminho} · ${plural(v.notas, "nota", "notas")}${v.notas >= 5000 ? " ou mais" : ""}`}
          />
        ))}
        <Opcao
          ativa={modo === "outra"}
          onClick={() => {
            setModo("outra");
            setEscolha({ caminho: outra, criar: false });
            if (ponteDesktop()) void procurar();
          }}
          icone={<FolderOpen size={18} />}
          titulo="Outra pasta…"
          detalhe={outra || "uma pasta com arquivos .md, em qualquer lugar"}
        />
        <Opcao
          ativa={modo === "nova"}
          onClick={() => {
            setModo("nova");
            setEscolha({ caminho: dados.sugestao_nova, criar: true });
          }}
          icone={<FolderPlus size={18} />}
          titulo="Começar do zero"
          detalhe="crio a pasta com a estrutura que a busca aproveita: diário com data no nome, MOC por seção"
        />
      </div>

      {modo !== "achado" && escolha && (
        <Input
          label={modo === "nova" ? "Onde criar" : "Caminho da pasta"}
          mono
          value={escolha.caminho}
          onChange={(e) => {
            setEscolha({ ...escolha, caminho: e.target.value });
            if (modo === "outra") setOutra(e.target.value);
          }}
          placeholder="C:/Users/voce/Notas"
        />
      )}
      {erro && <Callout tone="baixa">{erro}</Callout>}
      <div className={css.acoes}>
        <Button variant="primary" size="lg" iconRight={ArrowRight} loading={salvando} disabled={!escolha?.caminho.trim()} onClick={confirmar}>
          {escolha?.criar ? "Criar e continuar" : "Usar esta pasta"}
        </Button>
      </div>
    </>
  );
}

function PassoOllama({ aoSeguir }: { aoSeguir: () => void }) {
  const { dados: o, recarregar, carregando } = useDados(() => api.ollama(), []);
  const pull = useTarefa<{ modelo: string }>(() => recarregar());
  const modelo = o?.modelo ?? "bge-m3";
  const instalado = o?.modelos.some((m) => m.tipo === "embedding" && mesmoModelo(modelo, m.nome));
  const t = pull.tarefa;

  return (
    <>
      <div className={css.titulo}>
        <h1>O modelo que lê as notas</h1>
        <p>
          A busca transforma cada trecho num vetor com um modelo que roda na sua máquina, pelo Ollama. Nada sai para a
          internet.
        </p>
      </div>
      {o && (
        <div>
          <StatusRow
            status={o.ok ? "ok" : "falta"}
            label={o.ok ? "Ollama respondendo" : "O Ollama não respondeu"}
            detail={o.ok ? o.url : o.erro}
            hint={
              <>
                instale em <a href="https://ollama.com/download" target="_blank" rel="noreferrer">ollama.com/download</a> e abra o
                app; depois clique em testar de novo
              </>
            }
          />
          {o.ok && (
            <StatusRow
              status={instalado ? "ok" : "falta"}
              label={instalado ? `Modelo ${modelo} baixado` : `Falta baixar o ${modelo}`}
              detail={instalado ? "multilíngue, 1024 dimensões, roda em CPU" : "cerca de 1,2 GB, uma vez só"}
              action={
                !instalado && (
                  <Button size="sm" variant="primary" icon={Download} loading={pull.rodando} onClick={() => void pull.iniciar(() => api.baixarModelo(modelo))}>
                    Baixar
                  </Button>
                )
              }
            />
          )}
        </div>
      )}
      {t?.estado === "rodando" && (
        <ProgressBar value={t.total ? t.feito / t.total : null} label={`ollama pull ${modelo} · ${t.mensagem}`} />
      )}
      {t?.estado === "erro" && <Callout tone="baixa" title="O download falhou">{t.erro}</Callout>}
      <div className={css.acoes}>
        {!(o?.ok && instalado) && (
          <Button icon={RefreshCw} loading={carregando} onClick={recarregar}>
            Testar de novo
          </Button>
        )}
        <Button variant="primary" size="lg" iconRight={ArrowRight} disabled={!(o?.ok && instalado)} onClick={aoSeguir}>
          Continuar
        </Button>
      </div>
    </>
  );
}

function PassoIndice({ aoConcluir, aoTerminar }: { aoConcluir: () => void; aoTerminar: () => void }) {
  const indexacao = useTarefa<ResultadoIndexacao>((t) => t.estado === "ok" && aoTerminar());
  const { dados: sistema, recarregar } = useDados(() => api.sistema(), []);
  const t = indexacao.tarefa;

  useEffect(() => {
    void indexacao.iniciar(() => api.indexar());
  }, []);

  return (
    <>
      <div className={css.titulo}>
        <h1>{t?.estado === "ok" ? "Pronto." : "Lendo as notas"}</h1>
        <p>
          {t?.estado === "ok"
            ? `${plural(t.resultado?.indexadas ?? 0, "nota indexada", "notas indexadas")}, ${plural(t.resultado?.trechos ?? 0, "trecho", "trechos")}. Daqui em diante, só o que mudar é reprocessado.`
            : "Cada nota é cortada nos títulos e cada trecho vira um vetor. Em CPU, centenas de notas levam alguns minutos; o que já entrou fica salvo."}
        </p>
      </div>
      {t?.estado === "rodando" && (
        <ProgressBar
          value={t.total ? t.feito / t.total : null}
          label={t.mensagem || "Conferindo o que existe"}
          detail={t.total ? `${numero(t.feito)} / ${plural(t.total, "nota", "notas")}` : ""}
        />
      )}
      {t?.estado === "erro" && (
        <Callout tone="baixa" title="A indexação parou">
          {t.erro}
        </Callout>
      )}
      {sistema?.autostart.suportado && (
        <Card padding={16}>
          <Switch
            checked={sistema.autostart.ligado}
            onChange={(ligado) => void api.autostart(ligado).then(recarregar)}
            label="Abrir com o Windows"
            description="Fica escondido na bandeja, perto do relógio, com o servidor do Claude no ar. Muda depois em Ajustes."
          />
        </Card>
      )}
      <div className={css.acoes}>
        {t?.estado === "erro" && (
          <Button icon={RefreshCw} onClick={() => void indexacao.iniciar(() => api.indexar())}>
            Tentar de novo
          </Button>
        )}
        <Button variant="primary" size="lg" iconRight={ArrowRight} disabled={t?.estado !== "ok"} onClick={aoConcluir}>
          Abrir o vault
        </Button>
      </div>
    </>
  );
}

/** Primeiro uso: vault, modelo, indice. Sem editar TOML nenhum. */
export function PrimeiroUso({ aoConcluir }: { aoConcluir: () => void }) {
  const [passo, setPasso] = useState<Passo>("vault");
  const [pronto, setPronto] = useState(false);
  return (
    <div className={css.tela}>
      <div className={css.caixa}>
        <div className={css.topo}>
          <AppMark size={36} active={passo !== "vault"} />
          <Etapas atual={passo} pronto={pronto} />
        </div>
        {passo === "vault" && <PassoVault aoEscolher={() => setPasso("ollama")} />}
        {passo === "ollama" && <PassoOllama aoSeguir={() => setPasso("indice")} />}
        {passo === "indice" && <PassoIndice aoConcluir={aoConcluir} aoTerminar={() => setPronto(true)} />}
      </div>
    </div>
  );
}
