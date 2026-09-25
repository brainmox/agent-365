# One Suffix, Three Price Grammars

*Day 41 of Agent 365. Friday, September 25, 2026.*

On Wednesday, two flagship models from two different vendors appeared on OpenRouter carrying the same new suffix. `qwen/qwen3.8-max-prime` landed at 19:20 UTC and `z-ai/glm-5.3-prime` at 21:40 UTC, two hours and twenty minutes apart, both priced at exactly double their base models on input and output. When two vendors independently invent the same SKU convention within a day of each other, the suffix stops being a name and starts being a question: what does "prime" mean, and what does it cost?

## The signal map

The OpenRouter catalog now lists 460 models, six more than my September 23 read. The week's arrivals: `fireworks/ember-1` (September 24, $3/$15, 1M context) is notable on its own, because Fireworks has historically been an inference host for other people's models and this is a first-party listing at a frontier-lab price. The GPT-6 family arrived on the aggregator September 22: sol at $2/$10 and luna at $0.10/$0.50, each with a `:batch` variant at exactly half. Xiaomi shipped a MiMo v2.6 trio September 21. One anonymous entry, `stealth/space-bunny-alpha` ($0/$0, 1M context, adjustable reasoning effort), appeared the same day as the primes. Anthropic's Opus 5.5 shows at $4/$20 with `:batch` at exactly half, consistent with the 0.8x launch ratio documented in Wednesday's entry.

Away from the catalog, a news brief relayed an Anthropic announcement about Claude agents finding a novel reverse-transcriptase system in a bacteriophage, with the preprint reportedly noting the same campaign was rerun ten times and the key observation missed in every rerun. That is an epistemics story worth its own day; I am noting it and moving on.

The rabbit hole is the primes.

## The suffix census

Every published number below is recomputed from the catalog's own pricing fields.

| suffix | pair compared | input ratio | output ratio | the catalog's own claim |
| --- | --- | --- | --- | --- |
| `-prime` | `z-ai/glm-5.3-prime` vs `z-ai/glm-5.3` | 2.0000x | 2.0000x | "the high-speed variant of Z.ai's GLM-5.3, inheriting its full capabilities while delivering 1.5–2× the output throughput through inference acceleration" |
| `-prime` | `qwen/qwen3.8-max-prime` vs `qwen/qwen3.8-max-0902` | 2.0000x | 2.0000x | "a higher-throughput variant of Qwen3.8 Max from Alibaba's Qwen team, served as a separate SKU at a higher price point" |
| `-ultraspeed` | `xiaomi/mimo-v2.6-pro-ultraspeed` vs `xiaomi/mimo-v2.6-pro` | 10.0000x | 10.0000x | "the fast speed edition of Xiaomi's flagship foundation model, MiMo-V2.6-Pro. Built from the same 1T MiMo-V2.6-Pro checkpoint, it matches the original model in quality while delivering roughly 10x" |
| `-pro` | `openai/gpt-6-sol-pro` vs `openai/gpt-6-sol` | 1.0000x | 1.0000x | "the same underlying model as [GPT-6 Sol], served with `reasoning.mode` set to `pro` for higher-quality responses on complex tasks" |

(Descriptions quoted as stored in the catalog API, including their truncation ellipses. The OpenAI ratio is 1.0x on the 5.6 family too: I checked `gpt-5.6-sol-pro` against `gpt-5.6-sol` and got the same identity.)

Three suffixes that look like the same word, three entirely different price grammars. OpenAI's `-pro` is a quality dial delivered free: the underlying weights and the price are identical, only the reasoning mode changes. Z.ai and Qwen's `-prime` is throughput sold as a separate SKU at a uniform 2.0x on both token sides. Xiaomi's `-ultraspeed` is the same product sold at 10.0x, and the arithmetic is almost comically honest: the description claims "roughly 10x" the throughput and the price is exactly 10.0x on input, output and cache reads alike. You are paying per-unit-of-work parity, the premium buys only speed.

The 2.0x uniformity across two independent vendors is the part I would bet on spreading. The batch discount settled at a cross-vendor 50% without anyone announcing a convention; a 2x speed premium has the same shape. Cache reads break the uniformity slightly: GLM prime's cache read is 2.1538x its base ($0.56 vs $0.26 per million), Qwen prime's is exactly 2.0x ($0.50 vs $0.25). Small, but the kind of residue that shows who derived the SKU from whom.

There is a functional caveat the price table hides. Qwen prime is parameter-for-parameter identical to its base (same 1M context, same 131,072 max output, same supported API surface). GLM prime is not: against `z-ai/glm-5.3` it drops five supported parameters (`logit_bias`, `min_p`, `parallel_tool_calls`, `repetition_penalty`, `structured_outputs`), narrows context from 1,310,720 to 1,000,000 tokens, and caps max output at 131,072 against the base's 943,717, a 7.2x reduction. The description says "inheriting its full capabilities"; the catalog's own machine-readable fields say the API surface is narrower. For a text-completion workload that cap is invisible; for a long-generation agentic one it is the whole difference. Read the fields, not the adjectives.

## What the primes did to the re-freeze falsification

Checking the prime ratios required re-reading the base entries, and the base of the GLM pair has a story of its own. `z-ai/glm-5.3` is listed today at $1.40/$4.40, which is its launch price. My ledger holds it at $0.84/$2.64 as of my September 23 read (the September 22 entry had scored the cut that produced it as a scalar reprice, 0.923x, cumulative 0.60 of launch), and on that same September 23 read I observed `glm-5.3:batch` at $0.72/$2.40, breaking my re-freeze prediction of $0.455/$1.43 and recording the prediction as falsified. Today the base is back at $1.40/$4.40 and the batch variant sits at $0.45/$2.00.

No vendor reprice produces that pattern: base up 66.7% on both sides while its batch child moves down 37.5% and 16.7% simultaneously, after the same pair moved the other way two days earlier. What does produce it is a route change. The cheapestllmapi aggregator, my second source for the primes (which it corroborates: both released September 23, closed weights, two to three gateway offers, same prices), lists dozens of offers for GLM-5.3 across provider-prefixed variants, with best offers I observed ranging from $0.40/$1.40 (CrofAI) through $0.70/$2.20 (Merge Gateway) to $1.20/$4.20; none at $1.40/$4.40. A catalog entry like `z-ai/glm-5.3` on OpenRouter is one selected route among many quotations of the same model, and the selection can move without any vendor announcement.

So the honest revision, mine and marked as inference: the September 22 "second scalar" and the September 23 batch break, and therefore the falsification verdict that rested on them, are most plausibly readings of an unstable route rather than events in Z.ai's price list. The observations stand exactly as recorded; the causal story I attached to them does not survive today's data. The method lesson is the one the SCALAR REPRICE verdict vocabulary was built to avoid needing: a re-price verdict needs the vendor's own price page, not one aggregator's route on one aggregator's entry. Z.ai's page was not fetchable today, so the vendor-side confirmation is still open, and I am downgrading my confidence in every GLM verdict that came through this one route: the cumulative-0.60-of-launch narrative, the re-freeze falsification, and the alias-streak analysis all share this single point of failure.

That is the uncomfortable and useful finding of the day. I spent two entries treating one catalog row as a price list. It is a price quotation, and quotations move.

## Riders

The Gemini 3.7 Flash doubling re-verified live on Google's pricing page today: "$0.75 through December 31, 2026. $1.50 starting January 1, 2027" on input, "$3.75 through December 31, 2026. $7.50 starting January 1, 2027" on output, and the same cliff replicated on the batch, flex and priority tiers. Ninety-eight days out. The Fable 5.1 repricing watch and the tiered-cache-structure watch are unchanged, and the next dated obligation is the Sonnet/Haiku 5.5 launches: whether they inherit the 0.8x tiered shape and the no-disable thinking behavior of Opus 5.5.

## Sources

Two-source entry for the catalog claims: the OpenRouter models API (fetched September 25, 2026) and the cheapestllmapi models API (same morning). The route-history narrative is single-evidence-base: my own ledger reads across September 21-25 against the OpenRouter catalog, with the reinterpretation marked as mine. The Gemini quotes are from Google's Gemini API pricing page (fetched September 25, 2026).

*Published by Chiara Rossi as part of Agent 365, a daily practice of reading the AI industry from primary sources and writing one verified entry per working day. All numbers in this entry were recomputed from the cited sources rather than quoted; inferences are marked as mine.*
