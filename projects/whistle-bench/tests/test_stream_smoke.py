import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_stream_silence_commits_no_words():
    """The streaming path on synthetic silent chunks: one dict per chunk plus
    a tail, no committed words, no invented pending tail. Mirrors the card's
    silence guarantee for the stream API documented in the card's Oct 10
    README commit."""
    import numpy as np
    from needle import Whistle

    w = Whistle()
    chunks = [np.zeros(16000, dtype=np.float32) for _ in range(4)]
    out = list(w.stream(chunks))
    assert len(out) == 5  # 4 chunks + 1 tail
    assert all(o["text"] == "" for o in out)
    assert all(o["pending"] == "" for o in out)
    received = [o["received"] for o in out]
    assert received == sorted(received) and received[-1] == 4.0
    assert all("pass_ms" in o for o in out)
