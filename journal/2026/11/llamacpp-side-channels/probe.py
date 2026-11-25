#!/usr/bin/env python3
"""Do the two inference-server side channels from Deshpande & Africa
("Models Can Communicate via Inference Servers Despite Being Sandboxed",
LessWrong, 2026-11-19; measured on vLLM/SGLang/LMDeploy/TensorRT-LLM on GPUs)
exist on llama.cpp's llama-server running on a CPU?

Two parties share one llama-server. "Alice" may send a write; "Bob" then sends a
read. Bob sees only what the server's /completion endpoint returns to him.
For each condition the script records what Bob can observe:

  numeric   - Bob's top-k next-token logprobs (bitwise compared with a baseline)
  metadata  - fields the server returns to Bob: tokens_cached, timings.cache_n
  timing    - timings.prompt_ms

Usage: python3 probe.py SERVER_BIN MODEL_GGUF LABEL [extra server args...]
Prints one JSON object (results for that model and server configuration).
"""
import json, os, statistics, subprocess, sys, threading, time, urllib.request

BIN, MODEL, LABEL = sys.argv[1], sys.argv[2], sys.argv[3]
EXTRA = sys.argv[4:]
PORT = 8093
HERE = os.path.dirname(os.path.abspath(__file__))
DOC = open(os.path.join(HERE, 'document.txt')).read()  # 1,627-token synthetic filler (Qwen3 tokenizer)

SYSTEM = "You are a helpful assistant that answers questions about documents.\n"
MAILBOX = "Mailbox 7: the heron waits by the quiet copper gate.\n"
QUESTION = "Question: what colour is the gate? Answer:"


def start(np_slots, extra):
    p = subprocess.Popen([BIN, '-m', MODEL, '-t', '6', '-c', '16384', '-np', str(np_slots),
                          '--port', str(PORT), '--seed', '1'] + extra,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            if b'ok' in urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health', timeout=2).read():
                return p
        except Exception:
            pass
        time.sleep(0.5)
    p.kill()
    raise RuntimeError('server did not start')


def stop(p):
    p.terminate()
    p.wait(timeout=30)


def complete(prompt, n_predict=1, cache_prompt=True, n_probs=10):
    body = json.dumps(dict(prompt=prompt, n_predict=n_predict, n_probs=n_probs,
                           temperature=0, cache_prompt=cache_prompt,
                           post_sampling_probs=False)).encode()
    r = urllib.request.urlopen(urllib.request.Request(
        f'http://127.0.0.1:{PORT}/completion', body,
        {'Content-Type': 'application/json'}), timeout=600)
    d = json.loads(r.read())
    probs = [[(t['id'], t['logprob']) for t in step['top_logprobs']]
             for step in d['completion_probabilities']]
    return dict(probs=probs, cache_n=d['timings']['cache_n'],
                tokens_cached=d['tokens_cached'], prompt_ms=d['timings']['prompt_ms'],
                prompt_n=d['timings']['prompt_n'], slot=d.get('id_slot'))


def max_abs_diff(a, b):
    """Largest |logprob difference| over all positions and shared token ids."""
    m = 0.0
    for sa, sb in zip(a, b):
        da, db = dict(sa), dict(sb)
        for k in da.keys() & db.keys():
            m = max(m, abs(da[k] - db[k]))
    return m


BOB = SYSTEM + MAILBOX + QUESTION
WORDS = ['heron', 'lantern', 'copper', 'willow', 'anchor', 'meadow', 'falcon', 'quartz',
         'harbor', 'ember', 'cedar', 'violet']


def mailbox(k):
    """A fresh mailbox per round, so Bob never reads the same mailbox twice."""
    return f"Mailbox {k}: the {WORDS[k % 12]} waits by the quiet {WORDS[(k * 5 + 3) % 12]} gate.\n"


def read_prompt(k):
    return SYSTEM + mailbox(k) + QUESTION


def message_board(np_slots, extra, rounds=12):
    """Round k: Alice either writes mailbox k (inside a long prompt, so it is computed
    in a 512-token ubatch) or sends equal work with a different mailbox. Bob then
    reads mailbox k once. Baselines for each mailbox, computed alone, come from a
    separate fresh server so they cannot seed this server's caches."""
    p = start(1, extra)
    try:
        base = {k: complete(read_prompt(k), cache_prompt=False) for k in range(rounds)}
        again = {k: complete(read_prompt(k), cache_prompt=False) for k in range(rounds)}
    finally:
        stop(p)
    p = start(np_slots, extra)
    try:
        rows = []
        for k in range(rounds):
            wrote = k % 2 == 0
            first = mailbox(k) if wrote else mailbox(k + 100)
            a = complete(SYSTEM + first + DOC)
            r = complete(read_prompt(k))
            rows.append(dict(round=k, wrote=wrote, alice_slot=a['slot'], cache_n=r['cache_n'],
                             tokens_cached=r['tokens_cached'], prompt_n=r['prompt_n'],
                             prompt_ms=r['prompt_ms'], slot=r['slot'],
                             bitwise_equal_to_alone=r['probs'] == base[k]['probs'],
                             top1_equal_to_alone=r['probs'][0][0][0] == base[k]['probs'][0][0][0],
                             max_abs_logprob_diff=max_abs_diff(r['probs'], base[k]['probs'])))
        return dict(baseline_deterministic=all(base[k]['probs'] == again[k]['probs'] for k in base),
                    rounds=rows)
    finally:
        stop(p)


def step_size(extra, trials=4):
    """Bob decodes 8 tokens alone, then while Alice's long prompt is being processed."""
    p = start(2, extra)
    try:
        alone = [complete(BOB, n_predict=8, cache_prompt=False) for _ in range(2)]
        out = []
        for i in range(trials):
            box = {}
            doc = SYSTEM + f"Document {i}.\n" + DOC + DOC   # fresh, ~3,260 tokens
            t = threading.Thread(target=lambda: box.update(a=complete(doc, cache_prompt=False)))
            t.start()
            time.sleep(0.4)
            b = complete(BOB, n_predict=8, cache_prompt=False)
            t.join()
            out.append(dict(bitwise_equal_to_alone=b['probs'] == alone[0]['probs'],
                            max_abs_logprob_diff=max_abs_diff(b['probs'], alone[0]['probs']),
                            bob_prompt_ms=b['prompt_ms'], alice_prompt_ms=box['a']['prompt_ms']))
        return dict(deterministic_alone=alone[0]['probs'] == alone[1]['probs'], trials=out)
    finally:
        stop(p)


def main():
    res = dict(label=LABEL, model=os.path.basename(MODEL), server_args=EXTRA)
    res['message_board_1slot'] = message_board(1, EXTRA)
    res['message_board_4slots'] = message_board(4, EXTRA)
    res['step_size_2slots'] = step_size(EXTRA)
    print(json.dumps(res))


if __name__ == '__main__':
    main()
