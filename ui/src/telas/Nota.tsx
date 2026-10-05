import { ArrowLeft, Check, Copy, FileText, FolderInput, History, Link2, Pencil, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ErroApi } from "../api/cliente";
import type { Nota as NotaDados, Versao } from "../api/tipos";
import { Leitura } from "../componentes/app/Leitura";
import { PassosGravacao } from "../componentes/app/PassosGravacao";
import { Badge, Button, Callout, Card, Checkbox, Dialog, IconButton, Input, Tabs, TextArea, useToast } from "../componentes/ds";
import { MetaList } from "../componentes/vault";
import { useApp } from "../lib/app";
import { useDados } from "../lib/dados";
import { bytes, data, dataDoNome, dataHora, idade, numero, plural, tipoNota } from "../lib/formato";
import { secaoDaLinha, secoes, semFrontmatter } from "../lib/markdown";
import { apagarRascunho, guardarRascunho, lerRascunho, type Rascunho } from "../lib/rascunho";
import { hrefDe, hrefNota, navegar } from "../lib/rota";
import css from "./Nota.module.css";

/** Separa o "# Titulo" do topo, que vira o H1 grande da tela. */
function tituloECorpo(texto: string): { titulo: string | null; corpo: string } {
  const m = /^\s*#\s+(.+)\n?/.exec(texto);
  return m ? { titulo: m[1]!.trim(), corpo: texto.slice(m[0].length) } : { titulo: null, corpo: texto };
}

function LeituraDaNota({ nota, linha }: { nota: NotaDados; linha: number | null }) {
  const lista = useMemo(() => secoes(nota.conteudo), [nota.conteudo]);
  const alvo = linha ? secaoDaLinha(lista, linha) : -1;
  const destacada = useRef<HTMLElement>(null);

  useEffect(() => {
    destacada.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [alvo, nota.path]);

  return (
    <>
      {lista.map((s, i) => {
        // O titulo da nota ja esta no H1 da tela; nao repete no corpo.
        const texto = i === 0 ? tituloECorpo(semFrontmatter(s.texto)).corpo : s.texto;
        if (!texto.trim()) return null;
        return (
          <section
            key={`${s.linha}-${i}`}
            ref={i === alvo ? destacada : undefined}
            className={i === alvo ? css.destaque : css.secao}
            data-linha={s.linha}
          >
            <Leitura texto={texto} />
          </section>
        );
      })}
    </>
  );
}

function Historico({ versoes, aoRestaurar }: { versoes: Versao[]; aoRestaurar: (v: Versao) => void }) {
  if (!versoes.length) {
    return (
      <p className={css.vazio}>
        Nenhuma versão guardada ainda. Toda gravação — sua ou do Claude — copia a versão anterior para{" "}
        <code>_historico/</code> antes de escrever.
      </p>
    );
  }
  return (
    <ul className={css.versoes}>
      {versoes.map((v, i) => (
        <li key={v.versao}>
          <History size={16} className={css.iconeVersao} />
          <span className={css.versaoArquivo} title={v.versao}>
            {v.versao.split("/").pop()}
          </span>
          <span className={css.versaoQuando}>
            {i === 0 ? "mais recente · " : ""}
            {v.quando} · {bytes(v.bytes)}
          </span>
          <Button size="sm" onClick={() => aoRestaurar(v)}>
            Restaurar
          </Button>
        </li>
      ))}
    </ul>
  );
}

export function Nota({ params }: { params: URLSearchParams }) {
  const caminho = params.get("caminho") ?? "";
  const linhaPedida = Number(params.get("linha")) || null;
  const { recarregarEstado } = useApp();
  const toast = useToast();
  const { dados: nota, erro, recarregar } = useDados(() => api.nota(caminho), [caminho]);

  const [aba, setAba] = useState("nota");
  const [linha, setLinha] = useState(linhaPedida);
  const [editando, setEditando] = useState(false);
  const [texto, setTexto] = useState("");
  const [base, setBase] = useState(0); // mtime de quando a edicao comecou
  const [gravando, setGravando] = useState(false);
  const [gravado, setGravado] = useState<{ historico: string | null; indice: string } | null>(null);
  const [rascunho, setRascunho] = useState<Rascunho | null>(null);
  const [conflito, setConflito] = useState(false);
  const [mover, setMover] = useState<{ destino: string; links: boolean } | null>(null);
  const [apagar, setApagar] = useState(false);
  const [restaurar, setRestaurar] = useState<Versao | null>(null);
  const [indexando, setIndexando] = useState(false);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => setLinha(linhaPedida), [linhaPedida, caminho]);

  const comecarEdicao = useCallback(
    (n: NotaDados, de?: Rascunho) => {
      setTexto(de?.texto ?? n.conteudo);
      setBase(de?.mtime ?? n.mtime);
      setGravado(null);
      setRascunho(null);
      setEditando(true);
    },
    [],
  );

  // Ao abrir: rascunho pendente desta nota? E #/nota?editar=1 (nota nova)
  // ja entra no editor - uma vez so: depois de salvar a nota recarrega, e
  // o editar=1 continua na URL.
  const editorAutomatico = useRef<string | null>(null);
  useEffect(() => {
    if (!nota) return;
    setEditando(false);
    const r = lerRascunho(nota.path);
    if (r && r.texto !== nota.conteudo) setRascunho(r);
    else if (r) apagarRascunho(nota.path);
    if (params.get("editar") === "1" && !r && editorAutomatico.current !== nota.path) {
      editorAutomatico.current = nota.path;
      comecarEdicao(nota);
    }
  }, [nota?.path, nota?.mtime]);

  const salvar = useCallback(
    async (mtime: number) => {
      if (!nota) return;
      setGravando(true);
      setConflito(false);
      try {
        const r = await api.gravarNota(nota.path, texto, mtime);
        setGravado({ historico: r.historico, indice: r.indice });
        apagarRascunho(nota.path);
        setEditando(false);
        toast("Nota salva. A versão anterior está no histórico.");
        recarregar();
      } catch (e) {
        if (e instanceof ErroApi && e.codigo === "conflito") setConflito(true);
        else toast(e instanceof Error ? e.message : String(e), "erro");
      } finally {
        setGravando(false);
      }
    },
    [nota, texto, toast, recarregar],
  );

  useEffect(() => {
    if (!editando) return;
    const tecla = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        void salvar(base);
      }
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [editando, salvar, base]);

  const editar = (valor: string) => {
    setTexto(valor);
    if (nota) guardarRascunho(nota.path, valor, base);
  };

  const cancelar = () => {
    if (nota) apagarRascunho(nota.path);
    setEditando(false);
  };

  const executar = async (acao: () => Promise<void>) => {
    setOcupado(true);
    try {
      await acao();
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "erro");
    } finally {
      setOcupado(false);
    }
  };

  const reindexar = async () => {
    setIndexando(true);
    try {
      const t = await api.indexar();
      // Uma nota so: espera curta, sem barra de progresso.
      for (let i = 0; i < 60; i++) {
        const atual = await api.tarefa(t.id);
        if (atual.estado !== "rodando") break;
        await new Promise((r) => setTimeout(r, 500));
      }
      recarregar();
      recarregarEstado();
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "erro");
    } finally {
      setIndexando(false);
    }
  };

  if (erro) {
    return (
      <div className="tela-conteudo" style={{ maxWidth: 720 }}>
        <Callout tone="baixa" title={erro.status === 404 ? "Nota não encontrada" : "Não consegui abrir a nota"}>
          {erro.message}
        </Callout>
        <div>
          <Button icon={ArrowLeft} onClick={() => history.back()}>
            Voltar
          </Button>
        </div>
      </div>
    );
  }
  if (!nota) return null;

  const { titulo } = tituloECorpo(semFrontmatter(nota.conteudo));
  const mudou = editando && texto !== nota.conteudo;

  return (
    <div className={css.tela}>
      <header className={css.topo}>
        <FileText size={16} className={css.iconeTopo} />
        <span className={css.caminho} title={nota.path}>
          {nota.path}
        </span>
        <IconButton
          icon={Copy}
          label="Copiar caminho"
          onClick={() => {
            void navigator.clipboard.writeText(nota.path).then(() => toast("Caminho copiado.", "info"));
          }}
        />
        <IconButton icon={FolderInput} label="Mover ou renomear" onClick={() => setMover({ destino: nota.path, links: true })} disabled={editando} />
        <IconButton icon={Trash2} label="Mandar para a lixeira" onClick={() => setApagar(true)} disabled={editando} />
        {editando ? (
          <>
            <Button variant="ghost" onClick={cancelar}>
              Cancelar
            </Button>
            <Button variant="primary" icon={Check} loading={gravando} disabled={!mudou} onClick={() => void salvar(base)} title="Ctrl+S">
              Salvar
            </Button>
          </>
        ) : (
          <Button icon={Pencil} onClick={() => comecarEdicao(nota)}>
            Editar
          </Button>
        )}
      </header>

      <div className={css.corpo}>
        <div className={css.coluna}>
          <h1 className={css.titulo}>{titulo ?? nota.titulo}</h1>
          <div className={css.selos}>
            <Badge mono title={dataHora(nota.mtime)}>
              editada {data(nota.mtime)} · {idade(nota.mtime)}
            </Badge>
            {nota.data && <Badge mono>{dataDoNome(nota.data)}</Badge>}
            {nota.tipo !== "nota" && <Badge>{tipoNota(nota.tipo)}</Badge>}
            <Badge mono>{plural(nota.citada_por.length, "citação", "citações")}</Badge>
            {linhaPedida && (
              <Badge mono tone="accent">
                aberta da busca · L{linhaPedida}
              </Badge>
            )}
          </div>

          {rascunho && !editando && (
            <Callout
              tone="media"
              title="Há uma edição não salva desta nota"
              action={
                <div className={css.acoesAviso}>
                  <Button size="sm" variant="primary" onClick={() => comecarEdicao(nota, rascunho)}>
                    Continuar
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      apagarRascunho(nota.path);
                      setRascunho(null);
                    }}
                  >
                    Descartar
                  </Button>
                </div>
              }
            >
              Guardada às {new Date(rascunho.quando).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}, quando
              você saiu do editor sem salvar.
            </Callout>
          )}

          {editando ? (
            <div className={css.editor}>
              <TextArea
                aria-label="Conteúdo da nota em markdown"
                value={texto}
                onChange={(e) => editar(e.target.value)}
                spellCheck
                autoFocus
                className={css.textarea}
              />
              <div className={css.rodapeEditor}>
                <span>
                  {numero(texto.split("\n").length)} linhas · {numero(texto.length)} caracteres
                </span>
                <span>
                  <kbd>Ctrl</kbd> <kbd>S</kbd> salva · o rascunho fica guardado se você sair
                </span>
              </div>
            </div>
          ) : (
            <>
              <Tabs
                items={[
                  { id: "nota", label: "Nota" },
                  { id: "historico", label: "Histórico", count: nota.versoes.length },
                ]}
                value={aba}
                onChange={setAba}
              />
              <div className={css.conteudo}>
                {aba === "nota" ? (
                  <LeituraDaNota nota={nota} linha={linha} />
                ) : (
                  <Historico versoes={nota.versoes} aoRestaurar={setRestaurar} />
                )}
              </div>
            </>
          )}
        </div>

        <aside className={css.lateral}>
          {(editando || gravando || gravado) && (
            <Card padding={16} selected={editando}>
              <div className="rotulo" style={{ marginBottom: 6 }}>
                {gravando ? "Gravando" : gravado ? "Gravado" : "Ao salvar, vai acontecer"}
              </div>
              <PassosGravacao gravando={gravando} resultado={gravado} caminho={nota.path} />
            </Card>
          )}

          {nota.desatualizada && !editando && (
            <Callout
              tone="media"
              title="O índice está atrás desta nota"
              action={<IconButton icon={RefreshCw} label="Reindexar agora" onClick={reindexar} disabled={indexando} />}
            >
              Ela mudou fora do app depois da última indexação. A busca ainda vê a versão antiga.
            </Callout>
          )}

          <Card padding={16}>
            <div className="rotulo" style={{ marginBottom: 12 }}>
              Metadados
            </div>
            <MetaList
              items={[
                { k: "section", v: nota.secao || "(raiz)" },
                { k: "note_kind", v: nota.tipo },
                { k: "note_ts", v: nota.data ? dataDoNome(nota.data) : "—", hint: "data do evento, tirada do nome do arquivo" },
                { k: "mtime", v: dataHora(nota.mtime) },
                { k: "tamanho", v: bytes(nota.bytes) },
                { k: "n_chunks", v: nota.indexada ? nota.trechos.length : "fora do índice" },
              ]}
            />
          </Card>

          {nota.trechos.length > 0 && (
            <Card padding={16}>
              <div className="rotulo" style={{ marginBottom: 8 }}>
                Trechos indexados
              </div>
              <ul className={css.trechos}>
                {nota.trechos.map((t) => (
                  <li key={t.id}>
                    <button type="button" onClick={() => setLinha(t.start_line)} title={t.heading_path.split(" > ").join(" › ")}>
                      <span className={css.trechoNome}>{t.heading_path.split(" > ").pop() || "(início)"}</span>
                      <span className={css.trechoInfo}>
                        L{t.start_line} · {numero(t.chars)}c · {t.embed_hash?.slice(0, 6) ?? "—"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card padding={16}>
            <div className="rotulo" style={{ marginBottom: 8 }}>
              Quem aponta para cá · {nota.citada_por.length}
            </div>
            {nota.citada_por.length ? (
              <ul className={css.citacoes}>
                {nota.citada_por.map((c) => (
                  <li key={c}>
                    <a href={hrefNota(c)}>
                      <Link2 size={12} />
                      {c}
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={css.vazio}>Nenhuma nota tem wikilink para esta.</p>
            )}
          </Card>
        </aside>
      </div>

      <Dialog
        open={conflito}
        onClose={() => setConflito(false)}
        title="A nota mudou no disco"
        description="Alguém gravou nela depois que você começou a editar — o Obsidian aberto ao lado, ou o Claude pelo MCP."
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                apagarRascunho(nota.path);
                setConflito(false);
                setEditando(false);
                recarregar();
              }}
            >
              Descartar a minha
            </Button>
            <Button
              variant="primary"
              loading={gravando}
              onClick={() =>
                void executar(async () => {
                  const atual = await api.nota(nota.path);
                  await salvar(atual.mtime);
                })
              }
            >
              Gravar a minha por cima
            </Button>
          </>
        }
      >
        <p className={css.textoDialogo}>
          Gravar por cima não perde a outra versão: ela vai para o histórico antes, e dá para restaurar de lá.
        </p>
      </Dialog>

      <Dialog
        open={mover !== null}
        onClose={() => setMover(null)}
        title="Mover ou renomear"
        description="Os wikilinks que apontam para esta nota são reescritos para o caminho novo."
        footer={
          <>
            <Button variant="ghost" onClick={() => setMover(null)}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              loading={ocupado}
              disabled={!mover?.destino.trim() || mover.destino === nota.path}
              onClick={() =>
                void executar(async () => {
                  if (!mover) return;
                  const r = await api.moverNota(nota.path, mover.destino, mover.links);
                  toast(`Nota movida. ${plural(r.links_atualizados, "nota teve", "notas tiveram")} o wikilink atualizado.`);
                  setMover(null);
                  recarregarEstado();
                  navegar("nota", { caminho: r.para });
                })
              }
            >
              Mover
            </Button>
          </>
        }
      >
        {mover && (
          <div className={css.formDialogo}>
            <Input label="Caminho novo" mono value={mover.destino} onChange={(e) => setMover({ ...mover, destino: e.target.value })} />
            <Checkbox
              checked={mover.links}
              onChange={(links) => setMover({ ...mover, links })}
              label={`Atualizar wikilinks (${plural(nota.citada_por.length, "nota cita", "notas citam")} esta)`}
            />
          </div>
        )}
      </Dialog>

      <Dialog
        open={apagar}
        onClose={() => setApagar(false)}
        title="Mandar para a lixeira?"
        description="O arquivo vai para _historico/lixeira/ e sai do índice. Não é apagado de verdade: dá para trazer de volta."
        footer={
          <>
            <Button variant="ghost" onClick={() => setApagar(false)}>
              Cancelar
            </Button>
            <Button
              variant="danger"
              icon={Trash2}
              loading={ocupado}
              onClick={() =>
                void executar(async () => {
                  const r = await api.apagarNota(nota.path);
                  toast(`Na lixeira: ${r.lixeira}`);
                  setApagar(false);
                  recarregarEstado();
                  navegar("buscar");
                })
              }
            >
              Mandar para a lixeira
            </Button>
          </>
        }
      >
        {nota.citada_por.length > 0 && (
          <Callout tone="media" title={`${plural(nota.citada_por.length, "nota cita", "notas citam")} esta`}>
            Os wikilinks delas ficam quebrados.
          </Callout>
        )}
      </Dialog>

      <Dialog
        open={restaurar !== null}
        onClose={() => setRestaurar(null)}
        title="Restaurar esta versão?"
        description={restaurar ? `A nota volta a ser como estava em ${restaurar.quando}.` : undefined}
        footer={
          <>
            <Button variant="ghost" onClick={() => setRestaurar(null)}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              loading={ocupado}
              onClick={() =>
                void executar(async () => {
                  if (!restaurar) return;
                  const r = await api.restaurarNota(nota.path, restaurar.versao, nota.mtime);
                  setGravado({ historico: r.historico, indice: r.indice });
                  toast("Versão restaurada. A que estava antes foi para o histórico.");
                  setRestaurar(null);
                  setAba("nota");
                  recarregar();
                })
              }
            >
              Restaurar
            </Button>
          </>
        }
      >
        <p className={css.textoDialogo}>A versão atual vai para o histórico antes, então restaurar também tem volta.</p>
      </Dialog>

      <a className="sr-only" href={hrefDe("buscar")}>
        Voltar para a busca
      </a>
    </div>
  );
}
