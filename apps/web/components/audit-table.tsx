"use client";

import { useState } from "react";

import type { AuditEvent } from "@/lib/types";

type Props = {
  events: AuditEvent[];
};

const STATUS_STYLES: Record<AuditEvent["status"], string> = {
  ok: "bg-emerald-100 text-emerald-800",
  warn: "bg-amber-100 text-amber-800",
  error: "bg-rose-100 text-rose-800",
};

export function AuditTable({ events }: Props) {
  if (events.length === 0) {
    return (
      <p className="text-sm text-neutral-500">
        No audit events for this thesis yet.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-md border border-neutral-200">
      <table className="min-w-full text-left text-xs">
        <thead className="bg-neutral-50 text-neutral-600">
          <tr>
            <th className="px-3 py-2 font-medium">Time</th>
            <th className="px-3 py-2 font-medium">Actor</th>
            <th className="px-3 py-2 font-medium">Action</th>
            <th className="px-3 py-2 font-medium">Status</th>
            <th className="px-3 py-2 font-medium">Model</th>
            <th className="px-3 py-2 font-medium">Tokens</th>
            <th className="px-3 py-2 font-medium">Cost</th>
            <th className="px-3 py-2 font-medium">Latency</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-200">
          {events.map((event) => (
            <AuditRow key={event.id} event={event} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AuditRow({ event }: { event: AuditEvent }) {
  const [open, setOpen] = useState(false);
  const tokens =
    event.input_tokens != null && event.output_tokens != null
      ? `${event.input_tokens} → ${event.output_tokens}`
      : "—";
  const cost = event.cost_usd != null ? `$${event.cost_usd.toFixed(4)}` : "—";
  const latency = event.latency_ms != null ? `${event.latency_ms} ms` : "—";
  const time = new Date(event.created_at).toLocaleTimeString();
  const hasPayload = Object.keys(event.payload).length > 0;

  return (
    <>
      <tr
        className={`hover:bg-neutral-50 ${hasPayload ? "cursor-pointer" : ""}`}
        onClick={() => hasPayload && setOpen((v) => !v)}
        aria-expanded={hasPayload ? open : undefined}
      >
        <td className="px-3 py-2 font-mono text-neutral-500">{time}</td>
        <td className="px-3 py-2 font-medium text-neutral-800">
          {event.actor}
        </td>
        <td className="px-3 py-2 text-neutral-700">{event.action}</td>
        <td className="px-3 py-2">
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${STATUS_STYLES[event.status]}`}
          >
            {event.status}
          </span>
        </td>
        <td className="px-3 py-2 text-neutral-600">{event.model ?? "—"}</td>
        <td className="px-3 py-2 text-neutral-600">{tokens}</td>
        <td className="px-3 py-2 text-neutral-600">{cost}</td>
        <td className="px-3 py-2 text-neutral-600">{latency}</td>
      </tr>
      {open && hasPayload ? (
        <tr className="bg-neutral-50">
          <td colSpan={8} className="px-3 py-2">
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-white p-2 text-[11px] text-neutral-700">
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          </td>
        </tr>
      ) : null}
    </>
  );
}

export function AuditSummary({ events }: Props) {
  const total = events.length;
  const errors = events.filter((e) => e.status === "error").length;
  const warns = events.filter((e) => e.status === "warn").length;
  const totalCost = events.reduce(
    (acc, e) => acc + (e.cost_usd ?? 0),
    0,
  );
  const totalIn = events.reduce(
    (acc, e) => acc + (e.input_tokens ?? 0),
    0,
  );
  const totalOut = events.reduce(
    (acc, e) => acc + (e.output_tokens ?? 0),
    0,
  );

  return (
    <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-5">
      <Stat label="Events" value={String(total)} />
      <Stat label="Errors" value={String(errors)} tone={errors > 0 ? "rose" : undefined} />
      <Stat label="Warnings" value={String(warns)} tone={warns > 0 ? "amber" : undefined} />
      <Stat label="Tokens (in → out)" value={`${totalIn.toLocaleString()} → ${totalOut.toLocaleString()}`} />
      <Stat label="Est. cost" value={`$${totalCost.toFixed(4)}`} />
    </dl>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "amber" | "rose";
}) {
  const valueClass =
    tone === "rose"
      ? "text-rose-700"
      : tone === "amber"
        ? "text-amber-700"
        : "text-neutral-800";
  return (
    <div className="rounded-md border border-neutral-200 bg-white p-3">
      <dt className="text-[10px] uppercase tracking-wide text-neutral-500">
        {label}
      </dt>
      <dd className={`mt-1 text-sm font-medium ${valueClass}`}>{value}</dd>
    </div>
  );
}
