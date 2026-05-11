"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ErrorBanner } from "@/components/error-banner";
import { Loading } from "@/components/loading";
import { ThesisViewer } from "@/components/thesis-viewer";
import {
  ApiError,
  getCitations,
  getThesis,
  isAbortError,
} from "@/lib/api";
import type {
  CitationListItem,
  ThesisGetResponse,
  ThesisStatus,
} from "@/lib/types";

const POLL_INTERVAL_MS = 4000;
const TERMINAL_STATUSES: ReadonlySet<ThesisStatus> = new Set([
  "completed",
  "failed",
  "cancelled",
]);

type CitationsState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "loaded"; items: CitationListItem[] }
  | { kind: "failed"; message: string };

type PageProps = { params: { id: string } };

export default function ThesisPage({ params }: PageProps) {
  // Re-mount the inner component on thesisId change so all useState values
  // reset to their initial defaults. Without `key`, navigating from one
  // thesis to another would briefly render the previous dossier and citations
  // under the new URL until the first fresh poll resolved.
  return <ThesisPageInner key={params.id} thesisId={params.id} />;
}

function ThesisPageInner({ thesisId }: { thesisId: string }) {
  const [thesis, setThesis] = useState<ThesisGetResponse | null>(null);
  const [citations, setCitations] = useState<CitationsState>({ kind: "idle" });
  const [error, setError] = useState<string | null>(null);
  // Bumped on each manual citation retry so the in-flight effect can be
  // distinguished from a stale one if the user spams the button.
  const [retryNonce, setRetryNonce] = useState(0);

  const retryCitations = useCallback(() => {
    setRetryNonce((n) => n + 1);
  }, []);

  // ---------- main poll loop + initial citations fetch ----------
  // The cancelled flag is scoped to each effect run, so an in-flight response
  // from a previous thesisId can't call setState on the new component state.
  // The AbortController additionally cancels the underlying fetch.
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function fetchCitationsOnce() {
      if (cancelled) return;
      setCitations({ kind: "loading" });
      try {
        const cits = await getCitations(thesisId, {
          signal: controller.signal,
        });
        if (cancelled) return;
        setCitations({ kind: "loaded", items: cits.citations });
      } catch (e) {
        if (cancelled || isAbortError(e)) return;
        const message =
          e instanceof Error ? e.message : "Could not load citations.";
        setCitations({ kind: "failed", message });
      }
    }

    async function poll(): Promise<void> {
      if (cancelled) return;
      try {
        const next = await getThesis(thesisId, { signal: controller.signal });
        if (cancelled) return;
        setThesis(next);
        setError(null);
        if (TERMINAL_STATUSES.has(next.status)) {
          if (next.status === "completed") {
            void fetchCitationsOnce();
          }
          return;
        }
      } catch (e) {
        if (cancelled || isAbortError(e)) return;
        if (e instanceof ApiError && e.status === 404) {
          setError("Thesis not found.");
          return;
        }
        // Transient error — keep polling.
        console.warn("poll error", e);
      }
      timer = setTimeout(poll, POLL_INTERVAL_MS);
    }

    void poll();
    return () => {
      cancelled = true;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [thesisId]);

  // ---------- citations retry effect ----------
  // Separate effect, gated on the retry nonce. Triggered only when the user
  // clicks Retry; idempotent because each click bumps the nonce.
  useEffect(() => {
    if (retryNonce === 0) return;
    if (!thesis || thesis.status !== "completed") return;
    let cancelled = false;
    const controller = new AbortController();

    (async () => {
      setCitations({ kind: "loading" });
      try {
        const cits = await getCitations(thesisId, {
          signal: controller.signal,
        });
        if (cancelled) return;
        setCitations({ kind: "loaded", items: cits.citations });
      } catch (e) {
        if (cancelled || isAbortError(e)) return;
        const message =
          e instanceof Error ? e.message : "Could not load citations.";
        setCitations({ kind: "failed", message });
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [retryNonce, thesisId, thesis]);

  if (error) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <ErrorBanner title="Could not load thesis" detail={error} />
      </main>
    );
  }

  if (!thesis) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <Loading label="Loading thesis…" />
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <StatusStrip thesis={thesis} />
      <div className="mt-3 text-right">
        <Link
          href={`/thesis/${thesisId}/audit` as never}
          className="text-xs text-neutral-500 hover:text-neutral-900 hover:underline"
        >
          View audit log →
        </Link>
      </div>
      <div className="mt-6">
        <ThesisBody
          thesis={thesis}
          citations={citations}
          onRetryCitations={retryCitations}
        />
      </div>
    </main>
  );
}

function ThesisBody({
  thesis,
  citations,
  onRetryCitations,
}: {
  thesis: ThesisGetResponse;
  citations: CitationsState;
  onRetryCitations: () => void;
}) {
  if (thesis.status === "failed") {
    return (
      <ErrorBanner
        title="Thesis run failed"
        detail={
          thesis.error ??
          "The orchestrator did not produce a dossier. See the audit log for details."
        }
      />
    );
  }
  if (thesis.status === "cancelled") {
    return (
      <ErrorBanner
        title="Thesis run cancelled"
        detail={thesis.error ?? "This thesis was cancelled before it finished."}
      />
    );
  }
  if (thesis.status === "completed") {
    if (!thesis.dossier) {
      // Terminal but no dossier — synthesizer didn't produce output. Don't
      // spin forever; tell the user to check the audit log.
      return (
        <ErrorBanner
          title="Thesis completed without a dossier"
          detail={
            thesis.error ??
            "The orchestrator finished but the synthesizer did not produce a dossier. Check the audit log for the failing step."
          }
        />
      );
    }
    return (
      <div className="space-y-4">
        {citations.kind === "failed" ? (
          <CitationsDegradedBanner
            message={citations.message}
            onRetry={onRetryCitations}
          />
        ) : null}
        {citations.kind === "loading" ? (
          <Loading label="Loading citations…" />
        ) : null}
        <ThesisViewer
          ticker={thesis.ticker}
          focusQuestion={thesis.focus_question}
          dossier={thesis.dossier}
          citations={citations.kind === "loaded" ? citations.items : []}
        />
      </div>
    );
  }
  // pending / running
  return (
    <>
      <Loading label={`Status: ${thesis.status}…`} />
      <p className="mt-3 text-xs text-neutral-500">
        Auto-refreshes every {Math.round(POLL_INTERVAL_MS / 1000)}s.
      </p>
    </>
  );
}

function CitationsDegradedBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div
      role="alert"
      className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
    >
      <p className="font-medium">Citations unavailable</p>
      <p className="mt-1 text-amber-700">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-2 inline-flex rounded-md border border-amber-300 bg-white px-2.5 py-1 text-xs font-medium text-amber-800 hover:bg-amber-100"
      >
        Retry citations
      </button>
    </div>
  );
}

function StatusStrip({ thesis }: { thesis: ThesisGetResponse }) {
  const colour =
    thesis.status === "completed"
      ? "bg-emerald-50 text-emerald-800"
      : thesis.status === "failed" || thesis.status === "cancelled"
        ? "bg-rose-50 text-rose-800"
        : "bg-amber-50 text-amber-800";
  return (
    <div
      className={`flex items-center justify-between rounded-md px-3 py-2 text-sm ${colour}`}
    >
      <div>
        <span className="font-semibold uppercase tracking-wide">
          {thesis.ticker}
        </span>
        <span className="ml-3 capitalize">{thesis.status}</span>
      </div>
      <div className="text-xs">
        Created {new Date(thesis.created_at).toLocaleString()}
      </div>
    </div>
  );
}
