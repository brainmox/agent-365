#!/usr/bin/env python3
"""Ground-truth test of the "latency reveals the tokenizer" method.

Serve a model whose tokenizer we know with llama-server, time many prompts, and ask
which candidate tokenizer's token counts best explain the latency, the way a black-box
auditor would. Repeat for several served models.

  python3 fingerprint.py prompts SERVER_BIN TOKDIR CORPUSDIR > prompts.json
  python3 fingerprint.py time    SERVER_BIN MODEL.gguf prompts.json label > timing-label.json

prompts: cuts windows from every passage in CORPUSDIR (one passage = one text file),
         with lengths spread evenly, and counts tokens with every tokenizer in TOKDIR.
time:    sends every prompt once (shuffled order, one request in flight, n_predict=1,
         cache_prompt=false), records client wall-clock latency and the server's own
         prompt_n / prompt_ms / cache_n.
Analysis lives in analyze.py. Standard library plus `tokenizers` (prompts step only).
"""
import json, os, random, subprocess, sys, time, urllib.request

PORT = 8097
WINDOWS_PER_PASSAGE = 12
TOK_RANGE = (256, 3072)   # target length, in mean-tokenizer tokens


def build_prompts(tokdir, corpusdir):
    from tokenizers import Tokenizer
    toks = {os.path.splitext(f)[0]: Tokenizer.from_file(os.path.join(tokdir, f))
            for f in sorted(os.listdir(tokdir)) if f.endswith('.json')}
    rng = random.Random(2026)
    prompts = []
    for fn in sorted(os.listdir(corpusdir)):
        text = open(os.path.join(corpusdir, fn), encoding='utf-8', errors='replace').read()
        sample = text[:20000]
        # chars per token for this passage, averaged over all tokenizers (tokenizer-neutral)
        cpt = sum(len(sample) / len(t.encode(sample, add_special_tokens=False).ids)
                  for t in toks.values()) / len(toks)
        for _ in range(WINDOWS_PER_PASSAGE):
            n_chars = int(rng.uniform(*TOK_RANGE) * cpt)
            if n_chars >= len(text):
                n_chars = len(text) - 1
            start = rng.randrange(0, len(text) - n_chars)
            body = text[start:start + n_chars]
            counts = {k: len(t.encode(body, add_special_tokens=False).ids) for k, t in toks.items()}
            prompts.append(dict(id=len(prompts), passage=fn, chars=len(body), counts=counts, text=body))
    return dict(tokenizers=sorted(toks), prompts=prompts)


def post(body):
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}/completion', json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'})
    t0 = time.perf_counter()
    d = json.loads(urllib.request.urlopen(req, timeout=900).read())
    return (time.perf_counter() - t0) * 1000, d


def start_server(binary, model):
    p = subprocess.Popen([binary, '-m', model, '-t', '6', '-c', '8192', '-np', '1',
                          '--port', str(PORT), '--cache-ram', '0'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(300):
        try:
            if b'ok' in urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health', timeout=2).read():
                return p
        except Exception:
            pass
        time.sleep(1)
    p.kill()
    raise RuntimeError('server did not start')


def time_prompts(binary, model, prompts_file, label):
    P = json.load(open(prompts_file))['prompts']
    order = list(range(len(P)))
    random.Random(label).shuffle(order)
    p = start_server(binary, model)
    rows = []
    try:
        for _ in range(5):   # warm-up, discarded
            post(dict(prompt=P[0]['text'], n_predict=1, cache_prompt=False))
        for i in order:
            ms, d = post(dict(prompt=P[i]['text'], n_predict=1, cache_prompt=False, temperature=0))
            t = d['timings']
            rows.append(dict(id=i, wall_ms=round(ms, 3), prompt_n=t['prompt_n'],
                             prompt_ms=round(t['prompt_ms'], 3), cache_n=t.get('cache_n')))
    finally:
        p.kill(); p.wait()
    return dict(label=label, model=os.path.basename(model), n=len(rows), rows=rows)


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'prompts':
        print(json.dumps(build_prompts(sys.argv[3], sys.argv[4]), ensure_ascii=False))
    elif mode == 'time':
        print(json.dumps(time_prompts(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])))
