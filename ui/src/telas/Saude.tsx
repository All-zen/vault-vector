import { RefreshCw, RotateCcw } from "lucide-react";
import { useState } from "react";
import { api } from "../api/cliente";
import type { ResultadoIndexacao } from "../api/tipos";
import { Button, Callout, Card, CardHeader, Dialog, ProgressBar, useToast } from "../componentes/ds";
import { CommandBlock, IndexGrid, StatusRow } from "../componentes/vault";
import { useApp } from "../lib/app";
import { useDados, useTarefa } from "../lib/dados";
import { numero, plural } from "../lib/formato";
import css from "./Saude.module.css";

function Numero({ valor, rotulo }: { valor: string; rotulo: string }) {
  return (
    <div className={css.numero}>
      <span className={css.valor}>{valor}</span>
      <span className={css.rotulo}>{rotulo}</span>
    </div>
  );
}

export function Saude() {
  const { recarregarEstado, setOcupado } = useApp();
  const toast = useToast();
  const { dados, erro, carregando, recarregar } = useDados(() => api.saude(), []);
  const [confirmarTudo, setConfirmarTudo] = useState(false);

  const indexacao = useTarefa<ResultadoIndexacao>((t) => {
    setOcupado(false);
    if (t.estado === "ok" && t.resultado) {
      toast(
        t.resultado.erros.length
          ? `Indexado com ${plural(t.resultado.erros.length, "erro", "erros")}. O que entrou está salvo.`
          : `${plural(t.resultado.indexadas, "nota reindexada", "notas reindexadas")}. Trecho que não mudou reaproveitou o vetor.`,
        t.resultado.erros.length ? "erro" : "ok",
      );
    } else if (t.estado === "erro") {
      toast(`A indexação falhou: ${t.erro}`, "erro");
    }
    recarregar();
    recarregarEstado();
  });

  const indexar = (forcar: boolean) => {
    setConfirmarTudo(false);
    setOcupado(true);
    void indexacao.iniciar(() => api.indexar(forcar));
  };

  const t = indexacao.tarefa;
  const progresso = t && t.total ? t.feito / t.total : t?.estado === "rodando" ? null : 0;
  const pendentes = dados?.indice.pending ?? 0;

  return (
    <div className="tela-conteudo" style={{ maxWidth: 860 }}>
      <div className={css.cabecalho}>
        <div className="tela-titulo">
          <h1>Saúde</h1>
          <p>Tudo o que a busca precisa para funcionar, e o que fazer quando algo falta.</p>
        </div>
        <div className={css.acoes}>
          <Button icon={RotateCcw} variant="ghost" disabled={indexacao.rodando} onClick={() => setConfirmarTudo(true)}>
            Reindexar tudo
          </Button>
          <Button
            icon={RefreshCw}
            variant="primary"
            loading={indexacao.rodando}
            disabled={!dados || pendentes === 0}
            onClick={() => indexar(false)}
          >
            {pendentes ? `Indexar ${plural(pendentes, "pendente", "pendentes")}` : "Índice em dia"}
          </Button>
        </div>
      </div>

      {erro && (
        <Callout tone="baixa" title="Não consegui rodar o diagnóstico">
          {erro.message}
        </Callout>
      )}
      {indexacao.erro && (
        <Callout tone="baixa" title="A indexação não começou">
          {indexacao.erro.message}
        </Callout>
      )}

      {dados && (
        <>
          <Card className={css.numeros}>
            <Numero valor={numero(dados.indice.files)} rotulo="notas" />
            <Numero valor={numero(dados.indice.chunks)} rotulo="trechos" />
            <Numero valor={`${dados.indice.db_mb.toLocaleString("pt-BR")} MB`} rotulo="índice SQLite" />
            <Numero valor={numero(pendentes)} rotulo="pendentes" />
          </Card>

          <Card>
            <div className={css.mapa}>
              <CardHeader
                title="Mapa do índice"
                subtitle="Cada célula é uma nota, na ordem em que a indexação percorre o vault."
              />
              <IndexGrid total={dados.mapa.total} pending={dados.mapa.pendentes} progress={progresso ?? 0} />
              <div className={css.legenda}>
                <span>
                  <i style={{ background: "var(--vv-200)" }} /> indexada
                </span>
                <span>
                  <i style={{ background: "var(--media-fg)" }} /> mudou desde a última indexação
                </span>
                <span>
                  <i style={{ background: "var(--vv-400)" }} /> reembeddada agora
                </span>
              </div>
              {t && t.estado === "rodando" && (
                <ProgressBar
                  value={progresso}
                  label={t.mensagem || "Conferindo o que mudou"}
                  detail={t.total ? `${numero(t.feito)} / ${plural(t.total, "nota", "notas")}` : `${t.segundos}s`}
                />
              )}
              {dados.mapa.removidas > 0 && (
                <span className={css.removidas}>
                  {plural(dados.mapa.removidas, "nota apagada do disco ainda está", "notas apagadas do disco ainda estão")} no
                  índice e sai na próxima indexação.
                </span>
              )}
            </div>
          </Card>

          {dados.grupos.map((g, gi) => (
            <section key={g.id}>
              <div className="rotulo" style={{ marginBottom: 4 }}>
                {g.nome}
              </div>
              {g.itens.map((item, i) => (
                <StatusRow
                  key={item.rotulo}
                  index={gi * 3 + i}
                  status={item.status}
                  label={item.rotulo}
                  detail={item.detalhe}
                  hint={item.dica}
                />
              ))}
            </section>
          ))}

          <CommandBlock command="vault-vector doctor" comment="a mesma checagem no terminal" />
        </>
      )}

      {carregando && !dados && <ProgressBar value={null} label="Checando Ollama, índice e escrita…" />}

      <Dialog
        open={confirmarTudo}
        onClose={() => setConfirmarTudo(false)}
        title="Reindexar o vault inteiro?"
        description="Refaz o embedding de todas as notas, do zero. Só vale depois de trocar o modelo ou se o índice parecer errado."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmarTudo(false)}>
              Cancelar
            </Button>
            <Button variant="primary" onClick={() => indexar(true)}>
              Reindexar tudo
            </Button>
          </>
        }
      >
        <p className={css.texto}>
          Em CPU, cada mil trechos levam alguns minutos. A busca continua funcionando durante a indexação, com o índice
          antigo.
        </p>
      </Dialog>
    </div>
  );
}
