import { describe, expect, it } from "vitest";
import { mesmoModelo } from "./Modelos";

// Os mesmos casos do selftest para ollama.mesmo_modelo: as duas pontas
// precisam concordar sobre qual modelo instalado e o do config.
describe("mesmoModelo", () => {
  it("nome sem tag casa com :latest", () => {
    expect(mesmoModelo("bge-m3", "bge-m3:latest")).toBe(true);
  });

  it("tag diferente nao casa", () => {
    expect(mesmoModelo("qwen2.5:3b", "qwen2.5:7b")).toBe(false);
  });

  it("nome com tag casa consigo e com :latest dele", () => {
    expect(mesmoModelo("qwen2.5:3b-instruct", "qwen2.5:3b-instruct")).toBe(true);
  });

  it("config vazio (juiz desligado) nao casa com nada", () => {
    expect(mesmoModelo("", "qwen2.5:3b-instruct")).toBe(false);
  });
});
