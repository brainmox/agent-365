"""How much of the Riemann Hypothesis Lean release's unused code can plain text analysis find?

Input: the original release (https://alpo.ge/lean.tar.gz.part01 ... part14, Nov 20 2026), extracted,
and optionally James Shore's kernel-closure dataset (rh-proof-dependencies v0.2.1, decls.csv.gz).

Method (no Lean, no build):
  1. Split every .lean file into top-level declarations (theorem/lemma/def/abbrev/instance/structure/
     class/inductive/opaque/axiom/example), tracking namespaces and `_root_.` names.
  2. Roots: the five theorems in Main.lean (whole Main/Statements modules), every instance, every
     declaration with an attribute, every type (structure/class/inductive), every example, and every
     name in notation/macro/syntax/elab/attribute/alias/export/run_cmd/... commands (whole command).
  3. Reach: a declaration is reached if any contiguous dotted piece of any identifier in a reached
     declaration's text equals any suffix of its full name. This over-approximates Lean name
     resolution (it ignores scoping, and dot notation `h.trans` reaches every `*.trans`), so
     "unreached" is meant as a lower bound on unused code.
  4. If the kernel dataset is given, check that claim declaration by declaration and explain misses.

Usage:  python3 text_reach.py SRC_DIR [--kernel decls.csv.gz] [--json out.json]
"""
from __future__ import annotations

import argparse
import collections
import csv
import gzip
import json
import os
import re
import sys
from multiprocessing import Pool

KW = r'(?:theorem|lemma|def|abbrev|instance|structure|class|inductive|opaque|axiom|example)'
MOD = (r'(?:(?:@\[[^\]]*\]\s*)|(?:private|protected|noncomputable|partial|unsafe|nonrec|scoped|local)\s+'
       r'|(?:set_option\s+\S+\s+\S+\s+in\s+))*')
DECL = re.compile(r'^(' + MOD + r')(' + KW + r')\b\s*([^\s:(\[{]*)', re.M)
TOK = re.compile(r"[\w'!?«».\u2080-\u209c\u1d62-\u1d6a]+")  # Lean identifier characters, dotted
NSEV = re.compile(r'^[ \t]*(namespace|end|section)\b[ \t]*([^\s]*)', re.M)
ROOTCMD = re.compile(r'^\s*(?:(?:local|scoped)\s+)?(?:alias|run_cmd|cpt_copy_thms|unseal|macro|syntax|notation\w*|'
                     r'infix|infixl|infixr|prefix|postfix|elab|macro_rules|elab_rules|initialize|deriving|'
                     r'attribute|export|register_\w+|add_decl_doc)\b', re.M)
WRAPPER = re.compile(r"^\s*first\s*\|\s*exact\s+@([\w.'«»]+)\s*\|\s*exact\s+\1\b", re.M)
SRC = ''


def pieces(tok: str) -> set[str]:
    parts = [p for p in tok.replace('_root_.', '').split('.') if p]
    return {'.'.join(parts[i:j]) for i in range(len(parts)) for j in range(i + 1, len(parts) + 1)}


def suffixes(full: str) -> list[str]:
    parts = [p for p in full.split('.') if p]
    return ['.'.join(parts[i:]) for i in range(len(parts))]


def parse(path: str):
    t = open(path, encoding='utf-8', errors='replace').read()
    mod = os.path.relpath(path, SRC)[:-5].replace(os.sep, '.')
    events = sorted([(m.start(), 0, m) for m in NSEV.finditer(t)] + [(m.start(), 1, m) for m in DECL.finditer(t)],
                    key=lambda x: x[0])
    stack, decls = [], []
    for pos, k, m in events:
        if k == 0:
            kind, name = m.group(1), m.group(2)
            if kind in ('namespace', 'section'):
                stack.append((kind, name))
            elif stack:
                stack.pop()
        else:
            decls.append((pos, m, '.'.join(n for kk, n in stack if kk == 'namespace')))
    out = []
    for i, (pos, m, ns) in enumerate(decls):
        body = t[pos:decls[i + 1][0] if i + 1 < len(decls) else len(t)]
        mods, kw, name = m.group(1), m.group(2), m.group(3).rstrip('.')
        full = name[7:] if name.startswith('_root_.') else (ns + '.' + name if name and ns else name)
        root = kw in ('instance', 'structure', 'class', 'inductive', 'example', 'axiom') or '@[' in mods or not name
        nl = body.count('\n') or 1
        short = full.split('.')[-1] if full else ''
        norm = ' '.join(body.split())
        if short:
            norm = re.sub(r'(?<![\w.])(?:[\w.]*\.)?' + re.escape(short) + r'(?![\w])', '§', norm)
        norm = re.sub(r'^.*?\b' + KW + r'\b', '', norm, count=1)
        h = hash(norm) if nl <= 400 else None
        wr = bool(WRAPPER.search(body)) and nl <= 8
        out.append((full, kw, root, nl, ' '.join(set(TOK.findall(body))), h, wr))
    rcmd = []
    for m in ROOTCMD.finditer(t):  # whole command incl. indented continuation lines
        e = m.start()
        while True:
            e = t.find('\n', e + 1)
            if e < 0 or e + 1 >= len(t) or not t[e + 1].isspace() or t[e + 1] == '\n':
                break
        rcmd.append(t[m.start(): e if e > 0 else len(t)])
    flags = (len(re.findall(r'\bsorry\b', t)), len(re.findall(r'^\s*axiom\b', t, re.M)), t.count('native_decide'))
    return mod, t.count('\n'), out, ' '.join(tk for s in rcmd for tk in TOK.findall(s)), flags


def main(argv=None) -> int:
    global SRC
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('src')
    ap.add_argument('--kernel', help="rh-proof-dependencies decls.csv.gz")
    ap.add_argument('--json')
    a = ap.parse_args(argv)
    SRC = os.path.abspath(a.src)
    paths = sorted(os.path.join(r, f) for r, _, fs in os.walk(SRC) for f in fs if f.endswith('.lean'))
    with Pool(min(8, os.cpu_count() or 1)) as pool:
        parsed = pool.map(parse, paths, chunksize=500)
    R: dict = {}
    D, mod_of, filelines, roottext = [], [], {}, []
    fl = [0, 0, 0]
    for mod, nl, res, rt, flags in parsed:
        filelines[mod] = nl
        roottext.append(rt)
        fl = [x + y for x, y in zip(fl, flags)]
        for d in res:
            D.append(d)
            mod_of.append(mod)
    del parsed
    total = sum(filelines.values())
    R['files'], R['lines_newline_count'], R['declarations'] = len(filelines), total, len(D)
    R['text_flags'] = dict(zip(('sorry_tokens', 'axiom_commands', 'native_decide'), fl))

    idx = collections.defaultdict(list)
    for i, d in enumerate(D):
        for s in suffixes(d[0]):
            idx[s].append(i)
    seen = bytearray(len(D))
    stack = []

    def mark(i):
        if not seen[i]:
            seen[i] = 1
            stack.append(i)

    for i, d in enumerate(D):
        if d[2] or mod_of[i] in ('Main', 'Statements'):
            mark(i)
    done = set()

    def expand(text):
        for tk in text.split():
            for p in pieces(tk):
                if p in done:
                    continue
                done.add(p)
                for j in idx.get(p, ()):
                    mark(j)

    for s in roottext:
        expand(s)
    del roottext
    while stack:
        expand(D[stack.pop()][4])
    D = [d[:4] + d[5:] for d in D]  # drop token text
    un = [i for i in range(len(D)) if not seen[i]]
    R['unreached'] = {'declarations': len(un), 'lines': sum(D[i][3] for i in un)}

    grp = collections.defaultdict(list)
    for i, d in enumerate(D):
        if d[0] and d[4] is not None and d[1] != 'example' and not d[5]:
            grp[d[4]].append(i)
    dup = {i for v in grp.values() if len(v) > 1 for i in v[1:]}
    cat, catn = collections.Counter(), collections.Counter()
    for i, d in enumerate(D):
        k = ('example' if d[1] == 'example' else 'unreached' if not seen[i] else 'wrapper' if d[5]
             else 'duplicate' if i in dup else 'rest')
        cat[k] += d[3]
        catn[k] += 1
    cat['outside_declarations'] = total - sum(d[3] for d in D)
    R['decomposition_lines'] = dict(cat)
    R['decomposition_decls'] = dict(catn)

    if a.kernel:
        mine = collections.defaultdict(list)
        for i, d in enumerate(D):
            if d[0]:
                mine[(mod_of[i], d[0].split('.')[-1])].append(i)
        rows = []
        with gzip.open(a.kernel, 'rt') as f:
            for r in csv.DictReader(f):
                if r['origin'] == 'project':
                    rows.append((r['module'], r['decl'], r['in_cone'] == 'true', int(r['lines'])))
        S = collections.defaultdict(list)
        for m, full, cone, n in rows:
            S[(m, full.split('.')[-1])].append(cone)
        chk, contra = collections.Counter(), []
        for i in un:
            if not D[i][0]:
                continue
            v = S.get((mod_of[i], D[i][0].split('.')[-1]))
            if not v:
                chk['no_match'] += 1
            elif all(v):
                chk['contradiction'] += 1
                contra.append(D[i][0])
            elif any(v):
                chk['ambiguous'] += 1
            else:
                chk['confirmed_unused'] += 1
        R['kernel_check_of_unreached'] = dict(chk)
        R['contradictions'] = contra
        used_short = collections.Counter(full.split('.')[-1] for m, full, cone, n in rows if cone)
        why, whyl = collections.Counter(), collections.Counter()
        for m, full, cone, n in rows:
            if cone:
                continue
            s = full.split('.')[-1]
            ids = mine.get((m, s))
            k = ('not_parsed' if not ids else 'caught' if any(not seen[i] for i in ids)
                 else 'root_by_rule' if any(D[i][2] for i in ids) else 'short_name_shared_with_used'
                 if used_short[s] else 'mentioned_in_reached_text')
            why[k] += 1
            whyl[k] += n
        R['kernel_unused_by_reason_decls'] = dict(why)
        R['kernel_unused_by_reason_kernel_lines'] = dict(whyl)
        allshort = collections.Counter(full.split('.')[-1] for m, full, cone, n in rows)
        R['short_names'] = {'distinct': len(allshort), 'reused': sum(1 for v in allshort.values() if v > 1),
                            'top': allshort.most_common(5)}
    print(json.dumps(R, indent=1))
    if a.json:
        json.dump(R, open(a.json, 'w'), indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
