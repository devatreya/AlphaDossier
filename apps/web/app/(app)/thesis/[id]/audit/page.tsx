"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AuditSummary, AuditTable } from "@/components/audit-table";
import { ErrorBanner } from "@/components/error-banner";
import { Loading } from "@/components/loading";
import { ApiError, getAudit, isAbortError } from "@/lib/api";
import type { AuditEvent } from "@/lib/types";

type PageProps = { params: { id: string } };

export default function AuditPage({ params }: PageProps) {
  return <AuditPageInner key={params.id} thesisId={params.id} />;
}

function AuditPageInner({ thesisId }: { thesisId: string }) {
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    (async () => {
      try {
        const resp = await getAudit(thesisId, 500, {
          signal: controller.signal,
        });
        if (cancelled) return;
        setEvents(resp.events);
      } catch (e) {
        if (cancelled || isAbortError(e)) return;
        if (e instanceof ApiError && e.status === 404) {
          setError("Thesis not found.");
          return;
        }
        const message =
          e instanceof Error ? e.message : "Could not load audit log.";
        setError(message);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [thesisId]);

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <div className="mb-6 flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Audit log</h1>
          <p className="mt-1 text-sm text-neutral-500">
            Every connector call, agent run, and synthesizer invocation for
            this thesis.
          </p>
        </div>
        <Link
          href={`/thesis/${thesisId}` as never}
          className="text-sm text-neutral-600 hover:text-neutral-900 hover:underline"
        >
          ← Back to dossier
        </Link>
      </div>

      {error ? (
        <ErrorBanner title="Could not load audit log" detail={error} />
      ) : !events ? (
        <Loading label="Loading audit events…" />
      ) : (
        <div className="space-y-6">
          <AuditSummary events={events} />
          <AuditTable events={events} />
        </div>
      )}
    </main>
  );
}
