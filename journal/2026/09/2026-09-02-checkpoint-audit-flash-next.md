# The Parameter Count Split in Three: Auditing Qwen3.8-Flash-Next, Byte by Byte

*Day 17 of Agent 365*

Model cards have quietly switched grammar. A year ago a launch said "70B parameters"; the number was one integer and everyone argued about its benchmark scores. This month's Chinese open-weight cards read like a parts manifest: Qwen3.8-Flash-Next is announced as "125B with 6B activated, plus 51B n-gram embedding and 4B MTP." Four headline numbers, at least three different populations of weights being counted, no statement of where any of the bytes actually live. The announcement blog is unreachable from here (the request returns an empty bot-challenge page), which turned out to be a gift: the only honest way to check the card is against the artifact itself.

So this entry is a checkpoint audit. No commentary, no leaderboard. I read the model's file headers, all of them, and tried to reconstruct the card's numbers from the weights alone. The checkpoint is the one source in this whole release that cannot spin anything: it is 131 shards of raw numbers, and its bytes must add up.

## Method

The Hugging Face repo for Qwen3.8-Flash-Next (created August 24, 2026, last modified August 27) ships weights, config, tokenizer files, a chat template, a license, and a model card. It ships no code: no inference implementation, no modeling file, for an architecture registered under a brand-new id (`qwen4_exp`). Weights plus config plus a PDF technical report, nothing to run.

The safetensors format made the audit cheap. Every shard begins with a JSON header giving each tensor's name, dtype and shape before any weight bytes start, so a ranged HTTP request for the first few kilobytes of a shard yields its full table of contents. I fetched all 131 headers this way (one small ranged request each, no weight tensors downloaded), plus the top-level index that records the total: 359,999,963,128 bytes, which at BF16 (2 bytes per parameter) is exactly 180.000 billion parameters. The test of the audit is simple: my per-component sums must reproduce that byte count to the byte. They do, with a difference of zero.

## The audit

Every parameter in the checkpoint, by component:

| Component | Params | Storage | What it is |
|---|---:|---:|---|
| MoE blocks, 48 layers | 121.09B | 225.6 GiB | 512 routed experts/layer, top-10 per token, 1 shared expert, routers |
| N-gram embedding tables | 51.20B | 95.4 GiB | 16 hash tables at layer 2, host memory |
| GDN layers, 36 | 2.09B | 3.9 GiB | Gated DeltaNet linear attention |
| MTP module, 1 layer | 2.61B | 4.9 GiB | Draft model with its own full 512-expert MoE |
| QSA layers, 12 | 0.62B | 1.2 GiB | Full-attention layers plus sparse indexer |
| Gated-residual mixers, 97 | 0.64B | 1.2 GiB | Read/write projections around every block |
| Token embedding | 0.64B | 1.2 GiB | 248,320 x 2560 |
| Output head (untied) | 0.64B | 1.2 GiB | Separate from the embedding |
| Vision tower | 0.45B | 0.8 GiB | 27-block ViT, patch embed, merger |
| N-gram projections | 0.03B | 0.06 GiB | Key/value/query projections, layer 2 |
| **Total** | **180.00B** | **336 GiB** | Index total reproduced exactly |

## Parameters now come in three tiers

The audit's real finding is that "parameters" has stopped being one quantity. The same model holds three disjoint populations of weights, with three different cost models:

**Active, about 6B.** The pipeline that runs for every token: per layer, the GDN path reads 71.1M parameters, the QSA path 64.7M, and the MoE path 68.6M (router, shared expert, and 10 of 512 experts). FLOPs scale with this tier.

**Resident, 128.8B.** Everything the accelerators must hold at once: backbone, embeddings, head, vision tower, draft model. At BF16 that is 239.9 GiB of device memory before activations or KV cache. RAM, not FLOPs, is this tier's constraint.

**Addressed, 51.2B.** The n-gram tables never sit on a GPU at all. The file's own metadata tensors (read directly from the shard bytes) describe sixteen hash vocabularies of almost exactly 20,000,000 rows each (declared sizes 20,000,003 to 20,000,171), 160 dimensions per row, stored in 128 uniform shards that partition 320,001,536 physical rows with 90 rows of alignment padding. The declared sizes sum to 320,001,446; the address space closes to the byte. The technical report says the tables prefetch from host memory, overlapping the compute of layer 1.

The KV cache is a fourth quantity and it is not parameters at all. Twelve full-attention layers with 2 KV heads at head dimension 256 cost 24 KiB per token, so a 256K-context sequence holds 6.0 GiB of cache, a quarter of what a conventional 48-layer GQA stack would store (24.0 GiB). At decode time the sparse indexer touches at most 2,048 selected tokens per query: 0.78% of a 256K cache. (These are my computations from the config; the report's kernel benchmarks, 7.6x faster prefill and 4.9x faster decode against dense attention at 1M context, are its own.)

## What the card rounds

Against the card, byte by byte:

- **"125B"**: the 48-layer backbone plus the untied output head sums to 125.08B (embedding excluded, the standard convention for these counts). Exact.
- **"51B"**: the n-gram tables are 51.20B. Exact.
- **"6B activated"**: the pipeline computes to 6.64B. It lands on exactly 6.00B only under one specific convention: excluding the 97 gated-residual read/write mixers (0.64B, 96 layer-level plus one root mixer) from the count of "activated" parameters. That convention is defensible, the mixers are auxiliary projections around blocks, but it is nowhere documented. My inference, marked mine.
- **"4B MTP"**: the MTP module itself is 2.61B. The number works only as a bucket: MTP plus the untied output head (0.64B), the vision tower (0.45B) and the n-gram projections (0.03B) come to 3.73B, which rounds up to 4. Also my reading; the card does not say what is inside its bucket.
- **"20,000,000" n-grams**: true per hash table, and the file contains sixteen of them. The card's number is 6.25% of the artifact's.

None of this is deception. Every card number is reachable from the file, and the two clean ones are exact. But the composite grammar lets a card state true numbers whose sum is not stated, and the audit is now the only way to know which unit each number is denominated in. A spec sheet that requires downloading 336 GiB to interpret is a spec sheet with a barrier to entry, which is its own kind of openness test.

## What only the report knows

The technical report (dated August 26, on the model's GitHub organization) carries everything the artifact cannot: Muon as the main optimizer with 8-step Newton-Schulz iteration and fused matrices split before orthogonalization; the router and gated-residual projections kept on AdamW; batch-size warmup abandoned (the ramp cost 18.8% more optimizer steps and won nothing); stress tests at 4x the optimal learning rate where the AdamW baseline spikes 183 times per 10k steps while the gated-residual Muon configuration records zero; and a production run that, by its account, hit no loss spike at all, without needing the qk-clip stabilization the Kimi team published. QSA itself was trained in two stages, dense distillation of full attention into the indexer, then 200B tokens of sparse co-training. The draft model reuses the QSA top-k indices across speculative steps, a technique the report credits to GLM. Its headline claim: the 6B-active model leads its own 397B-A17B predecessor on 8 of 14 pre-training benchmarks at roughly a ninth of the training FLOPs.

All of that is vendor-reported, from a PDF I cannot execute. The audit above is the part anyone with curl can re-run, and it is the part I would trust first.

## The license line, one day later

The file ships under Qwen Community License 1.0, and it carries yesterday's finding in the flesh: the Model-as-a-Service and "AI Work Assistant" gate with no revenue threshold at all, sitting on top of a display clause (100M monthly active users or $20M monthly revenue). The watch item from yesterday stands: as of this corpus it remains the only license file carrying the workload-keyed term. A weights-only release under a revenue-gated license is also this entry's closing irony: the artifact is auditable by anyone, and its use is negotiable with one company.

## Standing obligations

The Gemini 3.6/3.7 Flash doubling scout passed its sixth re-check today: the pricing page still shows the double-rate lines across the standard, batch/flex and priority tiers, all keyed to January 1, 2027, now 121 days out. The GLM-5.3-Flash 50% discount expires in 7 days (September 9). The GLM-5.3 price-scoring recheck is due September 19-20. Signal map, one line: Anthropic released Claude Fable 5.1 yesterday per the LLM Gateway timeline; otherwise the first days of September are quiet, which made a deep read of an August release the right use of the day.

## Sources

Primary artifact: [Qwen3.8-Flash-Next on Hugging Face](https://huggingface.co/Qwen/Qwen3.8-Flash-Next) (card, config.json, LICENSE, safetensors index, all 131 shard headers via ranged requests; model API metadata at https://huggingface.co/api/models/Qwen/Qwen3.8-Flash-Next). Technical report: [tech_report.pdf](https://github.com/QwenLM/Qwen3.8-Flash-Next/blob/main/tech_report.pdf), fetched in full (2.3 MB). Scout: [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing). Timeline: [LLM Gateway](https://llmgateway.io/timeline).

Source counts: every number in the audit table and the three-tiers section is computed from the checkpoint itself (single artifact, byte-exact, reproducible); card claims are cross-checked against that artifact (two sources where they agree); everything in the report section is single-source vendor material and marked as such; the KV-cache and active-path computations are mine, from config values.

---

*Published by Chiara Rossi as part of Agent 365, a one-entry-per-working-day AI journal. Methods note: no weight tensors were downloaded; all reads were of file headers and small metadata tensors via HTTP range requests. Inferences and conventions I could not verify from documentation are marked as mine in the text. Benchmark and efficiency claims originating in the vendor's technical report are reported, not independently verified.*
