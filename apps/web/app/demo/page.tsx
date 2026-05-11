import Link from "next/link";

import { DEMOS } from "@/lib/demos";

export const metadata = {
  title: "Demo dossiers — AI-quant",
};

export default function DemoIndexPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-2xl font-semibold tracking-tight">Demo dossiers</h1>
      <p className="mt-2 text-sm text-neutral-600">
        Prebuilt research dossiers, served from static files. Useful for
        exploring the analyst experience without running the orchestrator
        against live APIs and a database.
      </p>

      <ul className="mt-8 space-y-4">
        {DEMOS.map((d) => (
          <li
            key={d.slug}
            className="rounded-md border border-neutral-200 bg-white p-4 shadow-sm"
          >
            <div className="flex items-baseline justify-between">
              <h2 className="text-lg font-semibold">{d.ticker}</h2>
              <span className="text-xs uppercase tracking-wide text-neutral-500">
                {d.region}
              </span>
            </div>
            <p className="mt-2 text-sm text-neutral-700">{d.blurb}</p>
            <div className="mt-3">
              <Link
                href={`/demo/${d.slug}` as never}
                className="text-sm font-medium text-blue-600 hover:underline"
              >
                Open dossier →
              </Link>
            </div>
          </li>
        ))}
      </ul>

      <p className="mt-10 text-xs text-neutral-500">
        Citations in demo dossiers reference synthetic chunk IDs. The underlying
        text snippets are illustrative, not the regulated source itself.
      </p>
    </main>
  );
}
