#!/usr/bin/env python3
"""Rebuild the documentation diffs behind the Workspace agent-rule entry.

  python3 compare.py            # fetch Wayback captures + live pages, write diffs/ and gmail-toolsets.json

Each pair compares an Internet Archive capture of a Google developer page with a later
capture or with the live page. Live pages keep changing, so a rerun after
2026-11-27 can produce different "after" text; the published diffs/ folder is the record
of what was compared on 2026-11-27. Page text: Google, CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/); extracted from HTML, unchanged except for
whitespace.
"""
import difflib, gzip, html, json, os, re, time, urllib.request

BASE = 'https://developers.google.com/'
PAIRS = [
    # name, path, before (Wayback timestamp), after (Wayback timestamp or 'live')
    ('gmail-quotas', 'workspace/gmail/api/guides/quotas', '20261126211519', 'live'),
    ('usage-tiers', 'workspace/guides/quota-usage-tiers', '20261124224030', 'live'),
    ('gmail-mcp-setup', 'workspace/gmail/api/guides/configure-mcp-server', '20261126211716', '20261127043338'),
    ('gmail-mcp-reference', 'workspace/gmail/api/reference/mcp', '20261104055932', 'live'),
    ('approvals-guide', 'workspace/guides/mcp-elicitation', '20261126211719', '20261127033247'),
]


def fetch(url, tries=4):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                if r.headers.get('Content-Encoding') == 'gzip' or raw[:2] == b'\x1f\x8b':
                    raw = gzip.decompress(raw)
            return raw.decode('utf-8', 'replace')
        except OSError:
            if i == tries - 1:
                raise
            time.sleep(20 * (i + 1))  # the Internet Archive refuses bursts of requests


def to_text(page):
    updated = re.findall(r'Last updated ([0-9-]+ UTC)', page)
    t = re.sub(r'(?s)<(script|style)[^>]*>.*?</\1>', ' ', page)
    m = re.search(r'(?s)<article[^>]*>(.*)</article>', t)
    t = m.group(1) if m else t
    t = re.sub(r'</(p|li|tr|h\d|div|td|th|pre)>', '\n', t)
    t = re.sub(r'<td[^>]*>|<th[^>]*>', ' | ', t)
    t = html.unescape(re.sub(r'<[^>]+>', '', t))
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n\s*\n+', '\n', t)
    return t, (updated[0] if updated else 'not shown')


def url_for(path, when):
    if when == 'live':
        return BASE + path
    return f'https://web.archive.org/web/{when}id_/{BASE}{path}'


def gmail_toolsets(text):
    def tools(s):
        out = []
        for line in s.split('\n'):
            line = line.strip(' |')
            if line and line.replace('_', '').isalpha() and line.islower():
                out.append(line)
        return out
    a = text.split('| /mcp/v1\n')[1].split('| /mcp/v1self')[0]
    b = text.split('| /mcp/v1self')[1]
    v1 = tools(a.split('Toolset for the Gmail MCP Server.')[1])
    vs = [x for x in tools(b.split('Self-mode toolset for the Gmail MCP Server.')[1]) if x in v1]
    return dict(v1=v1, v1self=vs, only_on_v1=sorted(set(v1) - set(vs)))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(here, 'diffs'), exist_ok=True)
    out = {}
    for name, path, before, after in PAIRS:
        tb, ub = to_text(fetch(url_for(path, before)))
        ta, ua = to_text(fetch(url_for(path, after)))
        head = (f'# {BASE}{path}\n# before: {url_for(path, before)} (page says last updated {ub})\n'
                f'# after:  {url_for(path, after)} (page says last updated {ua})\n'
                '# Page text (c) Google, CC BY 4.0; extracted from HTML, whitespace normalized.\n')
        diff = difflib.unified_diff(tb.splitlines(), ta.splitlines(), 'before', 'after', lineterm='', n=2)
        with open(os.path.join(here, 'diffs', name + '.diff'), 'w') as f:
            f.write(head + '\n'.join(diff) + '\n')
        if name == 'gmail-mcp-reference':
            out = gmail_toolsets(ta)
            out['source'] = url_for(path, after)
            out['page_last_updated'] = ua
        print(name, ub, '->', ua)
    with open(os.path.join(here, 'gmail-toolsets.json'), 'w') as f:
        json.dump(out, f, indent=1)
    print(len(out['v1']), 'tools on /mcp/v1;', len(out['v1self']), 'on /mcp/v1self; only on /mcp/v1:', out['only_on_v1'])


if __name__ == '__main__':
    main()
