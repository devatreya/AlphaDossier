import type { CitationListItem, FinalDossier } from "@/lib/types";

// Stable fake UUIDs so the demo's citation_ids resolve through the popover.
const C = {
  Q3: "11111111-1111-1111-1111-000000000001",
  GUIDE: "11111111-1111-1111-1111-000000000002",
  CAPEX: "11111111-1111-1111-1111-000000000003",
  CONC: "11111111-1111-1111-1111-000000000004",
  REG: "11111111-1111-1111-1111-000000000005",
  MACRO: "11111111-1111-1111-1111-000000000006",
  VAL: "11111111-1111-1111-1111-000000000007",
};
const S = "22222222-2222-2222-2222-000000000001";

export const nvdaDossier: FinalDossier = {
  executive_summary:
    "NVIDIA reported another beat-and-raise quarter, with data-center revenue continuing to outpace expectations on hyperscaler AI-compute demand. Management raised full-year guidance, citing strong order visibility into the next product cycle. Customer concentration with the top three hyperscalers remains the most material risk; export-control rules continue to add execution complexity. The cited evidence supports a positive stance with elevated confidence; the main risks are well-flagged in the disclosures rather than hidden.",
  executive_summary_cited_chunk_ids: [C.Q3, C.GUIDE],
  research_stance: "positive",
  evidence_strength: 0.74,
  bull_case: [
    {
      statement:
        "Data-center revenue grew triple-digits year-on-year, well ahead of consensus.",
      cited_chunk_ids: [C.Q3],
    },
    {
      statement:
        "Management raised full-year revenue and gross-margin guidance, citing strong visibility into the next product cycle.",
      cited_chunk_ids: [C.GUIDE],
    },
    {
      statement:
        "Hyperscaler capex commentary supports continued AI-compute demand into the next 12 months.",
      cited_chunk_ids: [C.CAPEX],
    },
  ],
  bear_case: [
    {
      statement:
        "Top-three customer concentration represents over 40% of data-center revenue.",
      cited_chunk_ids: [C.CONC],
    },
    {
      statement:
        "US export-control rules continue to constrain China data-center revenue and may tighten further.",
      cited_chunk_ids: [C.REG],
    },
  ],
  catalysts: [
    {
      statement:
        "Next-generation product launch announced for the upcoming GTC keynote, with early customer commitments disclosed.",
      cited_chunk_ids: [C.GUIDE],
    },
    {
      statement: "Q4 print is the next read on hyperscaler order durability.",
      cited_chunk_ids: [C.CAPEX],
    },
  ],
  key_risks: [
    {
      statement:
        "Customer concentration with three hyperscalers is the dominant idiosyncratic risk.",
      cited_chunk_ids: [C.CONC],
    },
    {
      statement:
        "Export-control overhang on China revenue introduces a regulatory wildcard.",
      cited_chunk_ids: [C.REG],
    },
  ],
  disconfirming_evidence: [
    {
      statement:
        "Some hyperscaler commentary suggests AI-capex pacing may slow in late 2026 — a watchpoint, not a rebuttal.",
      cited_chunk_ids: [C.CAPEX],
    },
  ],
  macro_context:
    "Late-cycle US backdrop with elevated real rates; AI-compute spending has so far decoupled from broader capex cyclicality, but a sustained Fed pause or rate-cut delay could compress hyperscaler buyback budgets, indirectly tightening capex.",
  macro_context_cited_chunk_ids: [C.MACRO],
  valuation_summary:
    "Trades at a premium to large-cap semis on EV/sales, justified by data-center growth durability if the cited capex visibility is real. Note: this MVP does not have access to consensus estimates.",
  valuation_summary_cited_chunk_ids: [C.VAL],
  quant_summary:
    "540 daily bars; ann. vol ~50%; max drawdown -28% in the cited window; 1y return materially above SPY benchmark.",
  limitations: [
    "Consensus estimates not available in this MVP; valuation is descriptive, not comparative.",
    "China exposure is reported in aggregate; segment-level transparency is limited.",
    "FCA NSM coverage unavailable for this US issuer (not applicable).",
  ],
  analyst_disclaimer:
    "This dossier is research-prototype output and is not investment advice. Verify all claims against primary sources before acting on it.",
  notes: null,
};

export const nvdaCitations: CitationListItem[] = [
  {
    id: "33333333-3333-3333-3333-000000000001",
    section: "bull_case",
    claim:
      "Data-center revenue grew triple-digits year-on-year, well ahead of consensus.",
    chunk_ids: [C.Q3],
    confidence: 0.82,
    supporting_chunks: [
      {
        chunk_id: C.Q3,
        source_id: S,
        source_kind: "sec_8k",
        source_provider: "sec_edgar",
        source_url: "https://example/8k",
        source_title: "8-K Q3 earnings release",
        text:
          "Data-center segment revenue rose 154% year-on-year to a record $XX.X billion, beating the high end of the prior guidance range.",
      },
    ],
    created_at: "2026-05-09T09:30:00Z",
  },
  {
    id: "33333333-3333-3333-3333-000000000002",
    section: "bull_case",
    claim:
      "Management raised full-year revenue and gross-margin guidance, citing strong visibility into the next product cycle.",
    chunk_ids: [C.GUIDE],
    confidence: 0.79,
    supporting_chunks: [
      {
        chunk_id: C.GUIDE,
        source_id: S,
        source_kind: "sec_8k",
        source_provider: "sec_edgar",
        source_url: "https://example/8k",
        source_title: "8-K Q3 earnings release",
        text:
          "We are raising full-year revenue guidance to $XXX–$XXX billion and tightening gross-margin guidance to the upper half of the prior range, reflecting strong order book and product-cycle commitments.",
      },
    ],
    created_at: "2026-05-09T09:30:00Z",
  },
  {
    id: "33333333-3333-3333-3333-000000000003",
    section: "bull_case",
    claim:
      "Hyperscaler capex commentary supports continued AI-compute demand into the next 12 months.",
    chunk_ids: [C.CAPEX],
    confidence: 0.66,
    supporting_chunks: [
      {
        chunk_id: C.CAPEX,
        source_id: S,
        source_kind: "news",
        source_provider: "news_api",
        source_url: "https://example/capex-news",
        source_title: "Hyperscaler capex tracker",
        text:
          "The four largest US cloud platforms collectively guided 2026 capex up double-digits versus 2025, with AI-infrastructure cited as the dominant line item.",
      },
    ],
    created_at: "2026-05-09T09:30:00Z",
  },
  {
    id: "33333333-3333-3333-3333-000000000004",
    section: "key_risks",
    claim:
      "Top-three customer concentration represents over 40% of data-center revenue.",
    chunk_ids: [C.CONC],
    confidence: 0.91,
    supporting_chunks: [
      {
        chunk_id: C.CONC,
        source_id: S,
        source_kind: "sec_10k",
        source_provider: "sec_edgar",
        source_url: "https://example/10k",
        source_title: "10-K risk factors",
        text:
          "Customer concentration: three customers individually accounted for more than 10% of revenue; collectively, our top three customers comprised approximately 41% of fiscal-year revenue.",
      },
    ],
    created_at: "2026-05-09T09:30:00Z",
  },
  {
    id: "33333333-3333-3333-3333-000000000005",
    section: "key_risks",
    claim:
      "US export-control rules continue to constrain China data-center revenue and may tighten further.",
    chunk_ids: [C.REG],
    confidence: 0.71,
    supporting_chunks: [
      {
        chunk_id: C.REG,
        source_id: S,
        source_kind: "sec_10q",
        source_provider: "sec_edgar",
        source_url: "https://example/10q",
        source_title: "10-Q export-control disclosure",
        text:
          "US export controls applicable to advanced data-center accelerators continued to limit shipments to certain customers in China during the quarter, and any further tightening could further constrain such revenue.",
      },
    ],
    created_at: "2026-05-09T09:30:00Z",
  },
  {
    id: "33333333-3333-3333-3333-000000000006",
    section: "macro_context",
    claim:
      "Late-cycle US backdrop with elevated real rates; AI-compute spending has so far decoupled from broader capex cyclicality.",
    chunk_ids: [C.MACRO],
    confidence: 0.62,
    supporting_chunks: [
      {
        chunk_id: C.MACRO,
        source_id: S,
        source_kind: "news",
        source_provider: "news_api",
        source_url: "https://example/macro-news",
        source_title: "Macro overview",
        text:
          "US real yields remain elevated relative to the prior cycle, but AI-related capex has been the strongest line item across hyperscaler results.",
      },
    ],
    created_at: "2026-05-09T09:30:00Z",
  },
  {
    id: "33333333-3333-3333-3333-000000000007",
    section: "valuation_summary",
    claim:
      "Trades at a premium to large-cap semis on EV/sales, justified by data-center growth durability if the cited capex visibility is real.",
    chunk_ids: [C.VAL],
    confidence: 0.55,
    supporting_chunks: [
      {
        chunk_id: C.VAL,
        source_id: S,
        source_kind: "news",
        source_provider: "news_api",
        source_url: "https://example/valuation",
        source_title: "Sector multiples summary",
        text:
          "The largest data-center accelerator vendor trades at a meaningful EV/sales premium versus large-cap semiconductor peers, with the gap driven by data-center segment growth.",
      },
    ],
    created_at: "2026-05-09T09:30:00Z",
  },
];
