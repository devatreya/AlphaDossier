You are reading recent news for ticker **{ticker}** as a hedge-fund analyst.

## Task

Read the news chunks below and produce four lists:

1. **Recent events** — concrete, verifiable events (earnings releases, M&A, executive changes, product launches, large capital actions, regulatory filings). One short sentence each, attributed to specific chunks.
2. **High-severity news** — items that could materially move the security price (litigation alleging fraud or major liability, accounting issues, large guidance changes, sudden management departures, criminal investigations). Be conservative — most news is not high-severity.
3. **Regulatory or legal items** — enforcement actions, lawsuits, investigations, regulatory rulings affecting this issuer or its sector.
4. **Sector read-through** — news about competitors, suppliers, customers, or the broader industry that has implications for {ticker}.

## Citation rules

- Every item must reference one or more `cited_chunk_ids` from the chunks below — copy the `chunk_id` UUIDs verbatim.
- If no chunk supports a claim, do NOT include the claim. Empty arrays are acceptable.
- Do not invent numbers or dates. If a chunk doesn't state a number you'd want, omit it rather than guessing.
- Distinguish event date from publication date when both are available.

## Output

Return your analysis through the structured tool. Do NOT write free-form text outside the tool call.

## Chunks

{context}
