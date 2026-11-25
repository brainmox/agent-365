#!/usr/bin/env python3
"""API-level checks of the KV-cache message board on llama-server:
  1. which cache_prompt combinations let Bob reuse Alice's prompt, with and without
     the server flag --no-cache-prompt;
  2. whether the OpenAI-compatible /v1/chat/completions endpoint exposes the same
     signal (usage.prompt_tokens_details.cached_tokens);
  3. whether giving Alice and Bob different API keys (--api-key a,b) isolates them.

Usage: python3 api_checks.py SERVER_BIN MODEL_GGUF > api_checks.json
"""
import json, os, sys, urllib.request

BIN, MODEL = sys.argv[1], sys.argv[2]
sys.argv = ['probe', BIN, MODEL, 'api']
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe as P  # noqa: E402


def post(path, body, key=None):
    h = {'Content-Type': 'application/json'}
    if key:
        h['Authorization'] = 'Bearer ' + key
    return json.loads(urllib.request.urlopen(urllib.request.Request(
        f'http://127.0.0.1:{P.PORT}{path}', json.dumps(body).encode(), h), timeout=600).read())


def raw(prompt, cache_prompt):
    b = dict(prompt=prompt, n_predict=1, temperature=0)
    if cache_prompt is not None:
        b['cache_prompt'] = cache_prompt
    return post('/completion', b)['timings']['cache_n']


def chat(user, key=None):
    msgs = [{'role': 'system', 'content': P.SYSTEM.strip()}, {'role': 'user', 'content': user}]
    d = post('/v1/chat/completions', dict(messages=msgs, max_tokens=1, temperature=0), key)
    return d['usage']['prompt_tokens_details']['cached_tokens']


def flags():
    combos = [(None, None), (True, True), (None, True), (True, None), (False, True),
              (False, None), (False, False)]
    out = {}
    for extra in ([], ['--no-cache-prompt']):
        p = P.start(1, extra)
        rows = []
        try:
            for i, (a, b) in enumerate(combos):
                k = 200 + i
                raw(P.SYSTEM + P.mailbox(k) + P.DOC, a)          # Alice writes mailbox k
                rows.append(dict(alice_cache_prompt=a, bob_cache_prompt=b,
                                 bob_cache_n=raw(P.read_prompt(k), b),
                                 shared_prefix_tokens_if_reused='system prompt + mailbox'))
        finally:
            P.stop(p)
        out[' '.join(extra) or 'default'] = rows
    return out


def board_chat(extra, keys=(None, None), rounds=8):
    p = P.start(4, extra)
    rows = []
    try:
        for i in range(rounds):
            k, wrote = 300 + i, i % 2 == 0
            chat((P.mailbox(k) if wrote else P.mailbox(k + 100)) + P.DOC, keys[0])
            rows.append(dict(wrote=wrote, bob_cached_tokens=chat(P.mailbox(k) + P.QUESTION, keys[1])))
    finally:
        P.stop(p)
    w = [r['bob_cached_tokens'] for r in rows if r['wrote']]
    n = [r['bob_cached_tokens'] for r in rows if not r['wrote']]
    return dict(rounds=rows, write=[min(w), max(w)], nowrite=[min(n), max(n)],
                separates=max(n) < min(w))


def main():
    print(json.dumps(dict(
        model=os.path.basename(MODEL),
        cache_prompt_flags=flags(),
        openai_chat_4slots=board_chat([]),
        openai_chat_4slots_separate_api_keys=board_chat(['--api-key', 'alice-key,bob-key'],
                                                        ('alice-key', 'bob-key')),
    ), indent=1))


if __name__ == '__main__':
    main()
