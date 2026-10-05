import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { IndexGrid, ScoreBreakdown, SimilarityPlot } from ".";

afterEach(cleanup);

describe("ScoreBreakdown", () => {
  it("monta o score com a conta do store.py: RRF dos dois lados vezes o boost", () => {
    render(<ScoreBreakdown vecRank={1} ftsRank={3} rrfK={60} factors={[["backlinks 2", 1.024]]} />);
    const base = 1 / 61 + 1 / 63;
    expect(screen.getByText(`= ${base.toFixed(4)}`, { exact: false })).toBeTruthy();
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe(`score ${(base * 1.024).toFixed(4)}`);
  });

  it("lado que nao trouxe o trecho aparece como traco, sem somar", () => {
    render(<ScoreBreakdown vecRank={null} ftsRank={1} rrfK={60} factors={[]} />);
    expect(screen.getByText("—")).toBeTruthy();
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe(`score ${(1 / 61).toFixed(4)}`);
  });
});

describe("SimilarityPlot", () => {
  const pontos = { dentro: [{ sim: 0.62, label: "a" }], fora: [{ sim: 0.4, label: "b" }] };

  it("as alcas andam pelo teclado, de 0,01 em 0,01", () => {
    const onChange = vi.fn();
    render(<SimilarityPlot {...pontos} duvidoso={0.43} confiavel={0.6} onChange={onChange} />);
    const [lo] = screen.getAllByRole("slider");
    fireEvent.keyDown(lo!, { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledWith({ duvidoso: 0.44, confiavel: 0.6 });
  });

  it("a linha de baixo nunca passa a de cima", () => {
    const onChange = vi.fn();
    render(<SimilarityPlot {...pontos} duvidoso={0.58} confiavel={0.6} onChange={onChange} />);
    const [lo] = screen.getAllByRole("slider");
    fireEvent.keyDown(lo!, { key: "ArrowRight", shiftKey: true });
    expect(onChange).toHaveBeenCalledWith({ duvidoso: 0.58, confiavel: 0.6 });
  });
});

describe("IndexGrid", () => {
  it("em vault grande, agrupa notas por celula e marca o grupo pendente", () => {
    const { container } = render(<IndexGrid total={1000} pending={[0, 1, 999]} maxCells={100} />);
    const celulas = container.querySelectorAll("[class*=celula]");
    expect(celulas).toHaveLength(100);
    expect(container.querySelectorAll("[class*=pendente]")).toHaveLength(2);
    expect(screen.getByText("1 célula ≈ 10 notas")).toBeTruthy();
  });
});
