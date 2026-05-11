import Link from "next/link";

import { getApiReadiness } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const readiness = await getApiReadiness().catch(() => null);

  const headerColor =
    readiness?.status === "ok"
      ? "text-emerald-700"
      : readiness?.status === "degraded"
        ? "text-amber-700"
        : "text-red-600";

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-4xl font-semibold tracking-tight">AI-quant</h1>
      <p className="mt-3 text-lg text-neutral-600">
        Cited AI research dossiers for public-market investors.
      </p>

      <div className="mt-6 flex items-center gap-3">
        <Link
          href="/thesis/new"
          className="inline-flex items-center rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-neutral-700"
        >
          Start a new thesis →
        </Link>
        <Link
          href={"/demo" as never}
          className="inline-flex items-center rounded-md border border-neutral-300 bg-white px-4 py-2 text-sm font-medium text-neutral-800 shadow-sm hover:bg-neutral-50"
        >
          See a demo
        </Link>
      </div>

      <section className="mt-10 rounded-xl border border-neutral-200 bg-white p-6 shadow-sm">
        <h2 className="text-sm font-medium uppercase tracking-wide text-neutral-500">
          API readiness
        </h2>
        {readiness ? (
          <>
            <p className={`mt-2 text-sm font-medium ${headerColor}`}>
              {readiness.status} (db: {readiness.db})
            </p>
            <pre className="mt-3 overflow-x-auto rounded-md bg-neutral-50 p-4 text-sm">
              {JSON.stringify(readiness, null, 2)}
            </pre>
          </>
        ) : (
          <p className="mt-3 text-sm text-red-600">
            Backend unreachable. Start it with{" "}
            <code className="rounded bg-neutral-100 px-1">
              uvicorn services.api.main:app --reload --port 8000
            </code>{" "}
            from the repo root.
          </p>
        )}
      </section>

      <p className="mt-10 text-xs text-neutral-500">
        Research prototype. Output requires analyst review before any investment
        action.
      </p>
    </main>
  );
}
