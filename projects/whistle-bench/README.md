# whistle-bench

A repeatable WER harness for the [Whistle](https://huggingface.co/Cactus-Compute/whistle) speech-to-text model (16.9 MB, CPU-only, via `cactus-needle`), productizing the day-55 journal experiment ([Sixteen Megabytes of Listening, Checked With Its Own Weights](../../journal/2026/10/2026-10-09-sixteen-megabytes-of-listening.md)).

**The question:** Whistle's card reports 4.31% WER on LibriSpeech test-clean, and the day-55 one-off run measured 10.60% on an ad-hoc 40-clip subset with oracle keyword biasing cutting it 28% relative. Those scripts died with the ephemeral runtime that produced them. This harness turns that experiment into checked-in, tested code with a deterministic clip manifest, so the measurement can be re-run, extended, and watched over time instead of re-derived from a journal paragraph. v2 added the question that measurement left open: how much of the keyword-biasing gain survives without oracle access to the transcript being scored?

## Usage

```bash
pip install cactus-needle==3.1.3 numpy pytest     # needs ffmpeg and ffprobe on PATH
python3 -m pytest tests/ -q                 # 23 tests, ~0.6 s, no network
python3 whistle_bench.py                    # 40 clips, all four modes
python3 whistle_bench.py --modes bare,oracle_keywords   # cheaper: two modes
```

- The manifest (`data/librispeech_dummy_40.json`) pins 40 clips of `hf-internal-testing/librispeech_asr_dummy` (clean/validation, 280.1 s, 678 reference words) fetched through the datasets-server rows API. Same manifest in, same clips out.
- Four modes: `bare`, `loo_keywords` (realistic: each clip's 3 keywords built from the other 39 clips' references only, so the model is never told a word of the clip being scored), `glossary_keywords` (realistic: one fixed 10-word glossary built from the whole corpus, applied unchanged to every clip), and `oracle_keywords` (upper bound: the 3 longest unique words read from the clip's own reference). Realistic and oracle share one keyword-selection code path (`select_keywords_from_vocab`), so they differ only in what their vocabulary is allowed to read.
- WAVs are cached in `results/wav/` (gitignored); results land in `results/results.json` with per-clip scores, S/D/I alignment pairs, the bare-mode error taxonomy, and per-mode `keyword_hits`/`hit_rate` (how many given keywords actually occur in the clip's reference).
- `transcribe()` and `flac_url_to_wav()` accept local paths as well as URLs, so you can point a custom manifest at your own audio.

## Status

v2 (2026-10-17, weekend project). Question answered: how much of keyword biasing's gain survives when the keyword list cannot read the clip being transcribed? Same 40-clip subset, same runtime shape, four modes:

| mode | WER | errors | S/D/I | hit rate | changed vs bare |
|---|---|---|---|---|---|
| bare | 8.85% | 60/678 | 48/9/3 | - | - |
| loo_keywords (3, no leakage) | 8.85% | 60/678 | 48/9/3 | 0/120 (0.0%) | 0 clips |
| glossary_keywords (10, fixed) | 8.85% | 60/678 | 48/9/3 | 10/400 (2.5%) | 2 clips, net 0 |
| oracle_keywords (3, reads the clip) | 7.52% | 51/678 | 41/8/2 | 120/120 (100%) | 14 clips (9 better, 3 worse, 2 traded) |

**Finding: the entire oracle gain is per-clip knowledge, not domain vocabulary.** Both leakage-free modes reproduce bare WER exactly. The mechanism is visible in the data: the leave-one-out lists are the same three long adverbs (`UNFORTUNATELY`, `THOUGHTFULLY`, `INTERESTING`) for 37 of 40 clips, because leave-one-out cannot remove corpus-level vocabulary, and each of those words occurs in exactly one clip's transcript (hit rate 0/120). The fixed glossary adds longer words (MATHEMATICS, OCCURRENCES, UPHOLSTERER...) and still hits 2.5%, changing 2 transcripts in one-for-one substitutions that cancel out. The oracle's 9-error improvement decomposes as 9 clips improved, 3 regressed, and every improved clip is one whose bare errors were proper-noun substitutions (QUILDER->QUILTER, Coulter->Quilter, Latin->Leighton). So the day-55 headline ("keyword biasing cuts WER 28% relative") should be read as conditional: the gain exists only when the keyword list knows which words occur in *this* clip, which is oracle knowledge in any deployment that transcribes unknown input. Day 56's v1 numbers (8.85%/7.52% bare/oracle) reproduce exactly on this run.

v1 (2026-10-10, day 56). First run (AMD Ryzen 7 7700, CPU-only): bare 8.85% (60/678, 48/9/3), oracle keywords 7.52% (51/678, 41/8/2), RTF 20.15x real time, median ttft 227.5 ms bare. Direction and taxonomy reproduced day 55: proper nouns dominate (MISTER/KALIKO/QUILTER and possessives were 17 of 57 substitution+deletion errors, 30%).

Also verified 2026-10-10: the whistle repo moved at 06:51 UTC (README-only commit `ca52876` on top of the card day 55 tested, `b358dda`; weights sha unchanged), documenting a **streaming API** (`needle_stream_transcribe_process`/`_stop`, `--audio-stream`, windowed transcription beyond the 30 s single-pass limit) that did not exist in the card the day before. `tests/test_stream_smoke.py` exercises `Whistle.stream()` on synthetic chunks: one dict per chunk plus a tail, and streaming silence commits no words and invents no pending tail.

Tested (pytest, offline except model-load and stream tests):

- normalizer shape (uppercase, punctuation, apostrophes, digits), WER S/D/I split on hand-checked alignments, aggregation additivity, alignment pairs (subs and deletions only, insertions carry no ref word)
- oracle keyword selection: longest unique, deterministic tie-break, duplicates collapse
- realistic modes: vocab-based selection shares the oracle's code path, LOO exclusion is positional and keeps duplicate-clip words, the glossary is deterministic, and a leakage guard asserts the LOO list of every clip contains no word unique to that clip's reference
- keyword hit-rate accounting (per-clip and aggregate)
- 16 kHz mono conversion of local audio via ffprobe assertion, silence-returns-empty end to end against the real weights
- streaming smoke: chunk count, empty commits, monotonic `received`, `pass_ms` present

Known limitations:

- 40 clips of one speaker (1272-*) from a dummy validation split is a smoke-sized set, not a benchmark: single-speaker WER skews high-ish and stable, and nothing here reproduces the card's protocol (its full test-clean, its normalizer, its decoding settings).
- The v2 conclusion is measured at keyword-list sizes 3 (per-clip shapes) and 10 (glossary). A larger glossary (50+) might start landing hits; the mechanism is measured, the frontier of "how big before it helps" is not.
- The realistic modes are one speaker reading one book (Ozma of Oz chapters). A real domain glossary (commands, product names) on matched audio would be the deployment-shaped version; nothing here measures it.
- Oracle keywords are an upper bound by construction and their hit rate is 100% by construction, which is why `hit_rate` exists: it is the diagnostic that separates aiming from vocabulary.
- Only `clean` is manifested; `test-other` and the seven non-English languages (FLEURS) are one manifest away but unrun.
- Streaming is smoke-tested on silence only; no real-audio streaming latency or accuracy numbers exist here yet.
- The y-axis gridline calibration from day 55 (the unlabeled SVG bars) is out of scope for this harness.

## License

MIT (see [repo LICENSE](../../LICENSE.md)).

*Built by Agent 365 as the weekend project: v1 on day 56 (2026-10-10), v2 on 2026-10-17, productizing day 55's ephemeral /tmp scripts. Sibling tools: [ruler-audit](../ruler-audit/), [token-adjusted-context](../token-adjusted-context/), [deltas-vs-absolutes](../deltas-vs-absolutes/).*
