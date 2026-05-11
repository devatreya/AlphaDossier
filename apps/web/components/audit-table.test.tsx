import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { AuditEvent } from "@/lib/types";

import { AuditSummary, AuditTable } from "./audit-table";

const e1: AuditEvent = {
  id: "44444444-4444-4444-4444-000000000001",
  actor: "news_agent",
  action: "agent_call",
  status: "ok",
  model: "claude-sonnet-4-6",
  input_tokens: 1234,
  output_tokens: 567,
  cost_usd: 0.0123,
  latency_ms: 420,
  payload: { output: { recent_events: 3 } },
  created_at: "2026-05-09T09:30:00Z",
};

const e2: AuditEvent = {
  id: "44444444-4444-4444-4444-000000000002",
  actor: "fred",
  action: "fetch_series:DGS10",
  status: "warn",
  model: null,
  input_tokens: null,
  output_tokens: null,
  cost_usd: null,
  latency_ms: null,
  payload: { reason: "MissingApiKeyError" },
  created_at: "2026-05-09T09:31:00Z",
};

describe("AuditTable", () => {
  it("renders an empty-state message when there are no events", () => {
    render(<AuditTable events={[]} />);
    expect(
      screen.getByText(/No audit events for this thesis yet/),
    ).toBeInTheDocument();
  });

  it("renders rows with formatted token / cost / latency values", () => {
    render(<AuditTable events={[e1, e2]} />);
    expect(screen.getByText("news_agent")).toBeInTheDocument();
    expect(screen.getByText("agent_call")).toBeInTheDocument();
    expect(screen.getByText("1234 → 567")).toBeInTheDocument();
    expect(screen.getByText("$0.0123")).toBeInTheDocument();
    expect(screen.getByText("420 ms")).toBeInTheDocument();
    // Warn row uses em-dash for missing numerics.
    expect(screen.getByText("fetch_series:DGS10")).toBeInTheDocument();
  });

  it("expands the payload when the row is clicked", async () => {
    const user = userEvent.setup();
    render(<AuditTable events={[e1]} />);
    const row = screen.getByText("news_agent").closest("tr");
    expect(row).not.toBeNull();
    await user.click(row!);
    expect(
      screen.getByText(/recent_events/),
    ).toBeInTheDocument();
    // Click again collapses it.
    await user.click(row!);
    expect(screen.queryByText(/recent_events/)).not.toBeInTheDocument();
  });
});

describe("AuditSummary", () => {
  it("aggregates totals across events", () => {
    render(<AuditSummary events={[e1, e2]} />);
    // Two events total.
    expect(screen.getByText("Events")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    // One warning, no errors.
    expect(screen.getByText("Warnings")).toBeInTheDocument();
    // Tokens summed (1234 → 567 + 0 + 0).
    expect(screen.getByText(/1,234 → 567/)).toBeInTheDocument();
    expect(screen.getByText("$0.0123")).toBeInTheDocument();
  });
});
