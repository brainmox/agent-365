#!/usr/bin/env python3
"""Reference MCP client for the approval flow, with swappable approvers.

  python3 client.py --url http://127.0.0.1:8765/mcp/v1 send --to bob@other.org --subject Hi
  python3 client.py --approver auto:ALLOW_TOOL_ALWAYS send --to bob@other.org

Approvers:
  terminal          render the server's prompt and read a number from stdin (a person decides)
  auto:<CHOICE>     answer the form itself with CHOICE, no person involved
  none              do not declare form elicitation at all
"""
import argparse, json, sys, urllib.request

PROTOCOL = '2026-07-28'


class Client:
    def __init__(self, url, name='approval-double reference client', approver='terminal',
                 stdin=sys.stdin, stdout=sys.stdout):
        self.url, self.name, self.approver = url, name, approver
        self.stdin, self.stdout, self.next_id = stdin, stdout, 1

    def meta(self):
        m = {'io.modelcontextprotocol/protocolVersion': PROTOCOL,
             'io.modelcontextprotocol/clientInfo': {'name': self.name, 'version': '0.1.0'}}
        if self.approver != 'none':
            m['io.modelcontextprotocol/clientCapabilities'] = {'elicitation': {'form': {}}}
        return m

    def rpc(self, method, params):
        req = {'jsonrpc': '2.0', 'id': self.next_id, 'method': method, 'params': params}
        self.next_id += 1
        r = urllib.request.Request(self.url, json.dumps(req).encode(), {
            'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
            'MCP-Protocol-Version': PROTOCOL})
        with urllib.request.urlopen(r, timeout=30) as resp:
            return json.loads(resp.read())

    def decide(self, form):
        """Return an inputResponses entry for one approval_choice form."""
        prop = form['params']['requestedSchema']['properties']['approval_choice']
        if self.approver.startswith('auto:'):
            choice = self.approver.split(':', 1)[1]
            return {'action': 'accept', 'content': {'approval_choice': choice}}
        w = self.stdout.write
        w(f"\n=== {prop['title']} ===\n{form['params']['message']}\n")
        for i, (val, label) in enumerate(zip(prop['enum'], prop['enumNames']), 1):
            w(f'  [{i}] {label} ({val})\n')
        w('Choice (Enter cancels): ')
        self.stdout.flush()
        line = self.stdin.readline().strip()
        if not line.isdigit() or not 1 <= int(line) <= len(prop['enum']):
            return {'action': 'cancel'}
        return {'action': 'accept', 'content': {'approval_choice': prop['enum'][int(line) - 1]}}

    def call(self, tool, arguments, max_rounds=3):
        params = {'name': tool, 'arguments': arguments, '_meta': self.meta()}
        for _ in range(max_rounds):
            out = self.rpc('tools/call', params)
            res = out.get('result')
            if not res or res.get('resultType') != 'input_required':
                return out
            answer = self.decide(res['inputRequests']['approval_choice'])
            params = {'name': tool, 'arguments': arguments, '_meta': self.meta(),
                      'requestState': res['requestState'],          # echoed unchanged
                      'inputResponses': {'approval_choice': answer}}
        return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--url', default='http://127.0.0.1:8765/mcp/v1')
    ap.add_argument('--name', default='approval-double reference client')
    ap.add_argument('--approver', default='terminal')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('send'); s.add_argument('--to', action='append', required=True)
    s.add_argument('--subject', default=''); s.add_argument('--body', default='')
    t = sub.add_parser('trash'); t.add_argument('--id', required=True)
    sub.add_parser('list')
    a = ap.parse_args()
    c = Client(a.url, a.name, a.approver)
    if a.cmd == 'list':
        out = c.rpc('tools/list', {'_meta': c.meta()})
    elif a.cmd == 'send':
        out = c.call('send_message', {'to': a.to, 'subject': a.subject, 'body': a.body})
    else:
        out = c.call('trash_message', {'id': a.id})
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
