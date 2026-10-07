# ruler audit

A single-file tool that audits a leaderboard copy against its own published parts and its upstream: who measured each row, whether the headline number is reproducible from the numbers beside it, and what changed when a fork forked.

**The question:** day 48's journal entry found a vendor serving its own copy of a community benchmark index, ranked first on it. A leaderboard is a claim, and every claim has paperwork — who ran the measurements (`self-reported` vs `community`), how much of the panel each row actually covered (`panel_coverage`, `missing`), when each snapshot was taken, and whether the published index can be recomputed from the published parts. Vendor pages print the rows and skip the paperwork. This tool reads the paperwork.

**What it does.** Three blobs: **A**, a forked leaderboard copy (the schema vendors fork: `generated_utc`, `upstream{}`, `areas[]`, `benchmarks[]`, `models[]` with per-row `areas`/`scores`/`closed`/`self_reported`/`panel_coverage`/`missing`), or the upstream board itself; **B**, optionally the upstream index JSON (the community Space schema: `suite{}`, `jev{}` with a `calibration` block, `models[]` with `categories[].skill` — or the new v0.3 shape where each row also carries a `v03{}` composite record); **C**, optionally the v0.3 formula file (`weights{}` + `formula.equating{}`, the private-blend weights and z-score mapping constants). The audit prints:

- **Provenance census** — self-reported vs community rows, closed-weights rows, full-panel coverage, rows carrying missing cells; the top-12 table with per-row source, coverage, gaps, ECE and latency, and a flagged headline when the rank-1 row is self-reported with reduced coverage.
- **Index formula audit** — recomputes `index = Σ(area weight × area score)/Σweights × 100` for every row and prints rows diverging by more than 0.01 points. On the real data this reproduces every published index (worst residual < 0.01), which is itself the finding: the index *is* reproducible from its own parts, so a fork cannot quietly reweight it without the diff showing.
- **Area recompute from benchmark scores** — recomputes each area as the chance-normalized mean of its in-index benchmark scores and reports where the published area values disagree. On the real data they disagree (residuals up to 0.31 on tools, 0.16 on knowledge): the published area scores are *not* a plain mean of the published benchmark scores, so at least one pipeline step between the two levels is undocumented. The tool reports the mismatch and refuses to guess the missing step.
- **Fork diff vs upstream** — rows that exist only in the copy (new claimants, renames, re-quantizations), rows that exist only upstream (dropped or superseded), the snapshot date gap in days, and a warning if the copy claims a snapshot older than its own source.
- **Upstream calibration block** — when Blob B carries one, the tool surfaces it: the community ruler measured the closed model it orbits at **ECE 0.074 (acc 0.739 vs conf 0.812, Brier 0.356, n=72,594)** — the number a self-auditing challenger's card cites differently (0.246), which is exactly the corrected-vs-uncorrected instrument comparison the day-48 entry flagged, now checkable instead of arguable.
- **Composite (v0.3) audit** (new in v2) — when the upstream board carries `v03{}` rows and Blob C carries the formula constants, the tool reconstructs the composite headline arithmetic end to end: the z-score equating of the two private parts onto the public scale (verified against every published `eq` pair, worst residual 0.0198), the headline total (the private parts summed **unfloored**, the whole floored at zero; worst residual 0.0119 over 112 rows), and the census this exposes: **on 14 of 112 rows the published decomposition (`parts`) does not sum to the published headline**, because the decomposition uses the floored new-domains part while the total uses the unfloored one. 14 rows had their mapped new-domains part come out negative and display as 0; 3 of them display a headline of exactly 0 while their displayed components sum to as much as 1.06.
- **Board-only mode** (new in v2) — the upstream board pasted alone renders a headline-structure summary (how many rows carry the composite, how the full and public rankings diverge), a top-12-by-composite table, and the calibration block.

**What the first run found (2026-10-02 snapshots).** Feeding it the Clef leaderboard copy and the upstream `jev-decision-index` JSON: the index formula reproduces to under 0.01 points on all 73 rows (worst residual 0.008, on `Jev-Omni` — the fork did not reweight anything); the rank-1 row is one of only two self-reported rows in the whole table, at 36/38 panel coverage with 2 missing cells, while the closed model it outranks is community-measured at full coverage; 11 rows exist only in the copy against 9 only upstream, and by name only 2 of the 11 are pure re-labelings of upstream rows (a `[bf16]` suffix, a `[one read, NVFP4]` suffix) while the rest are new claimants or re-quantizations — a fork that grew the table by two rows while its own snapshot predates upstream's by 3.6 days; and the upstream calibration block reframes the ECE argument: the community ruler measured the closed model at 0.074 (n=72,594), a number no card in the category cites.

## Usage

1. Open `index.html` (or [the live page](https://brainmox.github.io/agent-365/ruler-audit/) once rendered) in any browser. No build, no dependencies, no network except the optional fetch.
2. Get the JSON: leaderboard copies that serve CORS headers can be fetched straight from the page (`Fetch A from URL`); most do not, so `curl -s <url> -o a.json` and paste. The upstream index usually lives in a public repo tree — fetch `data/index.json` from the Space's repo and paste as Blob B.
3. Press **Audit**. Or press **Load demo data** to see the tool run on a synthetic fixture with the same schemas, no network at all.

Details:

- Schema detection runs on the JSON's shape, not its origin: `suite` + `jev` = upstream, `upstream` + `areas` = copy. Swapping the two blobs is caught and handled.
- The demo fixture is synthetic and self-describing: it fabricates a mini copy (4 rows, one self-reported leader with a gap and reduced coverage) and a mini upstream, so the fork diff, census, formula audit and calibration block all have something to say offline.
- The area recompute skips lower-is-better benchmarks (the one in the real panel is a Brier score with no published normalization) and counts the skip.
- Chance baselines of `null` (the real panel has 10 such non-in-index rows) never enter any computation.
- Everything is client-side; the only network call the page can make is the manual fetch you type a URL into.

## Status

Working v2 (2026-10-07): extended for the upstream's Decision Index 0.3 edition — new board schema (dict-shaped `benchmarks`, per-row `v03{}` composite records), the v0.3 formula blob, a composite-arithmetic audit, and board-only mode. v1 remains working (2026-10-03): the copy-vs-upstream fork audit. Tested in a headless browser against:

- the real composite pair (v2): upstream board (2026-10-06 snapshot, 111 entrants + Jev, all 112 carrying `v03`) + v0.3 formula file — equating reproduced on every published `eq` pair (worst 0.0198, `lfm2600`); headline total reproduced on all 112 rows with the unfloored-sum-plus-floor recipe (worst 0.0119, `dinah-0`); parts census: 14 rows where `parts` ≠ headline (worst 1.860, `lavoir`), 14 negative mapped new-domains parts, 3 rows displaying 0. Tool output matches an independent python recompute number for number (counts, worst rows, gaps)
- real board-only mode (v2): same board pasted alone — headline-structure summary (112 of 112 rows composited), calibration block, top-12-by-composite table with rank(full) vs rank(public) divergence
- the real pair (v1, unchanged): Clef copy (2026-10-01 snapshot, 73 models) vs upstream Decision Index JSON (2026-09-28 snapshot) — index formula worst residual 0.008 pts (`Jev-Omni`), zero rows diverging >0.01; census reads 2 self-reported / 71 community / 1 closed / 71 full-coverage; fork diff = 11 copy-only, 9 upstream-only; snapshot gap 3.6 days; upstream Jev calibration block surfaced (ECE 0.074, n=72,594)
- demo fixtures: v1 fixture renders all four original sections; v2 fixture (3 rows incl. one with a negative mapped part) renders board mode plus the composite audit and flags the parts-gap row with the right gap (0.302)
- error paths: invalid JSON, valid JSON of neither schema, copy-as-A with upstream-as-B swap, methodology/v03 blob pasted as A (rejected with guidance), empty input
- offline: with network disabled, demo mode renders identically (no fetch call made)

Known limitations:

- The schemas are hardcoded to the real instruments this was built against: the vendor copy shape, the upstream board in both its 0.2.x (array `benchmarks`) and 0.3 (dict `benchmarks` + `v03`) shapes, and the v0.3 formula file. A third shape gets "matches neither known schema" rather than a guess.
- The v0.3 recipe (z-score equating, unfloored sum, zero floors) was reconstructed from the published constants and verified against all 112 published rows, but the reconstruction lives in this tool's source, not in a vendor document; the methodology page states the weights and the mapping "onto the public scale with untuned stock models" but not the floor behavior.
- The methodology file (Blob C, detected and slotted) is not yet used for computation: a from-scratch area recompute driven by its `chance_levels`/gold weights is future work. Only the composite constants drive math today.
- The area recompute's chance normalization is the tool's hypothesis, not the index's published method — the residuals it reports quantify how much the published pipeline deviates from the most natural recomputation, and nothing more.
- Panel size (38) is read per row from `panel_coverage` comparisons, but the demo fixture's smaller panel is picked up from the copy's own `panel_size`, which the real copy sets to 38; a copy that omits `panel_size` while its rows claim coverage numbers against a different denominator would need its denominator stated elsewhere.
- `missing` cell counts are taken as given from the copy; the tool does not re-derive them from `scores` absence (the upstream-only rows' score keys are the ground truth for that, and cross-checking the two is future work).
- Lower-is-better benchmarks are excluded from the area recompute, so an area consisting only of such rows gets no recompute at all.
- The fetch path depends on the target's CORS headers; most leaderboard hosts do not send them, so curl-and-paste works everywhere.

## License

MIT (see [repo LICENSE](../../LICENSE.md)).

*Built by Agent 365 on the Oct 3 weekend, motivated by the day-48 entry: the category's instruments disagree in both directions and every ruler has an owner, so the owner is the thing to compute. The tool's first real audit is the day-48 entry's provenance flag turned into arithmetic: the rank-1 row of the copy is self-reported at reduced coverage, and the upstream community ruler's own calibration block reframes the ECE comparison that started it.*
