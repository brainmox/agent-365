#!/usr/bin/env python3
"""Count descriptive content in every release of Arm's open (BSD-3-Clause)
AARCHMRS package, as mirrored at git.kernel.org/.../maz/AARCHMRS.git.

Question: did any open release ever carry ASL pseudocode, titles, or prose
(which would mean something was later withdrawn)?

Usage: python3 release_history.py /path/to/AARCHMRS-clone > release_history.json
"""
import json, subprocess, sys

REPO = sys.argv[1]


def walk(o, f):
    st = [o]
    while st:
        x = st.pop()
        f(x)
        if isinstance(x, dict):
            st.extend(x.values())
        elif isinstance(x, list):
            st.extend(x)


def show(rev, path):
    return json.loads(subprocess.run(['git', '-C', REPO, 'show', f'{rev}:{path}'],
                                     capture_output=True, check=True).stdout)


def main():
    log = subprocess.run(['git', '-C', REPO, 'log', '--reverse', '--format=%h %ad %s',
                          '--date=short'], capture_output=True, text=True,
                         check=True).stdout.split('\n')
    out = []
    for line in filter(None, log):
        rev, date, subject = line.split(' ', 2)
        I, R = show(rev, 'Instructions.json'), show(rev, 'Registers.json')
        ops = I['operations'].values()
        c = dict(commit=rev, date=date, release=subject,
                 operations=len(ops),
                 operations_with_asl=sum(1 for o in ops if o.get('operation')
                                         and o['operation'].strip() != '// Not specified'),
                 operation_titles=sum(1 for o in ops if o.get('title')),
                 operation_briefs=sum(1 for o in ops if o.get('brief') not in (None, '', '.')),
                 registers=len(R),
                 register_titles=sum(1 for r in R if r.get('title')),
                 register_purposes=sum(1 for r in R if r.get('purpose')))
        n = {'instructions': 0, 'with_decode': 0, 'descriptions': 0, 'value_meanings': 0}

        def f(x):
            if isinstance(x, dict):
                t = x.get('_type')
                if t == 'Instruction.Instruction':
                    n['instructions'] += 1
                    n['with_decode'] += x.get('decode') is not None
                elif t == 'Description' and (x.get('before') or x.get('after')):
                    n['descriptions'] += 1
                elif t == 'Values.Value' and x.get('meaning'):
                    n['value_meanings'] += 1
        walk(I, f)
        walk(R, f)
        c.update(n)
        c['license'] = R[0]['_meta'].get('license', {}).get('info')
        out.append(c)
        print(json.dumps(c), file=sys.stderr)
    json.dump(out, sys.stdout, indent=1)
    print()


if __name__ == '__main__':
    main()
