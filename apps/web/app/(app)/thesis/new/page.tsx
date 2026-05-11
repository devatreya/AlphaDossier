"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorBanner } from "@/components/error-banner";
import { ApiError, createThesis } from "@/lib/api";

export default function NewThesisPage() {
  const router = useRouter();
  const [ticker, setTicker] = useState("");
  const [focus, setFocus] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await createThesis({
        ticker: ticker.trim(),
        focus_question: focus.trim() || null,
      });
      router.push(`/thesis/${res.thesis_id}` as never);
    } catch (e) {
      const message =
        e instanceof ApiError
          ? typeof (e.body as { detail?: unknown })?.detail === "string"
            ? ((e.body as { detail?: string }).detail ?? e.message)
            : e.message
          : "Could not start the thesis run.";
      setError(message);
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="text-2xl font-semibold tracking-tight">New thesis</h1>
      <p className="mt-2 text-sm text-neutral-500">
        Submit a ticker. The orchestrator runs in the background; you&apos;ll
        be redirected to the dossier as it streams in.
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-5">
        <div>
          <label
            htmlFor="ticker"
            className="block text-sm font-medium text-neutral-700"
          >
            Ticker
          </label>
          <input
            id="ticker"
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="NVDA, SHEL.L, ^GSPC, …"
            required
            disabled={submitting}
            className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-neutral-500 focus:outline-none disabled:bg-neutral-100"
          />
        </div>
        <div>
          <label
            htmlFor="focus"
            className="block text-sm font-medium text-neutral-700"
          >
            Focus question{" "}
            <span className="text-neutral-400">(optional)</span>
          </label>
          <textarea
            id="focus"
            value={focus}
            onChange={(e) => setFocus(e.target.value)}
            rows={3}
            maxLength={500}
            disabled={submitting}
            placeholder="e.g. how durable is the AI compute demand?"
            className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-neutral-500 focus:outline-none disabled:bg-neutral-100"
          />
        </div>

        {error ? <ErrorBanner title="Submission failed" detail={error} /> : null}

        <button
          type="submit"
          disabled={submitting || !ticker.trim()}
          className="inline-flex items-center rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-neutral-700 disabled:bg-neutral-400"
        >
          {submitting ? "Starting…" : "Run thesis"}
        </button>
      </form>
    </main>
  );
}
