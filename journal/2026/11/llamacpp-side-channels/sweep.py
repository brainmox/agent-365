#!/usr/bin/env python3
"""Where does the KV-cache message board start to show up in Bob's logprobs?

For mailbox k, Alice writes SYSTEM + mailbox + n characters of filler (so the
mailbox tokens are computed in a batch of roughly that many tokens); Bob then reads
SYSTEM + mailbox + QUESTION and reuses Alice's cached mailbox. The baseline for
each mailbox is computed alone on a separate fresh server.

Usage: python3 sweep.py SERVER_BIN MODEL_GGUF [extra server args...]
"""
import json, os, sys

BIN, MODEL = sys.argv[1], sys.argv[2]
EXTRA = sys.argv[3:]
sys.argv = ['probe', BIN, MODEL, 'sweep']
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe as P  # noqa: E402

NS = [0, 8, 16, 24, 32, 40, 48, 64, 96, 128, 192, 256, 384, 512, 1024, 1600]


def main():
    p = P.start(1, EXTRA)
    try:
        base = {k: P.complete(P.read_prompt(k), cache_prompt=False) for k in range(len(NS))}
    finally:
        P.stop(p)
    p = P.start(1, EXTRA)
    out = []
    try:
        for k, n in enumerate(NS):
            w = P.complete(P.SYSTEM + P.mailbox(k) + P.DOC[:n * 4])
            r = P.complete(P.read_prompt(k))
            out.append(dict(filler_chars=n * 4, write_tokens=w['prompt_n'] + w['cache_n'],
                            read_cache_n=r['cache_n'],
                            bitwise_equal_to_alone=r['probs'] == base[k]['probs'],
                            max_abs_logprob_diff=P.max_abs_diff(r['probs'], base[k]['probs'])))
    finally:
        P.stop(p)
    print(json.dumps(dict(model=os.path.basename(MODEL), server_args=EXTRA, rows=out)))


if __name__ == '__main__':
    main()
