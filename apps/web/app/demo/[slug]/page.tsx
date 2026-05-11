import Link from "next/link";
import { notFound } from "next/navigation";

import { ThesisViewer } from "@/components/thesis-viewer";
import { DEMOS, getDemo } from "@/lib/demos";

export function generateStaticParams() {
  return DEMOS.map((d) => ({ slug: d.slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }) {
  const d = getDemo(params.slug);
  return {
    title: d ? `${d.ticker} demo — AI-quant` : "Demo not found",
  };
}

type PageProps = { params: { slug: string } };

export default function DemoDossierPage({ params }: PageProps) {
  const demo = getDemo(params.slug);
  if (!demo) {
    notFound();
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <div className="mb-4 flex items-center justify-between">
        <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-medium uppercase tracking-wide text-blue-800">
          Demo
        </span>
        <Link
          href={"/demo" as never}
          className="text-sm text-neutral-600 hover:text-neutral-900 hover:underline"
        >
          ← All demos
        </Link>
      </div>
      <ThesisViewer
        ticker={demo.ticker}
        focusQuestion={null}
        dossier={demo.dossier}
        citations={demo.citations}
      />
    </main>
  );
}
