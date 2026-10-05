const inteiro = new Intl.NumberFormat("pt-BR");

export function numero(n: number | null | undefined): string {
  return n == null ? "—" : inteiro.format(n);
}

export function decimal(n: number | null | undefined, casas = 3): string {
  return n == null ? "—" : n.toFixed(casas);
}

export function bytes(n: number | null | undefined): string {
  if (n == null) return "—";
  const unidades = ["B", "KB", "MB", "GB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < unidades.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toLocaleString("pt-BR", { maximumFractionDigits: v < 10 && i > 0 ? 1 : 0 })} ${unidades[i]}`;
}

/** Data de um timestamp em segundos, no formato do vault (AAAA-MM-DD). */
export function data(ts: number | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function dataHora(ts: number | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${data(ts)} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** "há 3 meses". Nota antiga ainda aparece como relevante; saber de quando muda a leitura. */
export function idade(ts: number | null | undefined, agora = Date.now()): string {
  if (!ts) return "";
  const dias = Math.floor((agora - ts * 1000) / 86_400_000);
  if (dias < 1) return "hoje";
  if (dias === 1) return "ontem";
  if (dias < 30) return `há ${dias} dias`;
  const meses = Math.floor(dias / 30);
  if (meses < 12) return meses === 1 ? "há 1 mês" : `há ${meses} meses`;
  const anos = Math.floor(dias / 365);
  return anos === 1 ? "há 1 ano" : `há ${anos} anos`;
}

const TIPOS: Record<string, string> = {
  indice: "índice",
  diario: "diário",
  operacional: "operacional",
  spec: "especificação",
  pesquisa: "pesquisa",
  estrategia: "estratégia",
  nota: "nota",
};

export function tipoNota(tipo: string): string {
  return TIPOS[tipo] ?? tipo;
}

export function plural(n: number, um: string, varios: string): string {
  return `${numero(n)} ${n === 1 ? um : varios}`;
}
