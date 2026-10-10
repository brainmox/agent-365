#!/usr/bin/env python3
"""whistle-bench: repeatable WER harness for the Whistle speech-to-text model.

Reproduces the day-55 journal experiment (journal/2026/10/2026-10-09-
sixteen-megabytes-of-listening.md) as a checked-in, tested artifact:
bare transcription vs oracle keyword biasing on a fixed LibriSpeech subset,
with per-clip error taxonomy. All numbers in the results JSON are computed
by this script; none are typed by hand.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

MANIFEST_DEFAULT = Path(__file__).parent / "data" / "librispeech_dummy_40.json"
KEYWORDS_PER_CLIP = 3

# ---------------------------------------------------------------- normalization

_KEEP = re.compile(r"[^A-Z0-9 ']")
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Uppercase, keep alphanumerics, spaces and apostrophes, drop other
    punctuation, collapse whitespace. Documented shape of the Whisper
    normalizer, not the Whisper normalizer package."""
    t = text.upper()
    t = _KEEP.sub("", t)
    return _SPACES.sub(" ", t).strip()


def words(text: str) -> list:
    w = normalize(text).split()
    return w


def edit_distance(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i, wa in enumerate(a, 1):
        cur = [i]
        for j, wb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (wa != wb)))
        prev = cur
    return prev[-1]


def wer(ref: list, hyp: list) -> dict:
    """Word error rate with the S/D/I split from a Levenshtein alignment."""
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1,
                           dp[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))
    i, j, sub, dele, ins = n, m, 0, 0, 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            if ref[i - 1] != hyp[j - 1]:
                sub += 1
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            dele += 1
            i -= 1
        else:
            ins += 1
            j -= 1
    errors = sub + dele + ins
    return {"errors": errors, "ref_words": n, "substitutions": sub,
            "deletions": dele, "insertions": ins,
            "wer": round(errors / n, 4) if n else None}


def alignment_pairs(ref: list, hyp: list) -> list:
    """(ref_word, hyp_word) pairs for every substitution, ref_word None for
    deletions. Same backtrace as wer(), exposed for the error taxonomy."""
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1,
                           dp[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))
    pairs, i, j = [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            if ref[i - 1] != hyp[j - 1]:
                pairs.append((ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            pairs.append((ref[i - 1], None))
            i -= 1
        else:
            j -= 1
    return pairs


def select_keywords(ref_text: str, k: int = KEYWORDS_PER_CLIP) -> list:
    """Oracle keywords: the k longest unique normalized reference words,
    ties broken alphabetically. Upper bound by construction: read from the
    reference the model is about to be scored against."""
    seen, uniq = set(), []
    for w in words(ref_text):
        if w not in seen:
            seen.add(w)
            uniq.append(w)
    uniq.sort(key=lambda w: (-len(w), w))
    return uniq[:k]


# ---------------------------------------------------------------- audio

def flac_url_to_wav(url: str, dst: Path) -> Path:
    src = Path(url)
    if src.exists():
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                        "-ar", "16000", "-ac", "1", str(dst)], check=True)
        return dst
    with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as f:
        tmp = f.name
    try:
        urllib.request.urlretrieve(url, tmp)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp,
                        "-ar", "16000", "-ac", "1", str(dst)], check=True)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return dst


def audio_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


# ---------------------------------------------------------------- model

def load_model():
    from needle import Whistle
    return Whistle()


def transcribe(model, wav: Path, keywords=None) -> dict:
    return model.transcribe(str(wav), keywords=keywords)


# ---------------------------------------------------------------- experiment

def run(manifest_path: Path, results_dir: Path, modes: list, limit=None):
    manifest = json.loads(manifest_path.read_text())
    if limit:
        manifest = manifest[:limit]
    results_dir.mkdir(parents=True, exist_ok=True)
    cache = results_dir / "wav"
    cache.mkdir(exist_ok=True)
    model = load_model()

    clips = []
    total_audio = 0.0
    for row in manifest:
        wav = cache / f"{row['id'].replace('/', '_')}.wav"
        if not wav.exists():
            flac_url_to_wav(row["audio"][0]["src"], wav)
        clips.append({"id": row["id"], "speaker_id": row["speaker_id"],
                      "ref": row["text"], "wav": wav})
        total_audio += audio_seconds(wav)

    run_out = {"manifest": manifest_path.name, "clips": len(clips),
               "audio_seconds": round(total_audio, 1),
               "modes": {}}
    import time
    for mode in modes:
        per_clip = []
        agg = {"errors": 0, "ref_words": 0, "substitutions": 0,
               "deletions": 0, "insertions": 0}
        t_first = []
        wall_start = time.monotonic()
        for c in clips:
            kw = select_keywords(c["ref"]) if mode == "oracle_keywords" else None
            res = transcribe(model, c["wav"], keywords=kw)
            t_first.append(res["ttft_ms"])
            score = wer(words(c["ref"]), words(res["text"]))
            for k in agg:
                agg[k] += score[k]
            per_clip.append({"id": c["id"], "score": score,
                             "keywords": kw,
                             "hyp": res["text"],
                             "pairs": alignment_pairs(words(c["ref"]),
                                                      words(res["text"]))})
        wall = time.monotonic() - wall_start
        run_out["modes"][mode] = {
            "aggregate": dict(agg, wer=round(agg["errors"] / agg["ref_words"], 4)),
            "median_ttft_ms": sorted(t_first)[len(t_first) // 2],
            "wall_seconds": round(wall, 1),
            "per_clip": per_clip,
        }

    # taxonomy over substitutions and deletions of the bare mode
    if "bare" in run_out["modes"]:
        counts = {}
        for pc in run_out["modes"]["bare"]["per_clip"]:
            for ref_w, hyp_w in pc["pairs"]:
                if ref_w is not None and (hyp_w is None or ref_w != hyp_w):
                    counts[ref_w] = counts.get(ref_w, 0) + 1
        run_out["bare_error_counts"] = dict(sorted(counts.items(),
                                                   key=lambda kv: -kv[1]))
    bare = run_out["modes"]["bare"]
    run_out["rtf"] = round(total_audio / bare["wall_seconds"], 2)
    out = results_dir / "results.json"
    out.write_text(json.dumps(run_out, indent=1))
    print(json.dumps({m: {"wer": v["aggregate"]["wer"], "errors": v["aggregate"]["errors"],
                          "ref_words": v["aggregate"]["ref_words"]}
                      for m, v in run_out["modes"].items()}, indent=1))
    print(f"wrote {out}")
    return run_out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=MANIFEST_DEFAULT)
    ap.add_argument("--results", type=Path, default=Path(__file__).parent / "results")
    ap.add_argument("--modes", default="bare,oracle_keywords")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    run(a.manifest, a.results, [m for m in a.modes.split(",") if m], a.limit)


if __name__ == "__main__":
    main()
