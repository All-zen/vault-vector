import { describe, expect, it } from "vitest";
import { contar, sugerirCortes } from "./Calibrar";

describe("calibracao", () => {
  it("conta cada pergunta na faixa em que o cosseno cai", () => {
    expect(contar([0.65, 0.5, 0.43, 0.42], 0.43, 0.6)).toEqual([1, 2, 1]);
  });

  it("com sobreposicao, a faixa media cobre a sobreposicao inteira", () => {
    // ruido ate 0,48; legitima a partir de 0,45
    expect(sugerirCortes([0.45, 0.55, 0.62], [0.33, 0.41, 0.48])).toEqual({
      duvidoso: 0.44,
      confiavel: 0.49,
      sobrepoe: true,
    });
  });

  it("sem sobreposicao, a faixa media fica estreita logo acima do ruido", () => {
    expect(sugerirCortes([0.6, 0.7], [0.3, 0.4])).toEqual({ duvidoso: 0.39, confiavel: 0.41, sobrepoe: false });
  });

  it("os cortes sugeridos deixam as duas pontas limpas", () => {
    const dentro = [0.44, 0.52, 0.61, 0.7];
    const fora = [0.31, 0.47, 0.53];
    const s = sugerirCortes(dentro, fora)!;
    expect(contar(dentro, s.duvidoso, s.confiavel)[2]).toBe(0);
    expect(contar(fora, s.duvidoso, s.confiavel)[0]).toBe(0);
  });

  it("sem medicao nao inventa corte", () => {
    expect(sugerirCortes([], [0.4])).toBeNull();
  });
});
