---
description: Run the Mercari data-source spike and fill in the findings report
allowed-tools: Read, Write, Edit, Bash
model: sonnet
---

Read `CLAUDE.md` section 2 and `docs/SPIKE.md`.

This is the gate before any production code exists. Write a single throwaway
script `spike/probe_mercari.py`. It is exempt from the layered architecture but
**not** from the no-comment rule and not from the guardrails.

The script must:
1. Generate an RFC 9449 DPoP proof JWT signed with a freshly generated ECDSA
   P-256 key for the Mercari search endpoint.
2. Search a keyword, newest-first, on-sale only, page size 30.
3. Print item id, title, price, created timestamp, url and thumbnail per result.
4. Assert the created timestamps are genuinely descending and report whether the
   ordering is chronological rather than recommendation-based.
5. Fetch one item detail and report how many distinct photo urls exist.
6. Estimate the new-listing rate per day for the keyword from the spread of
   created timestamps across the first page.
7. Run N cycles at a configurable gap, recording status code, latency and errors,
   then print success rate, p50, p95 and an error breakdown.

CLI arguments: `--keyword`, `--cycles`, `--gap-seconds`. No retries, no backoff:
raw failure behaviour must be visible.

Run it locally, then tell the human to run the identical script from the Japanese
VPS, and to paste both outputs back. Fill in
`docs/SPIKE.md` only once all three columns exist.
