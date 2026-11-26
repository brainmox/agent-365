#!/usr/bin/env python3
"""Score the "latency picks the tokenizer" method against known ground truth.

  python3 analyze.py prompts.json timing-*.json > results.json

For each served model (whose real tokenizer we know) and each candidate tokenizer:
  global_rho  - Spearman rho between the candidate's token counts and latency, all prompts.
  bin_rho     - the published method: Spearman rho inside 2,000-token bins (binned on the
                mean count over all candidates, so no candidate gets its own bins),
                averaged with bin sizes as weights; 95% interval and "true tokenizer ranks
                first" rate from 2,000 passage-bootstrap resamples (passages, not prompts,
                are resampled because windows of one passage are not independent).
Both for client wall-clock latency and the server's own prompt_ms.

hosted_sim: what a hosted API would show. Latency = 77 ms + 9.75 ms per 1,000 true tokens
  + exponential jitter with scale 12.8 ms (p99 - p50 = 50 ms). The 77 ms intercept, the
  slope and the 50 ms gap are read off the Jev post's prose figures (median 77 -> 155 ms
  across its 2,000-token buckets, p50-p99 gap 47-58 ms); the exponential shape is my
  assumption. True tokens come from the server's prompt_n. Reported: how often the true
  tokenizer ranks first by bin_rho, over 300 jitter draws, at 600 / 2,000 / 10,000 prompts
  (above 600, prompts are drawn with replacement, each draw with fresh jitter: more
  requests over the same prompt mix, not more distinct content), plus a run with half and
  double the jitter.
hosted_sim_every_tokenizer: the same simulation with each candidate in turn as the hidden
  tokenizer (true counts from its Hugging Face tokenizer, no server).
hosted_sim_english_only: the same, using only English prose prompts.
"""
import json, sys
import numpy as np
from scipy.stats import rankdata

BIN = 2000
RNG = np.random.default_rng(365)


def spearman_cols(X, y):
    """Spearman rho of each column of X against y."""
    rx = np.apply_along_axis(rankdata, 0, X)
    ry = rankdata(y)
    rx -= rx.mean(0); ry = ry - ry.mean()
    den = np.sqrt((rx ** 2).sum(0) * (ry ** 2).sum())
    with np.errstate(invalid='ignore', divide='ignore'):
        return (rx * ry[:, None]).sum(0) / den


def bin_rho(C, y, binkey):
    tot, acc = 0, np.zeros(C.shape[1])
    for b in np.unique(binkey):
        m = binkey == b
        if m.sum() < 10:
            continue
        r = spearman_cols(C[m], y[m])
        if np.isnan(r).any():
            continue
        acc += m.sum() * r; tot += m.sum()
    return acc / tot


def first_rate(scores, true_idx):
    return float(np.mean(np.argmax(scores, 1) == true_idx))


def main():
    pr = json.load(open(sys.argv[1]))
    T, P = pr['tokenizers'], pr['prompts']
    C = np.array([[p['counts'][t] for t in T] for p in P], float)
    binkey = (C.mean(1) // BIN).astype(int)
    passages = np.array([p['passage'] for p in P])
    upass = np.unique(passages)
    pidx = {u: np.where(passages == u)[0] for u in upass}
    out = dict(tokenizers=T, n_prompts=len(P), n_passages=len(upass), models={})
    for f in sys.argv[2:]:
        tm = json.load(open(f))
        label = tm['label']; ti = T.index(label)
        R = {r['id']: r for r in tm['rows']}
        ids = np.array(sorted(R))
        assert len(ids) == len(P)
        res = dict(model=tm['model'], true_tokenizer=label,
                   max_cache_n=max(r['cache_n'] or 0 for r in tm['rows']),
                   server_count_minus_hf=sorted({R[i]['prompt_n'] - P[i]['counts'][label] for i in ids}))
        for metric in ('wall_ms', 'prompt_ms'):
            y = np.array([R[i][metric] for i in ids])
            g = spearman_cols(C, y); b = bin_rho(C, y, binkey)
            boots = []
            for _ in range(2000):
                pick = np.concatenate([pidx[u] for u in RNG.choice(upass, len(upass))])
                boots.append(bin_rho(C[pick], y[pick], binkey[pick]))
            boots = np.array(boots)
            lo, hi = np.percentile(boots, [2.5, 97.5], axis=0)
            order = np.argsort(-b)
            res[metric] = dict(
                global_rho={t: round(float(g[k]), 4) for k, t in enumerate(T)},
                bin_rho={t: round(float(b[k]), 4) for k, t in enumerate(T)},
                bin_rho_ci95={t: [round(float(lo[k]), 4), round(float(hi[k]), 4)] for k, t in enumerate(T)},
                ranking=[T[k] for k in order],
                global_winner=T[int(np.argmax(g))], bin_winner=T[int(order[0])],
                true_first_rate_bootstrap=first_rate(boots, ti),
                runner_up=T[int(order[1])] if order[0] == ti else T[int(order[0])])
        true_n = np.array([R[i]['prompt_n'] for i in ids], float)
        sim = {}
        for scale_name, theta in (('jitter_x0.5', 6.4), ('jitter_x1', 12.8), ('jitter_x2', 25.6)):
            for N in ((600, 2000, 10000) if scale_name == 'jitter_x1' else (600, 10000)):
                wins, rivals = 0, {}
                for _ in range(300):
                    pick = np.arange(len(P)) if N == len(P) else RNG.integers(0, len(P), N)
                    y = 77 + 0.00975 * true_n[pick] + RNG.exponential(theta, N)
                    s = bin_rho(C[pick], y, binkey[pick])
                    w = int(np.argmax(s)); wins += w == ti
                    if w != ti:
                        rivals[T[w]] = rivals.get(T[w], 0) + 1
                sim[f'{scale_name}_n{N}'] = dict(true_first_rate=round(wins / 300, 3), wrong_winners=rivals)
        res['hosted_sim'] = sim
        out['models'][label] = res
    # Same simulation with every candidate in turn as the hidden model's tokenizer
    # (true counts = that tokenizer's Hugging Face counts; no server involved).
    hyp = {}
    for ti, t in enumerate(T):
        row = {}
        for N in (600, 2000, 10000):
            wins, rivals = 0, {}
            for _ in range(300):
                pick = np.arange(len(P)) if N == len(P) else RNG.integers(0, len(P), N)
                y = 77 + 0.00975 * C[pick, ti] + RNG.exponential(12.8, N)
                w = int(np.argmax(bin_rho(C[pick], y, binkey[pick])))
                wins += w == ti
                if w != ti:
                    rivals[T[w]] = rivals.get(T[w], 0) + 1
            row[f'n{N}'] = dict(true_first_rate=round(wins / 300, 3), wrong_winners=rivals)
        hyp[t] = row
    out['hosted_sim_every_tokenizer'] = hyp
    # Same again, restricted to English prose prompts (English Wikipedia + Markdown docs),
    # where tokenizers agree most.
    eng = np.array([p['passage'].startswith(('wiki-en', 'md-')) for p in P])
    Ce, be = C[eng], binkey[eng]
    hyp_e = {}
    for ti, t in enumerate(T):
        row = {}
        for N in (int(eng.sum()), 2000, 10000):
            wins = 0
            for _ in range(300):
                pick = np.arange(len(Ce)) if N == len(Ce) else RNG.integers(0, len(Ce), N)
                y = 77 + 0.00975 * Ce[pick, ti] + RNG.exponential(12.8, N)
                wins += int(np.argmax(bin_rho(Ce[pick], y, be[pick]))) == ti
            row[f'n{N}'] = round(wins / 300, 3)
        hyp_e[t] = row
    out['hosted_sim_english_only'] = dict(n_prompts=int(eng.sum()), true_first_rate=hyp_e)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
