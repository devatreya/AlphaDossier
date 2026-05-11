import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { nvdaCitations, nvdaDossier } from "@/lib/demos/nvda";

import { ThesisViewer } from "./thesis-viewer";

describe("ThesisViewer", () => {
  function setup() {
    return render(
      <ThesisViewer
        ticker="NVDA"
        focusQuestion="how durable is AI compute demand?"
        dossier={nvdaDossier}
        citations={nvdaCitations}
      />,
    );
  }

  it("renders the ticker and stance badge", () => {
    setup();
    expect(
      screen.getByRole("heading", { level: 1, name: "NVDA" }),
    ).toBeInTheDocument();
    // The capitalize span is the badge label specifically; the prose may
    // also contain "positive" so we narrow to the badge by selector.
    expect(
      screen.getByText("positive", { selector: ".capitalize" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/evidence 74%/i)).toBeInTheDocument();
  });

  it("renders the focus question if provided", () => {
    setup();
    expect(
      screen.getByText(/how durable is AI compute demand/),
    ).toBeInTheDocument();
  });

  it("renders all the major sections", () => {
    setup();
    for (const heading of [
      "Executive summary",
      "Bull case",
      "Bear case",
      "Catalysts",
      "Key risks",
      "Disconfirming evidence",
      "Macro context",
      "Valuation",
      "Quant snapshot",
      "Limitations",
    ]) {
      expect(
        screen.getByRole("heading", { level: 2, name: heading }),
      ).toBeInTheDocument();
    }
  });

  it("renders the analyst disclaimer", () => {
    setup();
    expect(
      screen.getByText(/research-prototype output/),
    ).toBeInTheDocument();
  });

  it("emits citation markers for sections with citations", () => {
    setup();
    const markers = screen.getAllByRole("button", { name: /\[\d+\]/ });
    // At least one per major cited section: executive summary, several bulls,
    // bears, catalysts, risks, disconfirming, macro, valuation.
    expect(markers.length).toBeGreaterThanOrEqual(8);
  });

  it("renders empty-section placeholders when a list is empty", () => {
    render(
      <ThesisViewer
        ticker="X"
        focusQuestion={null}
        dossier={{
          ...nvdaDossier,
          bull_case: [],
          bear_case: [],
          catalysts: [],
          key_risks: [],
          disconfirming_evidence: [],
        }}
        citations={[]}
      />,
    );
    expect(
      screen.getByText(/No bull-case statements were cited/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/No bear-case statements were cited/),
    ).toBeInTheDocument();
  });
});
