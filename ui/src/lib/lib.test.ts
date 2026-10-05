import { describe, expect, it } from "vitest";
import { bytes, dataDoNome, idade, numero } from "./formato";
import { previa, secaoDaLinha, secoes, semFrontmatter, wikilinksParaLinks } from "./markdown";
import { hrefNota, lerRota } from "./rota";

describe("wikilinks", () => {
  it("vira link que abre a nota no app, com o rotulo do alias", () => {
    expect(wikilinksParaLinks("ver [[Homelab/Backup|o backup]]")).toBe(
      `ver [o backup](${hrefNota("Homelab/Backup")})`,
    );
  });

  it("sem alias, usa o nome curto da nota", () => {
    expect(wikilinksParaLinks("[[Projetos/Caderneta/Decisoes]]")).toBe(
      `[Decisoes](${hrefNota("Projetos/Caderneta/Decisoes")})`,
    );
  });

  it("embed de anexo vira so o nome, porque o app nao serve anexo", () => {
    expect(wikilinksParaLinks("![[diagrama.png]]")).toBe("`diagrama.png`");
  });
});

describe("secoes da nota", () => {
  const nota = "# Backup\n\nIntro.\n\n## Como\n\n```\n# nao e titulo\n```\n\n## Teste\n\nTexto.";

  it("corta nos titulos e guarda a linha de cada secao", () => {
    expect(secoes(nota).map((s) => s.linha)).toEqual([1, 5, 11]);
  });

  it("titulo dentro de bloco de codigo nao abre secao", () => {
    expect(secoes(nota)[1]?.texto).toContain("# nao e titulo");
  });

  it("acha a secao de uma linha do indice", () => {
    expect(secaoDaLinha(secoes(nota), 7)).toBe(1);
    expect(secaoDaLinha(secoes(nota), 1)).toBe(0);
  });
});

describe("previa do trecho", () => {
  it("tira titulo, tabela e sintaxe, e deixa o texto corrido", () => {
    const trecho = "# Backup\n\n## Como\n\n| a | b |\n|---|---|\nUm **job** diario, ver [[Homelab/Rede|rede]].";
    expect(previa(trecho)).toBe("a b Um job diario, ver rede.");
  });

  it("pipe fora de tabela e conteudo, nao sintaxe", () => {
    expect(previa("o script engolia o erro com `|| true` no fim")).toBe("o script engolia o erro com || true no fim");
  });

  it("sublinhado no meio de identificador fica; enfase some", () => {
    expect(previa("export RESTIC_REPOSITORY=x e _importante_ e **forte**")).toBe(
      "export RESTIC_REPOSITORY=x e importante e forte",
    );
  });

  it("frontmatter some da leitura", () => {
    expect(semFrontmatter("---\ntags: [x]\n---\n# Nota\n")).toBe("# Nota\n");
  });
});

describe("formato", () => {
  const dia = 86_400;
  const agora = Date.UTC(2026, 9, 5);

  it("idade relativa em portugues", () => {
    expect(idade(agora / 1000 - 3 * dia, agora)).toBe("há 3 dias");
    expect(idade(agora / 1000 - 40 * dia, agora)).toBe("há 1 mês");
    expect(idade(agora / 1000 - 800 * dia, agora)).toBe("há 2 anos");
  });

  it("data do nome do arquivo nao escorrega para o dia anterior no fuso do Brasil", () => {
    // O backend guarda 2026-08-12 como meia-noite UTC.
    expect(dataDoNome(Date.UTC(2026, 7, 12) / 1000)).toBe("2026-08-12");
  });

  it("numeros e bytes em pt-BR", () => {
    expect(numero(4512)).toBe("4.512");
    expect(bytes(1_157_672_605)).toBe("1,1 GB");
  });
});

describe("rota", () => {
  it("le tela e parametros do hash", () => {
    const r = lerRota("#/nota?caminho=Homelab%2FBackup.md&linha=12");
    expect(r.tela).toBe("nota");
    expect(r.params.get("caminho")).toBe("Homelab/Backup.md");
  });

  it("hash desconhecido cai na busca", () => {
    expect(lerRota("#/qualquer").tela).toBe("buscar");
    expect(lerRota("").tela).toBe("buscar");
  });
});
