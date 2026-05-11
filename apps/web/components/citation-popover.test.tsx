import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ChunkSnippet } from "@/lib/types";

import { CitationPopover } from "./citation-popover";

const grounded: ChunkSnippet = {
  chunk_id: "11111111-1111-1111-1111-000000000001",
  source_id: "22222222-2222-2222-2222-000000000001",
  text: "Acme reported strong revenue growth in Q3.",
  source_kind: "news",
  source_provider: "news_api",
  source_url: "https://example.com/article",
  source_title: "Acme Q3 results",
};

const ghost: ChunkSnippet = {
  chunk_id: "11111111-1111-1111-1111-000000000099",
  source_id: "22222222-2222-2222-2222-000000000001",
  text: "(orphan)",
  source_kind: null,
  source_provider: null,
  source_url: null,
  source_title: null,
};

describe("CitationPopover", () => {
  function setup(chunkIds: string[]) {
    const chunkIndex = new Map<string, ChunkSnippet>([
      [grounded.chunk_id, grounded],
    ]);
    return {
      chunkIndex,
      ...render(
        <CitationPopover index={1} chunkIds={chunkIds} chunkIndex={chunkIndex} />,
      ),
    };
  }

  it("renders the citation marker collapsed", () => {
    setup([grounded.chunk_id]);
    const button = screen.getByRole("button", { name: /\[1\]/ });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens the popover and shows source text on click", async () => {
    const user = userEvent.setup();
    setup([grounded.chunk_id]);
    await user.click(screen.getByRole("button", { name: /\[1\]/ }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(
      screen.getByText("Acme reported strong revenue growth in Q3."),
    ).toBeInTheDocument();
    expect(screen.getByText("Acme Q3 results")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open source/ })).toHaveAttribute(
      "href",
      "https://example.com/article",
    );
  });

  it("closes when the user presses Escape", async () => {
    const user = userEvent.setup();
    setup([grounded.chunk_id]);
    await user.click(screen.getByRole("button", { name: /\[1\]/ }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows a graceful empty state when chunk_ids resolve to nothing", async () => {
    const user = userEvent.setup();
    setup([ghost.chunk_id]); // not in the chunkIndex
    await user.click(screen.getByRole("button", { name: /\[1\]/ }));
    expect(screen.getByText(/0 supporting chunks/)).toBeInTheDocument();
    expect(
      screen.getByText(/No supporting chunks were resolved/),
    ).toBeInTheDocument();
  });

  it("toggles open / closed on repeated clicks", async () => {
    const user = userEvent.setup();
    setup([grounded.chunk_id]);
    const button = screen.getByRole("button", { name: /\[1\]/ });
    await user.click(button);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.click(button);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
