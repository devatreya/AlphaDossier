"use client";

import { useEffect, useRef, useState } from "react";

import type { ChunkSnippet } from "@/lib/types";

type Props = {
  index: number;
  chunkIds: string[];
  chunkIndex: Map<string, ChunkSnippet>;
};

/** Inline citation marker. Click opens a popover listing the supporting chunks
 * with provider, title, and a short excerpt. ESC or click-outside closes. */
export function CitationPopover({ index, chunkIds, chunkIndex }: Props) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (
        containerRef.current &&
        e.target instanceof Node &&
        !containerRef.current.contains(e.target)
      ) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const snippets = chunkIds
    .map((id) => chunkIndex.get(id))
    .filter((s): s is ChunkSnippet => Boolean(s));

  return (
    <span ref={containerRef} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="ml-1 inline-flex items-center rounded-full border border-neutral-300 bg-white px-1.5 py-0 text-[10px] font-medium leading-4 text-neutral-700 hover:bg-neutral-100"
      >
        [{index}]
      </button>
      {open ? (
        <div
          role="dialog"
          className="absolute left-0 z-20 mt-1 w-96 max-w-[90vw] rounded-md border border-neutral-200 bg-white p-3 text-xs shadow-lg"
        >
          <p className="mb-2 font-medium text-neutral-700">
            {snippets.length} supporting chunk{snippets.length === 1 ? "" : "s"}
          </p>
          <ul className="space-y-3">
            {snippets.length === 0 ? (
              <li className="text-neutral-500">
                No supporting chunks were resolved (the cited chunk may have
                been cleaned up). The citation is still recorded in the audit
                log.
              </li>
            ) : (
              snippets.map((s) => (
                <li
                  key={s.chunk_id}
                  className="border-l-2 border-neutral-200 pl-2"
                >
                  <p className="text-neutral-500">
                    {s.source_provider ?? "unknown provider"}
                    {s.source_kind ? ` · ${s.source_kind}` : null}
                  </p>
                  {s.source_title ? (
                    <p className="font-medium text-neutral-800">
                      {s.source_title}
                    </p>
                  ) : null}
                  <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap text-neutral-700">
                    {s.text.slice(0, 600)}
                    {s.text.length > 600 ? "…" : null}
                  </p>
                  {s.source_url ? (
                    <a
                      href={s.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1 inline-block text-blue-600 hover:underline"
                    >
                      open source ↗
                    </a>
                  ) : null}
                </li>
              ))
            )}
          </ul>
        </div>
      ) : null}
    </span>
  );
}
