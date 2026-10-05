import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { api } from "../api/cliente";
import { Badge, Button, Callout, Card, CardHeader, Tabs } from "../componentes/ds";
import { CommandBlock } from "../componentes/vault";
import { useDados } from "../lib/dados";
import css from "./Conectar.module.css";

const ESCRITA = /edit|append|write|move|delete/;

export function Conectar() {
  const { dados: c, erro } = useDados(() => api.conectar(), []);
  const [aba, setAba] = useState("code");
  const [ver, setVer] = useState(false);

  if (erro) return <div className="tela-conteudo" style={{ maxWidth: 820 }}><Callout tone="baixa">{erro.message}</Callout></div>;
  if (!c) return null;

  // O token aparece mascarado; o botao de copiar leva o valor de verdade.
  const mascara = c.token ? `${c.token.slice(0, 4)}${"•".repeat(12)}` : "";
  const token = (mostrar: boolean) => (mostrar ? c.token : mascara);
  const comandoCode = (t: string) =>
    `claude mcp add --scope user --transport http vault-vector ${c.url}` + (t ? ` --header "Authorization: Bearer ${t}"` : "");
  const python = c.python.replace(/\\/g, "/");
  const jsonDesktop = JSON.stringify(
    { mcpServers: { "vault-vector": { command: python, args: ["-m", "vault_rag.server"] } } },
    null,
    2,
  );

  return (
    <div className="tela-conteudo" style={{ maxWidth: 820 }}>
      <div className="tela-titulo">
        <h1>Conectar ao Claude</h1>
        <p>Um processo serve todos os clientes MCP, e roda inteiro na sua máquina. Os comandos abaixo já saem com o endereço e o token deste app.</p>
      </div>

      <Tabs
        items={[
          { id: "code", label: "Claude Code" },
          { id: "desktop", label: "Claude Desktop" },
        ]}
        value={aba}
        onChange={setAba}
      />

      {aba === "code" ? (
        <div className={css.bloco}>
          <p className={css.texto}>Num terminal qualquer, uma vez só. O Claude Code passa a enxergar o vault em todo projeto.</p>
          <CommandBlock command={comandoCode(c.token)} display={comandoCode(token(ver))} wrap />
          {c.token && (
            <div className={css.token}>
              <Button size="sm" variant="ghost" icon={ver ? EyeOff : Eye} onClick={() => setVer(!ver)}>
                {ver ? "Esconder o token" : "Mostrar o token"}
              </Button>
              <span>Quem tem o token lê e escreve no vault. Ele fica no arquivo <code>.token</code>, ao lado do config.</span>
            </div>
          )}
        </div>
      ) : (
        <div className={css.bloco}>
          <p className={css.texto}>
            Em <code>claude_desktop_config.json</code>, dentro de <code>mcpServers</code>. O Desktop sobe o próprio processo pelo
            stdio, então não precisa do token.
          </p>
          <CommandBlock command={jsonDesktop} />
        </div>
      )}

      <Card>
        <div className={css.ferramentas}>
          <CardHeader title="O que o Claude passa a poder fazer" />
          <div className={css.selos}>
            {c.ferramentas.map((f) => (
              <Badge key={f} mono tone={ESCRITA.test(f) ? "accent" : "neutral"}>
                {f}
              </Badge>
            ))}
          </div>
          <span className={css.texto}>
            As de escrita, em teal, copiam a versão anterior para <code>_historico/</code> antes de gravar, e recusam se a nota
            mudou no disco desde a leitura.
          </span>
        </div>
      </Card>

      <Callout title="A descrição do vault é automática">
        O servidor lê o próprio índice e conta ao modelo as seções, as subpastas e as convenções de diário e de índice. Você não
        precisa escrever instruções para o Claude saber onde procurar.
      </Callout>
    </div>
  );
}
