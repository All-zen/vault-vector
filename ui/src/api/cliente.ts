import type {
  Busca,
  Config,
  Conexao,
  Embedding,
  Estado,
  EstadoOllama,
  Gravacao,
  Nota,
  NivelParalelo,
  NotaResumo,
  PontoCalibracao,
  Recorte,
  ResultadoCalibracao,
  ResultadoIndexacao,
  ResultadoParalelismo,
  Saude,
  Sistema,
  Tarefa,
  ValoresConfig,
  Vaults,
} from "./tipos";

export class ErroApi extends Error {
  readonly status: number;
  readonly codigo: string;

  constructor(status: number, mensagem: string, codigo = "") {
    super(mensagem);
    this.name = "ErroApi";
    this.status = status;
    this.codigo = codigo;
  }
}

// O servidor Python embute o token nesta meta tag ao servir a pagina. Em
// desenvolvimento ela vem vazia e o proxy do Vite manda o header.
function token(): string {
  return document.querySelector<HTMLMetaElement>('meta[name="vv-token"]')?.content ?? "";
}

type Params = Record<string, string | number | boolean | null | undefined>;

function query(params?: Params): string {
  if (!params) return "";
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

async function pedir<T>(metodo: "GET" | "POST", caminho: string, corpo?: unknown, params?: Params): Promise<T> {
  const headers: Record<string, string> = {};
  const t = token();
  if (t) headers.Authorization = `Bearer ${t}`;
  if (corpo !== undefined) headers["Content-Type"] = "application/json";

  let resposta: Response;
  try {
    resposta = await fetch(caminho + query(params), {
      method: metodo,
      headers,
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
  } catch {
    throw new ErroApi(0, "O vault-vector nao respondeu. O app ainda esta aberto?", "offline");
  }

  const dados = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    throw new ErroApi(resposta.status, dados?.erro ?? resposta.statusText, dados?.codigo ?? "");
  }
  return dados as T;
}

const get = <T>(caminho: string, params?: Params) => pedir<T>("GET", caminho, undefined, params);
const post = <T>(caminho: string, corpo: unknown = {}) => pedir<T>("POST", caminho, corpo);

export const api = {
  estado: () => get<Estado>("/api/estado"),
  buscar: (q: string, secao?: string, k = 8) => get<Busca>("/api/buscar", { q, secao, k }),
  notas: (secao?: string, limite = 30) => get<NotaResumo[]>("/api/notas", { secao, limite }),

  nota: (caminho: string) => get<Nota>("/api/nota", { caminho }),
  gravarNota: (caminho: string, conteudo: string, mtime: number | null, nova = false) =>
    post<Gravacao>("/api/nota", { caminho, conteudo, mtime, nova }),
  moverNota: (de: string, para: string, links: boolean) =>
    post<{ de: string; para: string; links_atualizados: number }>("/api/nota/mover", { de, para, links }),
  apagarNota: (caminho: string) =>
    post<{ path: string; lixeira: string; citada_por: number }>("/api/nota/apagar", { caminho }),
  restaurarNota: (caminho: string, versao: string, mtime: number) =>
    post<Gravacao>("/api/nota/restaurar", { caminho, versao, mtime }),

  saude: () => get<Saude>("/api/saude"),
  indexar: (modo: { forcar?: boolean; refazer_trechos?: boolean } = {}) =>
    post<Tarefa<ResultadoIndexacao>>("/api/indexar", modo),
  tarefa: <R, P>(id: string) => get<Tarefa<R, P>>(`/api/tarefas/${id}`),

  ollama: (url?: string) => get<EstadoOllama>("/api/ollama", { url }),
  embeddar: (texto: string, modelo?: string) => post<Embedding>("/api/ollama/embeddar", { texto, modelo }),
  baixarModelo: (modelo: string) => post<Tarefa<{ modelo: string }>>("/api/ollama/baixar", { modelo }),
  medirParalelismo: () => post<Tarefa<ResultadoParalelismo, NivelParalelo>>("/api/medir/paralelismo"),
  medirCalibracao: () => post<Tarefa<ResultadoCalibracao, PontoCalibracao>>("/api/medir/calibracao"),

  config: () => get<Config>("/api/config"),
  gravarConfig: (valores: ValoresConfig) => post<Config>("/api/config", { valores }),
  recorte: (params: Params) => get<Recorte>("/api/recorte", params),

  conectar: () => get<Conexao>("/api/conectar"),
  vaults: () => get<Vaults>("/api/vaults"),
  escolherVault: (caminho: string, criar: boolean) =>
    post<{ vault: string; criados: string[]; estado: Estado }>("/api/vault", { caminho, criar }),

  sistema: () => get<Sistema>("/api/sistema"),
  autostart: (ligado: boolean) => post<Sistema>("/api/sistema/autostart", { ligado }),
};
