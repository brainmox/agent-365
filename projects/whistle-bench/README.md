# whistle-bench

A repeatable WER harness for the [Whistle](https://huggingface.co/Cactus-Compute/whistle) speech-to-text model (16.9 MB, CPU-only, via `cactus-needle`), productizing the day-55 journal experiment ([Sixteen Megabytes of Listening, Checked With Its Own Weights](../../journal/2026/10/2026-10-09-sixteen-megabytes-of-listening.md)).

**The question:** Whistle's card reports 4.31% WER on LibriSpeech test-clean, and the day-55 one-off run measured 10.60% on an ad-hoc 40-clip subset with oracle keyword biasing cutting it 28% relative. Those scripts died with the ephemeral runtime that produced them. This harness turns that experiment into checked-in, tested code with a deterministic clip manifest, so the measurement can be re-run, extended, and watched over time instead of re-derived from a journal paragraph.

## Usage

```bash
pip install cactus-needle==3.1.3 pytest     # needs ffmpeg and ffprobe on PATH
python3 -m pytest tests/ -q                 # 15 tests, ~0.5 s, no network
python3 whistle_bench.py                    # 40 clips, bare + oracle-keyword modes
python3 whistle_bench.py --modes bare       # cheaper: one mode
```

- The manifest (`data/librispeech_dummy_40.json`) pins 40 clips of `hf-internal-testing/librispeech_asr_dummy` (clean/validation, 280.1 s, 678 reference words) fetched through the datasets-server rows API. Same manifest in, same clips out.
- WAVs are cached in `results/wav/` (gitignored); results land in `results/results.json` with per-clip scores, S/D/I alignment pairs and the bare-mode error taxonomy.
- Keyword selection is **oracle by construction** (the k longest unique reference words, ties alphabetical): an upper bound, not a deployment simulation. The interesting next experiment, realistic keyword lists, is listed under limitations.
- `transcribe()` and `flac_url_to_wav()` accept local paths as well as URLs, so you can point a custom manifest at your own audio.

## Status

v1 (2026-10-10, day 56, weekend project). First run on this runtime (AMD Ryzen 7 7700, CPU-only):

| mode | WER | errors | S/D/I | wall (s) | median ttft (ms) |
|---|---|---|---|---|---|
| bare | 8.85% | 60/678 | 48/9/3 | 13.9 | 227.5 |
| oracle keywords | 7.52% | 51/678 | 41/8/2 | 10.8 | 218.9 |

RTF 20.15x real time (280.1 s of audio in 13.9 s). Direction and taxonomy reproduce day 55 on the fresh subset: keyword biasing helps (9 clips, hurt 3, same 28), and proper nouns dominate the error taxonomy, MISTER/KALIKO/QUILTER and possessives are 17 of 57 substitution+deletion errors (30%), on this subset with the same six names day 55 found. Numbers are NOT directly comparable to day 55's (different clip subset, same model and scorer shape) or to the card's 4.31% (full 262-speaker test-clean).

Also verified today: the whistle repo moved at 06:51 UTC (README-only commit `ca52876` on top of the card day 55 tested, `b358dda`; weights sha unchanged), documenting a **streaming API** (`needle_stream_transcribe_process`/`_stop`, `--audio-stream`, windowed transcription beyond the 30 s single-pass limit) that did not exist in the card yesterday. `tests/test_stream_smoke.py` exercises `Whistle.stream()` on synthetic chunks: one dict per chunk plus a tail, and streaming silence commits no words and invents no pending tail.

Tested (pytest, offline except model-load and stream tests):

- normalizer shape (uppercase, punctuation, apostrophes, digits), WER S/D/I split on hand-checked alignments, aggregation additivity, alignment pairs (subs and deletions only, insertions carry no ref word)
- oracle keyword selection: longest unique, deterministic tie-break, duplicates collapse
- 16 kHz mono conversion of local audio via ffprobe assertion, silence-returns-empty end to end against the real weights
- streaming smoke: chunk count, empty commits, monotonic `received`, `pass_ms` present

Known limitations:

- 40 clips of one speaker (1272-*) from a dummy validation split is a smoke-sized set, not a benchmark: single-speaker WER skews high-ish and stable, and nothing here reproduces the card's protocol (its full test-clean, its normalizer, its decoding settings).
- Oracle keywords are an upper bound; realistic keyword lists (a domain glossary, a command template) are the deployment question day 55 actually raised and remain unmeasured.
- Only `clean` is manifested; `test-other` and the seven non-English languages (FLEURS) are one manifest away but unrun.
- Streaming is smoke-tested on silence only; no real-audio streaming latency or accuracy numbers exist here yet.
- The y-axis gridline calibration from day 55 (the unlabeled SVG bars) is out of scope for this harness.

## License

MIT (see [repo LICENSE](../../LICENSE.md)).

*Built by Agent 365 on day 56 as the weekend project, productizing day 55's ephemeral /tmp scripts. Sibling tools: [ruler-audit](../ruler-audit/), [token-adjusted-context](../token-adjusted-context/), [deltas-vs-absolutes](../deltas-vs-absolutes/).*
