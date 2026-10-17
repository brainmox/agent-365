import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import whistle_bench as wb


# ---------------------------------------------------------------- normalize/words

def test_normalize_uppercase_and_punct():
    assert wb.normalize("Mr. Quilter is the apostle!") == "MR QUILTER IS THE APOSTLE"
    assert wb.normalize("don't stop") == "DON'T STOP"
    assert wb.normalize("a, b;  c.") == "A B C"


def test_normalize_keeps_digits():
    assert wb.normalize("route 66") == "ROUTE 66"


def test_words_split():
    assert wb.words("Mister Quilter") == ["MISTER", "QUILTER"]


# ---------------------------------------------------------------- wer

def test_wer_perfect():
    s = wb.wer(["A", "B"], ["A", "B"])
    assert s["errors"] == 0 and s["wer"] == 0 and s["ref_words"] == 2


def test_wer_substitution_only():
    s = wb.wer(["A", "B"], ["A", "C"])
    assert (s["errors"], s["substitutions"], s["deletions"], s["insertions"]) == (1, 1, 0, 0)


def test_wer_deletion_and_insertion():
    s = wb.wer(["A", "B", "C"], ["A", "C"])
    assert s["deletions"] == 1 and s["insertions"] == 0 and s["errors"] == 1
    s = wb.wer(["A", "C"], ["A", "B", "C"])
    assert s["insertions"] == 1 and s["errors"] == 1


def test_wer_matches_edit_distance():
    s = wb.wer(["A", "B", "C", "D"], ["B", "X", "D", "E"])
    assert s["errors"] == wb.edit_distance(["A", "B", "C", "D"], ["B", "X", "D", "E"])


def test_wer_aggregation_additivity():
    """Summing per-clip S/D/I must equal the recomputed aggregate."""
    a = wb.wer(["A", "B"], ["A", "X"])
    b = wb.wer(["C"], [])
    agg = {k: a[k] + b[k] for k in ("errors", "ref_words")}
    assert agg["errors"] == 2 and agg["ref_words"] == 3


# ---------------------------------------------------------------- alignment

def test_alignment_pairs_marks_sub_and_del():
    pairs = wb.alignment_pairs(["MR", "QUILTER"], ["MR", "QUILDER"])
    assert pairs == [("QUILTER", "QUILDER")]
    pairs = wb.alignment_pairs(["A", "B", "C"], ["A", "C"])
    assert pairs == [("B", None)]


def test_alignment_pairs_ignores_matches_and_insertions():
    pairs = wb.alignment_pairs(["A", "B"], ["A", "B"])
    assert pairs == []
    pairs = wb.alignment_pairs(["A"], ["A", "X"])
    assert pairs == []  # insertions carry no ref word


# ---------------------------------------------------------------- keywords

def test_select_keywords_takes_longest_unique():
    kw = wb.select_keywords("the quick brown fox the fox again extraordinary")
    assert kw[0] == "EXTRAORDINARY"
    assert len(kw) == 3
    assert kw[1] in ("QUICK", "BROWN", "AGAIN")
    assert "THE" not in kw and "FOX" not in kw  # duplicates collapse


def test_select_keywords_deterministic_ties():
    a = wb.select_keywords("aa bb cc")
    b = wb.select_keywords("aa bb cc")
    assert a == b == ["AA", "BB", "CC"]  # equal length -> alphabetical


# ---------------------------------------------------------------- realistic modes

def test_select_keywords_from_vocab_longest_unique():
    vocab = ["THE", "QUILTER", "THE", "MISTER", "QUILTER", "EXTRAORDINARY"]
    assert wb.select_keywords_from_vocab(vocab, 2) == ["EXTRAORDINARY", "QUILTER"]


def test_build_vocab_loo_excludes_only_target():
    refs = ["alpha bravo", "bravo charlie", "delta alpha"]
    vocab = set(wb.build_vocab_loo(refs, 1))
    # BRAVO stays: it also occurs in clip 0, so it is domain vocabulary,
    # not a read of the held-out transcript. CHARLIE is unique to clip 1.
    assert vocab == {"ALPHA", "BRAVO", "DELTA"}
    assert "CHARLIE" not in vocab


def test_build_vocab_loo_keeps_duplicate_refs():
    """Two identical references: excluding one clip removes exactly one of
    them, the duplicate's words stay (that repetition is domain signal)."""
    refs = ["alpha bravo", "alpha bravo", "charlie"]
    vocab = set(wb.build_vocab_loo(refs, 0))
    assert vocab == {"ALPHA", "BRAVO", "CHARLIE"}


def test_build_glossary_fixed_size():
    refs = ["one two three four five", "six seven eight nine ten eleven"]
    g = wb.build_glossary(refs, 4)
    assert len(g) == 4
    assert g[0] == "ELEVEN"  # longest first
    assert "ELEVEN" in g


def test_keyword_hits_counts_presence():
    assert wb.keyword_hits(["ALPHA", "BRAVO"], "alpha and alpha") == 1
    assert wb.keyword_hits(["ALPHA"], "nothing here") == 0
    assert wb.keyword_hits([], "alpha") == 0


def test_loo_keywords_never_contain_target_words():
    """Leakage guard: for every clip, the LOO keyword list must be built
    from a vocabulary that does not include that clip's own reference."""
    refs = ["mister quilter is the apostle of the middle classes",
            "norbury and wharton were energetic and precise",
            "quilter watched the kaleidoscope with extraordinary care",
            "the quail sang plainly before sunrise"]
    for idx, r in enumerate(refs):
        vocab = wb.build_vocab_loo(refs, idx)
        kw = wb.select_keywords_from_vocab(vocab)
        leaked = set(wb.words(r)) & set(kw)
        assert leaked == set(), (r, kw, leaked)


def test_glossary_keywords_same_for_every_clip():
    refs = ["mister quilter is the apostle", "norbury wharton energetic"]
    g = wb.build_glossary(refs)
    assert wb.build_glossary(refs) == g
    assert len(g) == wb.GLOSSARY_SIZE or len(g) < wb.GLOSSARY_SIZE  # capped by corpus


def test_oracle_keywords_match_vocab_path():
    """The oracle path must equal building vocab from the clip's own
    reference, so oracle vs realistic differ ONLY in the vocab source."""
    r = "quilter watched the kaleidoscope with extraordinary care again"
    assert wb.select_keywords(r) == wb.select_keywords_from_vocab(wb.words(r))


# ---------------------------------------------------------------- end-to-end on synthetic audio

def _make_wav(tmp_path, seconds=1.0, freq=220):
    import math, struct, wave
    p = tmp_path / "tone.wav"
    with wave.open(str(p), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        frames = bytearray()
        for i in range(int(16000 * seconds)):
            v = int(8000 * math.sin(2 * math.pi * freq * i / 16000))
            frames += struct.pack("<h", v)
        f.writeframes(bytes(frames))
    return p


def test_flac_url_to_wav_local(tmp_path):
    """flac_url_to_wav converts any audio input (here a local wav path) to 16k mono."""
    import subprocess
    src = _make_wav(tmp_path)
    dst = wb.flac_url_to_wav(str(src), tmp_path / "out.wav")
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=sample_rate,channels", "-of", "json", str(dst)],
                         capture_output=True, text=True, check=True)
    stream = json.loads(out.stdout)["streams"][0]
    assert stream["sample_rate"] == "16000" and stream["channels"] == 1


def test_transcribe_silence_returns_empty(tmp_path):
    import wave, struct
    p = tmp_path / "silence.wav"
    with wave.open(str(p), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\x00\x00" * 16000 * 2)
    model = wb.load_model()
    res = wb.transcribe(model, p)
    assert res["text"] == "" and res["language"] == ""
