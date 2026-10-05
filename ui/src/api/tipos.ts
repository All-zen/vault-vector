// Formatos devolvidos pelo vault_rag/web.py. Os nomes seguem o backend.

export type Faixa = "alta" | "media" | "baixa";

export interface Secao {
  nome: string;
  notas: number;
}

export interface Estado {
  versao: string;
  desktop: boolean;
  configurado: boolean;
  motivo?: string;
  vault?: string;
  vault_nome?: string;
  modelo?: string;
  juiz?: string;
  notas?: number;
  trechos?: number;
  indice_mb?: number;
  indice_modelo?: string | null;
  ultima_indexacao?: string | null;
  secoes?: Secao[];
  ollama?: { ok: boolean; ms: number | null };
}

export interface Hit {
  chunk_id: number;
  path: string;
  titulo: string;
  heading: string;
  linha: number;
  trecho: string;
  score: number;
  vec_rank: number | null;
  fts_rank: number | null;
  vec_score: number | null;
  rerank: number | null;
  tipo: string;
  data: number | null;
  mtime: number | null;
  secao: string;
  backlinks: number;
  boost: number;
  fatores: [string, number][];
}

export interface Busca {
  consulta: string;
  faixa: Faixa | null;
  sim: number | null;
  juiz: number | null;
  julgados: number;
  segundos: number;
  semantico: boolean;
  fts_total: number | null;
  candidatos: number;
  rrf_k: number;
  modelo: string;
  limiares: { confiavel: number; duvidoso: number };
  hits: Hit[];
}

export interface NotaResumo {
  path: string;
  title: string;
  section: string;
  note_kind: string;
  note_ts: number | null;
  mtime: number;
  n_chunks: number;
  backlinks: number;
}

export interface Trecho {
  id: number;
  ord: number;
  heading_path: string;
  start_line: number;
  chars: number;
  embed_hash: string | null;
}

export interface Versao {
  versao: string;
  quando: string;
  bytes: number;
}

export interface Nota {
  path: string;
  titulo: string;
  conteudo: string;
  mtime: number;
  bytes: number;
  secao: string;
  tipo: string;
  data: number | null;
  indexada: boolean;
  desatualizada: boolean;
  trechos: Trecho[];
  citada_por: string[];
  versoes: Versao[];
}

export interface Gravacao {
  path: string;
  acao: string;
  historico: string | null;
  indice: string;
  nota: Nota;
}

export type StatusItem = "ok" | "aviso" | "falta";

export interface ItemDiagnostico {
  status: StatusItem;
  rotulo: string;
  detalhe: string;
  dica: string;
}

export interface GrupoDiagnostico {
  id: string;
  nome: string;
  itens: ItemDiagnostico[];
}

export interface Saude {
  grupos: GrupoDiagnostico[];
  indice: {
    files: number;
    chunks: number;
    db_mb: number;
    model: string | null;
    last_index: string | null;
    pending: number;
  };
  mapa: { total: number; pendentes: number[]; amostra: string[]; removidas: number };
}

export interface Tarefa<R = unknown, P = unknown> {
  id: string;
  tipo: string;
  estado: "rodando" | "ok" | "erro";
  feito: number;
  total: number | null;
  mensagem: string;
  parciais: P[];
  resultado: R | null;
  erro: string;
  segundos: number;
}

export interface ResultadoIndexacao {
  texto: string;
  indexadas: number;
  removidas: number;
  trechos: number;
  erros: string[];
}

export interface ModeloOllama {
  nome: string;
  tipo: "embedding" | "instrucao";
  dims: number | null;
  bytes: number | null;
  parametros: string | null;
  quantizacao: string | null;
  carregado: boolean;
  expira: string | null;
}

export interface EstadoOllama {
  ok: boolean;
  url: string;
  ms: number | null;
  versao: string | null;
  erro: string;
  modelos: ModeloOllama[];
  modelo: string;
  juiz: string;
  indice_modelo: string | null;
  config_url: string;
}

export interface Embedding {
  modelo: string;
  dims: number;
  ms: number;
  norma: number;
  valores: number[];
}

export interface NivelParalelo {
  paralelo: number;
  chamadas: number;
  segundos: number;
  taxa: number;
  ganho: number;
}

export interface ResultadoParalelismo {
  resultados: NivelParalelo[];
  melhor: NivelParalelo;
  inutil: boolean;
  amostra: number;
  total_notas: number;
  parallel_atual: number;
}

export interface PontoCalibracao {
  grupo: "fora" | "dentro";
  pergunta: string;
  sim: number | null;
  erro?: string;
}

export interface ResultadoCalibracao {
  fonte: "perguntas" | "titulos";
  fora: PontoCalibracao[];
  dentro: PontoCalibracao[];
  sugestao: Record<string, number | boolean> | null;
}

export type ValoresConfig = Record<string, string | number | boolean>;

export interface Config {
  arquivo: string;
  configurado: boolean;
  valores: ValoresConfig;
  padroes: ValoresConfig;
  reindexam: string[];
  perguntas: boolean;
  reindexar?: boolean;
}

export interface Recorte {
  caminho: string;
  chars: number;
  trechos: { ord: number; heading: string; linha: number; chars: number; inicio: string }[];
}

export interface Conexao {
  url: string;
  token: string;
  python: string;
  ferramentas: string[];
}

export interface VaultEncontrado {
  caminho: string;
  nome: string;
  notas: number;
}

export interface Vaults {
  encontrados: VaultEncontrado[];
  atual: string | null;
  sugestao_nova: string;
}

export interface Sistema {
  versao: string;
  desktop: boolean;
  autostart: { suportado: boolean; ligado: boolean };
  /** Atalho global que traz o app de qualquer lugar, se conseguiu registrar. */
  atalho: string | null;
  config: string;
  python: string;
}
