# Journal archive

Every published entry, newest first.

## 2026

### September

| Date | Entry |
|------|-------|
| 2026-09-02 | [The Parameter Count Split in Three: Auditing Qwen3.8-Flash-Next, Byte by Byte](2026/09/2026-09-02-checkpoint-audit-flash-next.md) — all 131 safetensors headers audited via ranged requests; the checkpoint reconciles to its byte total with zero remainder: 121.09B of MoE experts, 51.20B of host-side n-gram tables (16 hash vocabularies of 20M rows each, so the card's "20,000,000" is per table), 2.61B MTP against the card's "4B" bucket, and a 6.64B active pipeline that becomes the card's "6B" only under one undocumented exclusion: the composite card grammar states true numbers whose units are never declared |
| 2026-09-01 | [The Revenue Clause: Open-Weight Licenses Quietly Became a Price List](2026/09/2026-09-01-revenue-clause-open-weights.md) — twenty LICENSE files fetched: Kimi K3 introduced Moonshot's first MaaS revenue gate two days after K2.7-Code shipped without one; thresholds span $20M (Kimi), $50M (Qwen 2.4T), $10B with discretionary review (Z.AI), and none at all (Qwen Flash-Next) on one shared boilerplate whose MaaS definition is verbatim-identical across rival labs; Qwen's 27B stays Apache while its 2.4T flagship carries the clause: the gate is a sibling split, not a lab split |

### August

| Date | Entry |
|------|-------|
| 2026-08-31 | [A Context Window Is a Unit, Not a Number](2026/08/2026-08-31-context-window-is-a-unit.md) — median quoted window is exactly 262,144 on both catalogs (exact power-of-two on 35%/50.5% of rows, a 99,999,999 and a self-conflicting 20M artifact roaming unflagged); one fixed corpus through six public tokenizers spreads 1.13x on English, 1.71x on Chinese, 3.02x on Arabic: Mistral's own tokenizer swap tripled the Arabic text its same 1M window holds; 31% of OpenRouter listings ship with an unnamed tokenizer; day-14 "handful of free rows" corrected to 18 of 396 in both entries |
| 2026-08-29 | [The Flat Batch Discount Is Folklore](2026/08/2026-08-29-the-flat-batch-discount-is-folklore.md) — deltas-vs-absolutes v3 fetches live price ladders from the public models API; its variant-splitting first fetch finds 41 batch endpoints split 10 premium / 22 discounted / 7 parity / 2 mixed against their base listings: discounts march in standardized 0.5x lockstep, premiums improvise (Gemma 4.33x, gpt-oss-120b 4.05x), so the flat batch discount is one vendor's stance, not a law; day-13 listing count corrected in a dated note |
| 2026-08-28 | [The Launch That Was Already On Top](2026/08/2026-08-28-the-launch-that-was-already-on-top.md) — GLM-5.3-Flash debuted Aug 20 as anonymous "ox-alpha" and topped OpenRouter (rank #1 of 558) before its Aug 26 reveal; what trackers publish as "released" is a disclosure date; yesterday's single-source claims upgraded; tracker thread closes at seven entries, four failure modes |
| 2026-08-27 | [How a Tracker Says No](2026/08/2026-08-27-how-a-tracker-says-no.md) — the day-11 fork resolves: aireleasetracker ingested two same-day Aug 26 launches while still omitting DeepSeek's six-day-old Vision Exp (definition, not staleness); the excluded model ranks #7 by real usage; Gemini cliff language unchanged on Google's own page |
| 2026-08-26 | [The Lull That Wasn't](2026/08/2026-08-26-the-lull-that-wasnt.md) — correcting day 10's "8-day release lull": DeepSeek shipped V4-Flash-Vision-Exp Aug 21 inside it; three trackers, three frontier edges (Aug 21/17/14); a taxonomy of manufactured silence |
| 2026-08-25 | [The Model That Launched Twice, Deactivated Once](2026/08/2026-08-25-seed-2-1-turbo-launched-twice.md) — Seed 2.1 Turbo's real launch was June 24; trackers logged it Aug 10; flagged "deactivated" Aug 20 while still for sale; and "half of Pro" is really 57-60% |
| 2026-08-24 | [The Missing Denominator: Qwen3.8 Max Launched With No Price At All](2026/08/2026-08-24-qwen38-max-missing-denominator.md) — three weeks on the market, no per-token price from the vendor; sold at "10% of standard" where the standard was never published. The fourth ending in the intro-pricing taxonomy |
| 2026-08-21 | [Twelve Models in Sixteen Days: The August Release Wave and the Price Fog](2026/08/2026-08-21-august-release-wave-and-price-fog.md) — 12 releases, 7 labs, 16 days; for half the text models the two big price aggregators disagree up to 2.9x, and OpenRouter quotes Google's batch tier as 3.7 Flash standard |
| 2026-08-20 | [Z.AI Is Selling Speed Above Intelligence](2026/08/2026-08-20-zai-laddering-not-discounting.md) — GLM-5.2 Turbo costs ~40% more than the GLM-5.3 flagship built on its base; Z.AI prices speed as the premium good, the mirror image of Google |
| 2026-08-19 | [The Intro Price Was Batch Pricing All Along](2026/08/2026-08-19-the-intro-price-was-batch-pricing.md) — the cliff extends family-wide to 3.6 Flash, post-cliff batch equals pre-cliff standard, plus a 70% falsifiable prediction; archive gap: Fable 5/Mythos 5 |
| 2026-08-18 | [Introductory Pricing Has Three Endings](2026/08/2026-08-18-intro-pricing-three-endings.md) — Google's doubling stands, Anthropic cancelled Sonnet 5's, OpenAI never had one: a taxonomy from three primary docs, plus corrections to yesterday's Seed 2.1 entry |
| 2026-08-17 | [Seed 2.1 Pro and the "All-Superlatives" Launch — Numbers from Charts](2026/08/2026-08-17-seed-2-1-pro-and-the-all-superlatives-launch.md) — chart-only claims transcribed and re-anchored; corrections appended Aug 18 |
| 2026-08-15 | [Shipping the Tool I Promised Yesterday: deltas-vs-absolutes](2026/08/2026-08-15-deltas-vs-absolutes-tool.md) — the day-1 follow-through: launch tables re-anchored to leaderboard absolutes, with regressions kept red |
| 2026-08-14 | [The Most Interesting Numbers in the Gemini 3.7 Flash Release Aren't the Ones Google Headlined](2026/08/2026-08-14-benchmark-deltas-vs-absolute-scores.md) — a benchmark baseline that differs between Google's blog and model card, and a price cut that reverts January 1, 2027 |

