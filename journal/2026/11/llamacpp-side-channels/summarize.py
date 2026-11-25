#!/usr/bin/env python3
"""Summarise probe.py and sweep.py outputs into results.json and a printed table.

Usage: python3 summarize.py OUT_DIR > results.json
"""
import json, os, sys

D = sys.argv[1]


def rng(xs):
    return [min(xs), max(xs)] if xs else None


def board(b):
    w = [r for r in b['rounds'] if r['wrote']]
    n = [r for r in b['rounds'] if not r['wrote']]
    sep = (max(r['cache_n'] for r in n) < min(r['cache_n'] for r in w))
    tsep = (max(r['prompt_ms'] for r in w) < min(r['prompt_ms'] for r in n))
    return dict(
        rounds=len(b['rounds']),
        baseline_deterministic=b['baseline_deterministic'],
        cache_n_write=rng([r['cache_n'] for r in w]),
        cache_n_nowrite=rng([r['cache_n'] for r in n]),
        cache_n_separates=sep,
        prompt_ms_write=rng([round(r['prompt_ms'], 1) for r in w]),
        prompt_ms_nowrite=rng([round(r['prompt_ms'], 1) for r in n]),
        prompt_ms_separates=tsep,
        bob_on_alices_slot_when_written=sum(r['slot'] == r['alice_slot'] for r in w),
        numeric_equal_alone_write=sum(r['bitwise_equal_to_alone'] for r in w),
        numeric_equal_alone_nowrite=sum(r['bitwise_equal_to_alone'] for r in n),
        top1_changed_write=sum(not r['top1_equal_to_alone'] for r in w),
        max_abs_logprob_diff_write=max(r['max_abs_logprob_diff'] for r in w),
        max_abs_logprob_diff_nowrite=max(r['max_abs_logprob_diff'] for r in n),
    )


def main():
    out = {'probe': {}, 'sweep': {}}
    for f in sorted(os.listdir(D)):
        d = json.load(open(os.path.join(D, f)))
        name = f[:-5]
        if 'rows' in d:
            out['sweep'][name] = dict(server_args=d['server_args'], model=d['model'], rows=[
                [r['write_tokens'], r['bitwise_equal_to_alone'], round(r['max_abs_logprob_diff'], 4)]
                for r in d['rows']])
            continue
        s = d['step_size_2slots']
        out['probe'][name] = dict(
            model=d['model'], server_args=d['server_args'],
            board_1slot=board(d['message_board_1slot']),
            board_4slots=board(d['message_board_4slots']),
            step_size=dict(trials=len(s['trials']), deterministic_alone=s['deterministic_alone'],
                           bitwise_equal_when_concurrent=sum(t['bitwise_equal_to_alone'] for t in s['trials']),
                           bob_prompt_ms=rng([round(t['bob_prompt_ms']) for t in s['trials']])))
    json.dump(out, sys.stdout, indent=1)
    print()
    for n, p in out['probe'].items():
        for k in ('board_1slot', 'board_4slots'):
            b = p[k]
            print(f"{n:20s} {k:12s} cache_n W{b['cache_n_write']} N{b['cache_n_nowrite']} sep={b['cache_n_separates']} "
                  f"ms W{b['prompt_ms_write']} N{b['prompt_ms_nowrite']} sep={b['prompt_ms_separates']} "
                  f"sameslot={b['bob_on_alices_slot_when_written']} numEq W{b['numeric_equal_alone_write']} "
                  f"N{b['numeric_equal_alone_nowrite']} top1chg={b['top1_changed_write']} "
                  f"maxd W{b['max_abs_logprob_diff_write']:.3f} N{b['max_abs_logprob_diff_nowrite']:.3f}",
                  file=sys.stderr)
        print(f"{n:20s} step {p['step_size']}", file=sys.stderr)


if __name__ == '__main__':
    main()
