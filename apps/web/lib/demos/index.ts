import type { CitationListItem, FinalDossier } from "@/lib/types";

import { nvdaCitations, nvdaDossier } from "./nvda";

export type Demo = {
  slug: string;
  ticker: string;
  region: "US" | "UK";
  blurb: string;
  dossier: FinalDossier;
  citations: CitationListItem[];
};

export const DEMOS: ReadonlyArray<Demo> = [
  {
    slug: "nvda",
    ticker: "NVDA",
    region: "US",
    blurb:
      "Reference dossier for a US large-cap semiconductor name. Demonstrates SEC-grounded bull/bear cases, hyperscaler-capex catalyst, and customer-concentration risk.",
    dossier: nvdaDossier,
    citations: nvdaCitations,
  },
];

export function getDemo(slug: string): Demo | null {
  return DEMOS.find((d) => d.slug === slug) ?? null;
}
