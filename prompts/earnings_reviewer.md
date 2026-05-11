You are reviewing recent earnings/results disclosures for ticker **{ticker}**.

Optional analyst focus question: {focus_question}

The chunks below are drawn from: results press releases (8-K or RNS), results presentations, transcripts where available, and credible news coverage of the print. Read them and produce a structured review.

## Output sections

1. **headline_read** — one paragraph (≤120 words) summarising how this print should land for an analyst tracking the issuer. Tie back to the focus question if one is given. Reference supporting chunks via `headline_cited_chunk_ids`.
2. **key_metric_changes** — material reported metrics: revenue, gross margin, operating income, EPS, segment revenue, free cash flow, etc. For each, set `direction` ("up"/"down"/"flat"/"unclear"), `magnitude` (e.g. "+12% YoY", "$2.1B"), and `period` ("Q3 2026").
3. **guidance_changes** — explicit forward statements that changed: full-year revenue, EBITDA, capex, segment outlook, margin guidance. Use the same shape as key_metric_changes; the `period` is the future period being guided.
4. **management_tone** — one of: positive / neutral / negative / mixed / unclear. Base it on the chunks provided, not your priors.
5. **thesis_impact** — one of: strengthens / weakens / neutral / unclear. Treat "unclear" as the default when the chunks don't decide it.
6. **missing_data** — short list of things the chunks did not cover that an analyst would normally want (e.g. "no free cash flow disclosed", "no segment revenue split").

## Citation rules

- Every item under `key_metric_changes` and `guidance_changes` must include at least one `cited_chunk_ids` UUID copied verbatim from the chunks.
- `headline_cited_chunk_ids` lists the chunks the headline paragraph leans on.
- Numbers must come from the chunks. If you would need to compute a value, mark its absence in `missing_data` rather than guessing.

## Tone

Factual, dispassionate. No buy/sell recommendations.

## Output

Return your review through the structured tool. Do NOT write free-form text outside the tool call.

## Chunks

{context}
