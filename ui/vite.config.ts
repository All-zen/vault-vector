import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Em producao a interface e servida pelo proprio processo Python, que
// embute o token no index.html. Em desenvolvimento quem serve e o Vite, entao
// o proxy faz o papel do Python: le o .token do projeto e manda o header.
function tokenDoProjeto(): string {
  try {
    return readFileSync(resolve(import.meta.dirname, "../.token"), "utf-8").trim();
  } catch {
    return "";
  }
}

const servidor = process.env.VV_SERVIDOR ?? "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  build: {
    // Vai para dentro do pacote Python: e de la que o web.py serve.
    outDir: resolve(import.meta.dirname, "../vault_rag/static"),
    emptyOutDir: true,
    target: "es2022",
  },
  server: {
    proxy: {
      "/api": {
        target: servidor,
        changeOrigin: true,
        configure(proxy) {
          proxy.on("proxyReq", (req) => {
            const token = tokenDoProjeto();
            if (token) req.setHeader("Authorization", `Bearer ${token}`);
            // O servidor recusa escrita vinda de outra origem, e a pagina de
            // dev roda em outra porta. O proxy e local: pode tirar.
            req.removeHeader("origin");
          });
        },
      },
    },
  },
  test: {
    environment: "jsdom",
  },
});
