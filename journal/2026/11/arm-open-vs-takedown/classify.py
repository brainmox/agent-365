#!/usr/bin/env python3
"""How much of a "Jon's Arm Reference" page could be rebuilt from Arm's own
BSD-3-Clause machine-readable release (AARCHMRS)?

Inputs (not redistributed here):
  SITE  - pages fetched once on 2026-11-24 from arm.jonpalmisc.com:
          latest_aarch64/*.html (A64 base index) and latest_sysreg/AArch64-*.html
  MRS   - git.kernel.org/pub/scm/linux/kernel/git/maz/AARCHMRS.git at 1346b16
          (AARCHMRS_OPENSOURCE_A_profile_FAT-2026-09), Instructions.json, Registers.json

Every visible text character on a page (site chrome excluded) is put in one bucket:
  structure - names, bit diagrams, encodings, assembler syntax, field headings,
              system-register encodings, field values: the kind of data the BSD
              release carries
  asl       - ASL pseudocode (decode, operation, accessor pseudocode)
  prose     - everything else: titles, descriptions, symbol explanations,
              value meanings, notes, conditions written as sentences
Then the structural claims are checked against the BSD JSON, and the prose is
checked for verbatim presence in it.

Usage: python3 classify.py SITE_DIR MRS_DIR > results.json
"""
import json, os, re, sys, collections
from bs4 import BeautifulSoup, NavigableString, Comment

SITE, MRS = sys.argv[1], sys.argv[2]
SKIP = {'discontinuation-notice', 'copyconf'}
STRUCT = {'regdiagram', 'regdiagram-32', 'encoding', 'asm-code', 'bitdiff',
          'encoding__label', 'bitfield', 'binarynumber', 'hexnumber'}
ENC_LINE = re.compile(r'^\s*\((?:coproc|op0|op1|opc1|CRn)\b')
FIELD_HEAD = re.compile(r'^(.+?), bits? \[(\d+)(?::(\d+))?\]\s*:?\s*$')


def bucket(node):
    for p in node.parents:
        if p.name in ('script', 'style', 'small', 'pagefind-searchbox'):
            return None
        if p.name == 'a' and p.get_text(strip=True) == '\u2190 Home':
            return None
        cls = set(p.get('class') or [])
        if cls & SKIP:
            return None
        if 'pseudocode' in cls and p.name == 'p':
            return 'asl'
        if cls & STRUCT or p.name == 'h1':
            return 'structure'
        if p.name == 'h4' and (p.get('id') or '').startswith('fieldset_'):
            return 'structure'
        if p.name == 'p' and ENC_LINE.match(p.get_text(' ', strip=True)):
            return 'structure'
        if p.name in ('h2', 'h3') and p.get_text(strip=True) in (
                'Operation', 'Field descriptions', 'Access Instructions',
                'Assembler Symbols', 'Configuration', 'Attributes',
                'Operational information'):
            return 'heading'
    return 'prose'


def page_stats(path):
    s = BeautifulSoup(open(path, encoding='utf-8').read(), 'lxml')
    c = collections.Counter()
    prose_chunks = []
    for t in s.body.find_all(string=True):
        if not isinstance(t, NavigableString) or isinstance(t, Comment):
            continue
        txt = ' '.join(t.split())
        if not txt:
            continue
        b = bucket(t)
        if b is None:
            continue
        c[b] += len(txt)
        if b == 'prose':
            prose_chunks.append(txt)
    return s, c, prose_chunks


def load_mrs():
    I = json.load(open(os.path.join(MRS, 'Instructions.json')))
    R = json.load(open(os.path.join(MRS, 'Registers.json')))
    names = set()
    strings = []
    # an alias page anchor is ALIAS_<encoding of the instruction it aliases>
    stack = [(I, None)]
    while stack:
        x, parent = stack.pop()
        if isinstance(x, dict):
            t = x.get('_type')
            if t == 'Instruction.Instruction':
                names.add(x['name'])
                parent = x['name']
            elif t == 'Instruction.InstructionAlias' and parent:
                names.add(x['name'] + '_' + parent)
            stack.extend((v, parent) for v in x.values())
        elif isinstance(x, list):
            stack.extend((v, parent) for v in x)
        elif isinstance(x, str):
            strings.append(x)
    regs = {}
    for r in R:
        if r.get('state') != 'AArch64' or r.get('_type') not in ('Register', 'RegisterArray'):
            continue
        fields = set()
        st = [r.get('fieldsets')]
        while st:
            x = st.pop()
            if isinstance(x, dict):
                if x.get('_type') in ('Fields.Field', 'Fields.ConditionalField',
                                      'Fields.Dynamic', 'Fields.Array',
                                      'Fields.Vector', 'Fields.ConstantField') \
                        and x.get('name'):
                    fields.add(x['name'])
                st.extend(x.values())
            elif isinstance(x, list):
                st.extend(x)
        regs.setdefault(r['name'], set()).update(fields)
    st = [R]
    while st:
        x = st.pop()
        if isinstance(x, dict):
            st.extend(x.values())
        elif isinstance(x, list):
            st.extend(x)
        elif isinstance(x, str):
            strings.append(x)
    return names, regs, '\n'.join(strings)


def main():
    insn_names, regs, corpus = load_mrs()
    out = {}
    for kind, sub, pat in (('instructions', 'latest_aarch64', None),
                           ('registers', 'latest_sysreg', 'AArch64-')):
        d = os.path.join(SITE, sub)
        files = sorted(f for f in os.listdir(d) if f.endswith('.html')
                       and not f.endswith('index.html')
                       and (pat is None or f.startswith(pat)))
        tot = collections.Counter()
        prose_sentences = prose_in_mrs = 0
        anchors = anchors_found = 0
        reg_pages = reg_found = fheads = fheads_found = 0
        pages_prose_majority = 0
        for f in files:
            s, c, chunks = page_stats(os.path.join(d, f))
            tot.update(c)
            body = c['structure'] + c['asl'] + c['prose']
            if body and c['prose'] / body > 0.5:
                pages_prose_majority += 1
            # verbatim prose check: joined prose split into sentences >= 40 chars
            joined = ' '.join(chunks)
            for sent in re.split(r'(?<=[.:])\s+', joined):
                if len(sent) >= 40:
                    prose_sentences += 1
                    if sent in corpus:
                        prose_in_mrs += 1
            if kind == 'instructions':
                for a in s.select('div.encoding__label a[id]'):
                    anchors += 1
                    anchors_found += a['id'] in insn_names
            else:
                h1 = s.find('h1')
                # array registers are titled like "DBGBVR<n>_EL1, n = 0 - 63"
                name = h1.get_text(strip=True).split(',')[0] if h1 else ''
                reg_pages += 1
                known = name in regs
                reg_found += known
                for h in s.find_all('h4', id=re.compile('^fieldset_')):
                    m = FIELD_HEAD.match(' '.join(h.get_text(' ', strip=True).split()))
                    if not m or m.group(1) in ('IMPLEMENTATION DEFINED',):
                        continue
                    if m.group(1).startswith('Bit') or ' ' in m.group(1):
                        continue
                    fheads += 1
                    # field names may carry an index suffix like "<n>"
                    base = re.sub(r'<[^>]*>', '', m.group(1))
                    if known and any(base == re.sub(r'<[^>]*>', '', x)
                                     for x in regs[name]):
                        fheads_found += 1
        body = tot['structure'] + tot['asl'] + tot['prose']
        out[kind] = dict(
            pages=len(files),
            chars=dict(tot),
            share_structure=round(tot['structure'] / body, 4),
            share_asl=round(tot['asl'] / body, 4),
            share_prose=round(tot['prose'] / body, 4),
            pages_majority_prose=pages_prose_majority,
            prose_sentences_ge40=prose_sentences,
            prose_sentences_verbatim_in_bsd_json=prose_in_mrs,
        )
        if kind == 'instructions':
            out[kind].update(encoding_anchors=anchors,
                             encoding_anchors_in_bsd_json=anchors_found)
        else:
            out[kind].update(register_pages=reg_pages,
                             register_names_in_bsd_json=reg_found,
                             named_field_headings=fheads,
                             named_field_headings_in_bsd_json=fheads_found)
    json.dump(out, sys.stdout, indent=1)
    print()


if __name__ == '__main__':
    main()
