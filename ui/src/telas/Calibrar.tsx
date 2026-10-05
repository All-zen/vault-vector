import { Play, RotateCcw, Save, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/cliente";
import type { PontoCalibracao, ResultadoCalibracao } from "../api/tipos";
import { Button, Callout, Card, CardHeader, ProgressBar, useToast } from "../componentes/ds";
import { CommandBlock, ConfidenceBadge, SimilarityPlot, type Ponto } from "../componentes/vault";
import { useApp } from "../lib/app";
import { useDados, useTarefa } from "../lib/dados";
import css from "./Calibrar.module.css";

type Contagem = [alta: number, media: number, baixa: number];

export function contar(valores: number[], duvidoso: number, confiavel: number): Contagem {
  const c: Contagem = [0, 0, 0];
  for (const v of valores) c[v >= confiavel ? 0 : v >= duvidoso ? 1 : 2]++;
  return c;
}

/**
 * A faixa media mais estreita que deixa as duas pontas limpas: nenhuma
 * pergunta de fora em alta, nenhuma de dentro em baixa.
 *
 * Esse par sempre existe - no limite, uma faixa media que cobre tudo. O que
 * a medicao decide e a largura: quando as populacoes se sobrepoem, a faixa
 * media precisa cobrir a sobreposicao inteira, e cada pergunta que cai ali
 * sai com ressalva. E onde o juiz local ajuda.
 */
export function sugerirCortes(
  dentro: number[],
  fora: number[],
): { duvidoso: number; confiavel: number; sobrepoe: boolean } | null {
  if (!dentro.length || !fora.length) return null;
  const tetoFora = Math.max(...fora);
  const pisoDentro = Math.min(...dentro);
  const confiavel = Math.ceil((tetoFora + 0.005) * 100) / 100;
  // Sem sobreposicao, o piso de dentro fica acima do corte de cima; a linha
  // de baixo encosta logo abaixo dela.
  const duvidoso = Math.min(Math.floor((pisoDentro - 0.005) * 100) / 100, Math.round((confiavel - 0.02) * 100) / 100);
  return { duvidoso, confiavel, sobrepoe: pisoDentro <= tetoFora };
}

function Num({ v, critico }: { v: number; critico?: boolean }) {
  const [rodada, setRodada] = useState(0);
  useEffect(() => setRodada((n) => n + 1), [v]);
  return (
    <span key={rodada} className={`${css.num} ${critico ? (v ? css.ruim : css.bom) : ""}`}>
      {v}
    </span>
  );
}

export function Calibrar() {
  const { recarregarEstado } = useApp();
  const toast = useToast();
  const { dados: config, recarregar } = useDados(() => api.config(), []);
  const [lo, setLo] = useState(0.43);
  const [hi, setHi] = useState(0.6);
  const medicao = useTarefa<ResultadoCalibracao, PontoCalibracao>();

  const salvos = config ? { lo: Number(config.valores.sim_duvidoso), hi: Number(config.valores.sim_confiavel) } : null;
  useEffect(() => {
    if (salvos) {
      setLo(salvos.lo);
      setHi(salvos.hi);
    }
  }, [salvos?.lo, salvos?.hi]);

  const t = medicao.tarefa;
  const pontos = t?.resultado ? [...t.resultado.fora, ...t.resultado.dentro] : (t?.parciais ?? []);
  const validos = pontos.filter((p): p is PontoCalibracao & { sim: number } => p.sim != null);
  const dentro: Ponto[] = validos.filter((p) => p.grupo === "dentro").map((p) => ({ sim: p.sim, label: p.pergunta }));
  const fora: Ponto[] = validos.filter((p) => p.grupo === "fora").map((p) => ({ sim: p.sim, label: p.pergunta }));
  const D = contar(dentro.map((p) => p.sim), lo, hi);
  const F = contar(fora.map((p) => p.sim), lo, hi);
  const limpo = D[2] === 0 && F[0] === 0;
  const sugestao = sugerirCortes(dentro.map((p) => p.sim), fora.map((p) => p.sim));
  const mudou = salvos && (lo !== salvos.lo || hi !== salvos.hi);
  const fonte = t?.resultado?.fonte;

  const salvar = async () => {
    await api.gravarConfig({ sim_duvidoso: lo, sim_confiavel: hi });
    toast(`config.toml: sim_duvidoso = ${lo.toFixed(2)}, sim_confiavel = ${hi.toFixed(2)}. Vale na próxima busca.`);
    recarregar();
    recarregarEstado();
  };

  return (
    <div className="tela-conteudo" style={{ maxWidth: 980 }}>
      <div className="tela-titulo">
        <h1>Calibrar confiança</h1>
        <p>
          Cada ponto é uma pergunta medida no seu vault: a maior similaridade que ela alcança. Arraste as duas linhas e veja
          quais perguntas mudam de faixa. Os números mudam com o idioma, o assunto e o tamanho do vault.
        </p>
      </div>

      <Card className={css.card}>
        <CardHeader
          title={
            pontos.length
              ? `${dentro.length} perguntas com resposta · ${fora.length} sem resposta`
              : "Nenhuma medição ainda"
          }
          subtitle={
            fonte === "perguntas"
              ? "Com resposta: as perguntas que você escreveu em perguntas.txt."
              : fonte === "titulos"
                ? "Com resposta: títulos de notas reais. Sem resposta: perguntas que nenhum vault de trabalho responde."
                : "A medição embedda 10 perguntas que o vault não responde e até 20 que ele responde."
          }
          action={
            <Button variant="primary" icon={Play} loading={medicao.rodando} onClick={() => void medicao.iniciar(() => api.medirCalibracao())}>
              {t?.resultado ? "Medir de novo" : "Medir no meu vault"}
            </Button>
          }
        />
        {t?.estado === "rodando" && (
          <ProgressBar value={t.total ? t.feito / t.total : null} label={t.mensagem} detail={t.total ? `${t.feito} / ${t.total}` : ""} />
        )}
        {pontos.length > 0 && (
          <SimilarityPlot
            dentro={dentro}
            fora={fora}
            duvidoso={lo}
            confiavel={hi}
            onChange={({ duvidoso, confiavel }) => {
              setLo(duvidoso);
              setHi(confiavel);
            }}
          />
        )}
        {(medicao.erro || t?.estado === "erro") && (
          <Callout tone="baixa" title="A medição falhou">
            {medicao.erro?.message ?? t?.erro}
          </Callout>
        )}
      </Card>

      {fonte === "titulos" && (
        <Callout tone="info" title="Título casa com a própria nota quase por construção">
          Isso mede o caso fácil. Para medir de verdade, escreva perguntas com palavras que a nota não usa: rode{" "}
          <code>vault-vector testar-confianca --gerar-modelo perguntas.txt</code>, reescreva cada linha e meça de novo.
        </Callout>
      )}

      <div className={css.grade}>
        <Card className={css.card}>
          <CardHeader title="Matriz das faixas" subtitle="Só a similaridade: o juiz e o termo raro ainda podem mover uma pergunta da faixa média." />
          <table className={css.matriz}>
            <thead>
              <tr>
                <th />
                <th><ConfidenceBadge faixa="alta" size="sm" compact /></th>
                <th><ConfidenceBadge faixa="media" size="sm" compact /></th>
                <th><ConfidenceBadge faixa="baixa" size="sm" compact /></th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className={css.rotuloLinha}>com resposta</td>
                <td><Num v={D[0]} /></td>
                <td><Num v={D[1]} /></td>
                <td className={css.critica}><Num v={D[2]} critico /></td>
              </tr>
              <tr>
                <td className={css.rotuloLinha}>sem resposta</td>
                <td className={css.critica}><Num v={F[0]} critico /></td>
                <td><Num v={F[1]} /></td>
                <td><Num v={F[2]} /></td>
              </tr>
            </tbody>
          </table>
          {pontos.length > 0 && (
            <p className={limpo ? css.ok : css.alerta}>
              {limpo
                ? "As duas pontas limpas: nenhuma resposta certa desencorajada, nenhum ruído entregue sem ressalva."
                : [
                    D[2] ? `${D[2]} pergunta(s) com resposta caíram em baixa.` : "",
                    F[0] ? `${F[0]} sem resposta em alta — o pior erro: sai sem ressalva.` : "",
                  ].join(" ")}
            </p>
          )}
        </Card>

        <Card className={css.card}>
          <div className={css.valores}>
            <div>
              <div className="rotulo">sim_duvidoso</div>
              <span className={css.valorLo}>{lo.toFixed(2)}</span>
            </div>
            <div>
              <div className="rotulo">sim_confiavel</div>
              <span className={css.valorHi}>{hi.toFixed(2)}</span>
            </div>
          </div>
          <div className={css.botoes}>
            <Button variant="primary" icon={Save} disabled={!mudou} onClick={salvar}>
              Salvar
            </Button>
            <Button
              icon={Sparkles}
              disabled={!sugestao}
              title={sugestao ? "A faixa média mais estreita que deixa as duas pontas limpas" : "Meça antes"}
              onClick={() => {
                if (!sugestao) return;
                setLo(sugestao.duvidoso);
                setHi(sugestao.confiavel);
              }}
            >
              Sugerir
            </Button>
            <Button
              variant="ghost"
              icon={RotateCcw}
              onClick={() => {
                setLo(Number(config?.padroes.sim_duvidoso ?? 0.43));
                setHi(Number(config?.padroes.sim_confiavel ?? 0.6));
              }}
            >
              Padrão
            </Button>
          </div>
          {sugestao && !medicao.rodando && (
            <p className={css.nota}>
              {sugestao.sobrepoe
                ? `As populações se sobrepõem: para as pontas ficarem limpas, a faixa média precisa ir de ${sugestao.duvidoso.toFixed(2)} a ${sugestao.confiavel.toFixed(2)}. Tudo ali sai com ressalva — é onde o juiz local ajuda.`
                : "As populações não se sobrepõem neste vault: um corte entre elas separa tudo, e a faixa média pode ser estreita."}
            </p>
          )}
        </Card>
      </div>

      <Callout title="Por que três faixas, e não um corte">
        Medido num vault real: pergunta sem resposta ocupou 0,387–0,527; pergunta legítima escrita com outro vocabulário,
        0,435–0,607. As duas populações se sobrepõem, então qualquer corte único ou deixa passar ruído, ou recusa pergunta boa.
      </Callout>

      <div className={css.comandos}>
        <CommandBlock command="vault-vector calibrar" comment="mede as duas populações" />
        <CommandBlock command="vault-vector testar-confianca" comment="matriz de confusão com o pipeline inteiro" />
      </div>
    </div>
  );
}
