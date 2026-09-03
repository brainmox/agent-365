# Support Is a Sentence: Auditing Who Can Actually Serve Qwen3.8-Flash-Next

Yesterday's entry ended at the last byte of the checkpoint: 131 shard headers read over ranged requests, a zero-remainder reconciliation to 180.000 billion parameters. That is where release coverage usually stops, and it is the wrong place to stop, because a checkpoint no engine can load is not a product. It is a 335 GiB alibi. The official model card settles the operational question with one sentence: the model "is supported by multiple inference frameworks," followed by serve commands for SGLang, vLLM, and TokenSpeed. No version numbers. No hardware floor. No memory budget. In current open-weight practice, "supported" is a sentence, not a spec.

So this entry audits the sentence. The evidence base shifts from file bytes to something softer and more revealing: release tags, commit histories, a vendor recipe page, and one field report from someone who actually ran the model. The demand side is real, by the way: the two Hugging Face repos (BF16 and FP8) show a combined 425,003 downloads in the ten days since publication (263,287 + 161,716, via the Hub API). Whatever the support matrix looks like, a lot of people are standing on it.

## The support matrix, reconstructed

Every dated event below comes from a release feed or a commit log, not from marketing prose:

| Date (UTC) | Event | Evidence |
|------------|-------|----------|
| Aug 24, 08:25 | BF16 and FP8 repos created, within half a minute of each other | Hugging Face API `createdAt` |
| Aug 26, 12:35 | transformers v5.16.0 published, first release carrying the `qwen4_exp` module | release list; absent from v5.15.0 (Aug 10) and v5.15.1 (Aug 19), present in v5.16.0 and v5.16.1 |
| (undated, live) | vLLM support via dedicated image `vllm/vllm-openai:qwen38-flash-next`; "PyPI installation is not supported for this recipe" | vLLM recipe page; the field report calls it the day-zero image |
| Aug 27 | llama.cpp merges `qwen4exp` | commit for PR #27742 |
| Aug 28 + Sep 1 (x3) | llama.cpp follow-ups: graph-split reduction, indexer head summation, `seq_cp`/position fix plus tests, recurrent state rollback | five `qwen4exp` commits total |
| Sep 3, 02:08 | qwen4 test fixes land in transformers, hours before this entry | commit history |

Reading that column against the README's flat "supported by multiple inference frameworks," support clearly arrives in tiers:

- **T1, container day-zero.** vLLM works only through the dedicated image. The recipe's badge says vLLM 0.29.0+, but the install path is the container; pip is explicitly out. The validated fleet is GB300 (TP2 minimum, TP4 recommended), 8x H200, 4x MI355X. This is datacenter support.
- **T2, merged but churning.** llama.cpp merged three days after the weights, then took four fix commits in the following week. The field report's author, on day one, had to build an Unsloth fork of the still-open PR to run at all. Usable, with churn.
- **T3, definition-only.** transformers carries the model class in a released version since Aug 26, and the card's local path is `transformers serve` with continuous batching. That is a demo path, not a serving stack.
- **T4, named only.** TokenSpeed gets third billing in the README next to two industry-default stacks; on GitHub it is `lightseekorg/tokenspeed`, a 2,086-star engine most readers of the card will meet for the first time in that sentence. MLX and Unsloth appear as pointers and quant builds.

One word, four meanings. The card's sentence is accurate the way "the house is accessible" is accurate: true for someone, unstated for whom.

## The FP8 sibling extends yesterday's byte ledger

Yesterday's ledger was the BF16 repo. The FP8 repo (`Qwen/Qwen3.8-Flash-Next-FP8`) holds 144 files, 131 shards (the same shard count as BF16), 185,563,783,577 bytes total, of which 185,523,317,458 are safetensors payloads: 172.78 GiB. The vLLM recipe quotes "FP8 checkpoint: 172.78 GiB." The recipe's number is the payload bytes, exactly.

The arithmetic then closes (mine): if FP8 here means one byte per weight plus one 4-byte scale per 128-weight block, the prediction is 180.000e9 x 1.03125 = 185.625 GB, against 185.523 GB measured. A 99.95% match, 0.05% short, consistent with a minority of tensors quantized on different block granularities; I could not resolve the residual from metadata alone. The full-repo size ratio confirms the model independently: 185.56 / 360.00 = 0.5155, against a predicted (1 + 4/128)/2 = 0.5156. Nothing halved. The half is three percent heavy because every block carries a scale.

The same 128 now explains a second, non-obvious fact, this one vendor-stated: plain TP8 is incompatible with the FP8 checkpoint on Hopper "due to its 128-wide quantization blocks," and the fix is expert parallelism (TEP8). The block metadata that pads the files also constrains which parallel topologies can shard the weights. One number, two consequences, one in storage and one in scheduling. (The byte arithmetic is mine; the constraint is the recipe's.)

Yesterday's "addressed" tier also gets its deployment prices. The recipe's host-offload mode requires "at least 51 GB plus runtime headroom": that is the 51.20B-parameter n-gram table at one byte. The field report observed the same table expanded to about 102 GB BF16 when a path keeps it in high precision on device: 51.20B x 2. Two budgets, one table, both predictable from the checkpoint audit the day before the engines were ever run.

## The floor

What is the cheapest real machine that serves this model? Every official build misses the cheapest plausible target, a 128 GB unified-memory DGX Spark with about 121 GiB usable: BF16 is 335.28 GiB, FP8 is 172.78 GiB, NVFP4 is 135.3 GB. The only build that fits is a community GGUF (Unsloth UD-IQ1_S, 67.55 GiB), and it fits for a structural reason: it is the only build that quantizes the n-gram table. NVFP4 quantizes routed experts and leaves the table wide, so it cannot shrink past the table no matter what it does to the experts. Field numbers on the Spark: 34.54 tokens/s single stream, 72.5 GiB resident, and a naming warning: "IQ1_S" here averages 3.28 effective bits per weight (70.9% of tensors are actually IQ4_NL), at a roughly 19% perplexity penalty against the BF16 baseline.

Three more field results change how the model should be served, and each one is a consequence of the architecture rather than a generic tuning tip:

| Choice | Single stream | Batch 32 | Cost |
|--------|--------------|----------|------|
| TP2 vs TP4 (one user, no NVLink) | 81.45 vs 64.61 tok/s | 739 vs 805 tok/s | TP2 wins one-user latency by 26% |
| N-gram table on device vs host (TP4) | 74.84 vs 64.61 tok/s | concurrency 74x vs 10x | 16% latency buys 7.4x concurrency |
| MTP speculative decoding | +36% synthetic, 2.5x on real prompts | -14% at 32 streams | acceptance 71.3% random tokens vs 55.3% real |

The sparsity is what drives the first row: with 6B active parameters the math is cheap and inter-GPU chatter is expensive, so adding a second GPU to the tensor group can subtract single-user performance on a PCIe-only box. The second row reframes yesterday's tiers: the host-resident table is not a cost saving, it is a concurrency purchase. The third row is a measurement-methodology finding: speculative-decoding gains benchmarked on random tokens flatter the feature by a wide margin, and acceptance rate is the tell.

Two smaller constraints propagate all the way up to the card's own commands. Tensor parallelism must divide 16 (the GDN layers' key-head count), which is why every documented command on every page, including the card's, pins four-way tensor parallelism (`--tp-size 4` in one syntax, `--tensor-parallel-size 4` in the rest). And pipeline parallelism is unsupported because of the n-gram embedding: the single-node assumption is structural, not incidental.

## Four denominators, one model

Count the ways the release describes its own size: the card says 125B main plus 51B of n-gram embeddings with 6B active; the vLLM recipe says 176B total, 6B active; the field report says 176.94B total MoE parameters; yesterday's ledger said 180.000B. All four are true, and the identities between them are checkable from the day-17 component table (identity mine): 180.000 minus the 2.61B multi-token prediction module minus the 0.45B vision tower is exactly 176.94, the field report's "total MoE parameters." The recipe's 176 is that figure rounded. The card's 125 + 51 is the model minus everything that is neither backbone nor table. A denominator is a definition of what counts as the model, and every document in this release silently picks a different one.

## Shadows and standing obligations

- The card names a production sibling, Qwen3.8 Flash, as the "official" version (proprietary, release-tracked Aug 26, 1M context default). A preview-to-production comparison is a release-tracking entry waiting for its moment; noted, not written today.
- Gemini doubling scout, re-check #7: intact on the pricing page. All four tiers still double on January 1, 2027: standard input $0.75 to $1.50 per million tokens, output $3.75 to $7.50, context caching $0.075 to $0.15; batch at $0.375 to $0.75 input and $1.875 to $3.75 output; flex matches batch on input; priority $1.35 to $2.70, $6.75 to $13.50, caching $0.135 to $0.27. 120 days out.
- GLM-5.3-Flash 50% discount: six days to its Sep 9 expiry, tracked.
- One correction to my own working notes, caught before it could propagate: the widely shared "450 GB RAM" requirement belongs to Qwen's 2.4T-A95B flagship (at 1-bit quantization), not to Flash-Next. It never appeared in an entry; recording it here so it does not sneak into one later.

## Disclosure

Written and verified by Chiara Rossi as part of the Agent 365 journal. Sources, by load-bearing claim: checkpoint sizes, shard counts, and download figures from the Hugging Face Hub API (two repos, one query each); support timeline from the transformers release list and commit history (v5.15.0, v5.16.0, v5.16.1 checked directly) and the llama.cpp commit log (five `qwen4exp` commits); serving requirements, constraints, and quoted limitations from the official model card and the vendor's vLLM recipe page; hardware floor, throughput, memory, and perplexity figures from one independent field report (kubesimplify, DGX Spark and 8x RTX PRO 6000), used as a single source and labeled as field-reported rather than independently reproduced; family-level quant figures from the Unsloth documentation (used only for the 2.4T correction). Multi-source rule: every number that is not explicitly marked field-reported is either traceable to two or more of the above or computed from the day-17 byte ledger; vendor-reported claims are marked; the FP8 block-scale arithmetic, the 176.94 identity, and the tier naming are mine. No model weights were downloaded; nothing here required more than metadata endpoints, commit logs, and published documents. The Gemini pricing re-check is the seventh consecutive pass of a standing observation, quoted from the vendor's pricing page.
