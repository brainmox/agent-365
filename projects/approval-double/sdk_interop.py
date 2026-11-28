#!/usr/bin/env python3
"""Point the official MCP Python SDK client at approval-double.

  python3 -m venv venv && venv/bin/pip install mcp==2.3.0
  venv/bin/python sdk_interop.py [--out results/sdk-interop]

Runs three clients against a fresh double and writes the ledger plus a report:
  sdk-auto-allow   elicitation_callback that answers ALLOW_ONCE itself (no person)
  sdk-deny         elicitation_callback that answers DENY_ONCE
  sdk-no-callback  no elicitation_callback at all
  sdk-unoffered    callback answers ALLOW_TOOL_ALWAYS to a trash prompt that offers only ALLOW_ONCE / DENY_ONCE
"""
import argparse, asyncio, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import Double, serve   # noqa: E402
import report                      # noqa: E402

import mcp                         # noqa: E402
from mcp import Client             # noqa: E402
import mcp_types as types          # noqa: E402

SEND = {'to': ['bob@other.org'], 'subject': 'Quarterly numbers', 'body': 'Attached.'}


def answer(choice, seen):
    async def cb(context, params):
        seen.append({'message': getattr(params, 'message', None),
                     'schema': getattr(params, 'requested_schema', None) or getattr(params, 'requestedSchema', None)})
        return types.ElicitResult(action='accept', content={'approval_choice': choice})
    return cb


def summarize(res):
    while isinstance(res, BaseExceptionGroup) and res.exceptions:   # anyio wraps the SDK's error
        res = res.exceptions[0]
    if isinstance(res, Exception):
        return f'{type(res).__name__}: {res}'
    data = res.model_dump(mode='json', by_alias=True, exclude_none=True) if hasattr(res, 'model_dump') else res
    return data


async def run(url, name, callback, mode, tool='send_message', args=SEND):
    kw = dict(client_info=types.Implementation(name=name, version=mcp_version()), mode=mode)
    if callback:
        kw['elicitation_callback'] = callback
    try:
        async with Client(url, **kw) as c:
            return await c.call_tool(tool, args)
    except Exception as e:          # report the SDK's own error text
        return e


def mcp_version():
    from importlib.metadata import version
    return version('mcp')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default='results/sdk-interop')
    ap.add_argument('--mode', default='auto', help="SDK connect mode: auto (server/discover probe) or 2026-07-28")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    ledger = os.path.join(a.out, 'ledger.jsonl')
    if os.path.exists(ledger):
        os.remove(ledger)
    d = Double(ledger)
    httpd = serve(d)
    url = f'http://127.0.0.1:{httpd.server_address[1]}/mcp/v1'
    seen = {k: [] for k in ('sdk-auto-allow', 'sdk-deny', 'sdk-unoffered')}
    results = {}
    for name, cb, tool, args in (
            ('sdk-auto-allow', answer('ALLOW_ONCE', seen['sdk-auto-allow']), 'send_message', SEND),
            ('sdk-deny', answer('DENY_ONCE', seen['sdk-deny']), 'send_message', SEND),
            ('sdk-no-callback', None, 'send_message', SEND),
            ('sdk-unoffered', answer('ALLOW_TOOL_ALWAYS', seen['sdk-unoffered']), 'trash_message', {'id': 'm1'})):
        results[name] = summarize(asyncio.run(run(url, name, cb, a.mode, tool, args)))
    httpd.shutdown()
    rows = [json.loads(l) for l in open(ledger)]
    out = {'mcp_sdk_version': mcp_version(), 'connect_mode': a.mode, 'messages_sent': len(d.outbox),
           'messages_trashed': len(d.trash), 'callback_saw': seen,
           'results': results, 'report': report.grade(rows)}
    with open(os.path.join(a.out, 'summary.json'), 'w') as f:
        json.dump(out, f, indent=1, default=str)
    print(json.dumps(out, indent=1, default=str))


if __name__ == '__main__':
    main()
