"use client";

import { useMemo } from "react";

import type {
  ChunkSnippet,
  CitationListItem,
  CitedStatement,
  FinalDossier,
  ResearchStance,
} from "@/lib/types";

import { CitationPopover } from "./citation-popover";

type Props = {
  ticker: string;
  focusQuestion: string | null;
  dossier: FinalDossier;
  citations: CitationListItem[];
};

const STANCE_STYLES: Record<ResearchStance, string> = {
  positive: "bg-emerald-100 text-emerald-800 ring-emerald-200",
  neutral: "bg-neutral-100 text-neutral-700 ring-neutral-200",
  negative: "bg-rose-100 text-rose-800 ring-rose-200",
};

export function ThesisViewer({
  ticker,
  focusQuestion,
  dossier,
  citations,
}: Props) {
  const chunkIndex = useMemo(() => {
    const m = new Map<string, ChunkSnippet>();
    for (const c of citations) {
      for (const s of c.supporting_chunks) {
        m.set(s.chunk_id, s);
      }
    }
    return m;
  }, [citations]);

  return (
    <article className="space-y-10">
      <header className="space-y-3">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="text-3xl font-semibold tracking-tight">{ticker}</h1>
          <StanceBadge
            stance={dossier.research_stance}
            evidenceStrength={dossier.evidence_strength}
          />
        </div>
        {focusQuestion ? (
          <p className="text-sm text-neutral-500">
            Focus question: <span className="text-neutral-700">{focusQuestion}</span>
          </p>
        ) : null}
        <ProseSection
          heading="Executive summary"
          text={dossier.executive_summary}
          chunkIds={dossier.executive_summary_cited_chunk_ids}
          chunkIndex={chunkIndex}
        />
      </header>

      <CitedListSection
        heading="Bull case"
        items={dossier.bull_case}
        chunkIndex={chunkIndex}
        empty="No bull-case statements were cited."
      />
      <CitedListSection
        heading="Bear case"
        items={dossier.bear_case}
        chunkIndex={chunkIndex}
        empty="No bear-case statements were cited."
      />
      <CitedListSection
        heading="Catalysts"
        items={dossier.catalysts}
        chunkIndex={chunkIndex}
        empty="No catalysts identified."
      />
      <CitedListSection
        heading="Key risks"
        items={dossier.key_risks}
        chunkIndex={chunkIndex}
        empty="No risks identified."
      />
      <CitedListSection
        heading="Disconfirming evidence"
        items={dossier.disconfirming_evidence}
        chunkIndex={chunkIndex}
        empty="None found in the cited chunks."
      />

      {dossier.macro_context ? (
        <ProseSection
          heading="Macro context"
          text={dossier.macro_context}
          chunkIds={dossier.macro_context_cited_chunk_ids}
          chunkIndex={chunkIndex}
        />
      ) : null}

      {dossier.valuation_summary ? (
        <ProseSection
          heading="Valuation"
          text={dossier.valuation_summary}
          chunkIds={dossier.valuation_summary_cited_chunk_ids}
          chunkIndex={chunkIndex}
        />
      ) : null}

      {dossier.quant_summary ? (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Quant snapshot</h2>
          <p className="text-sm leading-6 text-neutral-700">
            {dossier.quant_summary}
          </p>
        </section>
      ) : null}

      {dossier.limitations.length > 0 ? (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Limitations</h2>
          <ul className="list-disc space-y-1 pl-5 text-sm text-neutral-700">
            {dossier.limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <footer className="rounded-md bg-neutral-50 p-4 text-xs text-neutral-500">
        {dossier.analyst_disclaimer}
      </footer>
    </article>
  );
}

function StanceBadge({
  stance,
  evidenceStrength,
}: {
  stance: ResearchStance;
  evidenceStrength: number;
}) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-0.5 text-xs font-medium ring-1 ${STANCE_STYLES[stance]}`}
    >
      <span className="capitalize">{stance}</span>
      <span className="text-[10px] text-neutral-600">
        evidence {Math.round(evidenceStrength * 100)}%
      </span>
    </span>
  );
}

function ProseSection({
  heading,
  text,
  chunkIds,
  chunkIndex,
}: {
  heading: string;
  text: string;
  chunkIds: string[];
  chunkIndex: Map<string, ChunkSnippet>;
}) {
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold">{heading}</h2>
      <p className="text-sm leading-6 text-neutral-700">
        {text}
        {chunkIds.length > 0 ? (
          <CitationPopover
            index={1}
            chunkIds={chunkIds}
            chunkIndex={chunkIndex}
          />
        ) : null}
      </p>
    </section>
  );
}

function CitedListSection({
  heading,
  items,
  chunkIndex,
  empty,
}: {
  heading: string;
  items: CitedStatement[];
  chunkIndex: Map<string, ChunkSnippet>;
  empty: string;
}) {
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold">{heading}</h2>
      {items.length === 0 ? (
        <p className="text-sm text-neutral-500">{empty}</p>
      ) : (
        <ul className="space-y-2 text-sm leading-6 text-neutral-700">
          {items.map((item, i) => (
            <li key={i} className="flex items-baseline gap-1">
              <span className="text-neutral-400">•</span>
              <span>
                {item.statement}
                {item.cited_chunk_ids.length > 0 ? (
                  <CitationPopover
                    index={i + 1}
                    chunkIds={item.cited_chunk_ids}
                    chunkIndex={chunkIndex}
                  />
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
