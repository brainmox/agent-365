#!/usr/bin/env python3
"""A local test double of the approval flow Google documents for its Workspace MCP servers.

It is NOT Google's server. It implements the wire contract described in
https://developers.google.com/workspace/guides/mcp-elicitation (page last updated 2026-11-27):
stateless JSON-RPC over HTTP POST, per-request capabilities in params._meta, an
InputRequiredResult challenge, a retry carrying requestState + inputResponses, argument
binding, -32021 MissingRequiredClientCapability, UserDeniedAction / AdminPolicyBlock tool
errors, standing approvals that expire after 90 days, and a /mcp/v1self endpoint without the
send tool. Where Google's text leaves a choice open, this double's choice is marked DOUBLE.

Every request is appended to a JSONL ledger so report.py can grade the client that made it.

  python3 server.py --port 8765 --ledger ledger.jsonl [--policy external=allow]
"""
import argparse, hashlib, hmac, json, os, secrets, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROTOCOL = '2026-07-28'
CAP_KEY = 'io.modelcontextprotocol/clientCapabilities'
INFO_KEY = 'io.modelcontextprotocol/clientInfo'
LABELS = {
    'ALLOW_ONCE': 'Allow once',
    'ALLOW_AUDIENCE_ALWAYS': 'Always allow for these recipients',
    'ALLOW_TOOL_ALWAYS': 'Always allow this tool',
    'DENY_ONCE': "Don't allow",
}
ALLOWING = {'ALLOW_ONCE', 'ALLOW_AUDIENCE_ALWAYS', 'ALLOW_TOOL_ALWAYS'}
STANDING_TTL = 90 * 86400          # documented: saved approvals expire after 90 days
CHALLENGE_TTL = 600                # DOUBLE: Google does not publish how long a challenge stays valid
DENIED_TEXT = 'Action canceled. The user declined the confirmation request.'
BLOCKED_TEXT = ('Action could not be completed. Your administrator has blocked '
                'third-party agents from performing this action.')
MISSING_CAP_TEXT = ('Action could not be completed. This action requires user confirmation, '
                    'which this client does not support. Use a client that supports form '
                    'elicitation to perform this action.')

TOOLS = {
    'search_threads': {'kind': 'read', 'description': 'Search threads in the mailbox.',
                       'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}}}},
    'create_draft': {'kind': 'self_write', 'description': 'Create a draft (not sent).',
                     'inputSchema': {'type': 'object', 'properties': {
                         'to': {'type': 'array', 'items': {'type': 'string'}},
                         'subject': {'type': 'string'}, 'body': {'type': 'string'}}}},
    'send_message': {'kind': 'send', 'description': 'Send an email. Pauses for user confirmation.',
                     'inputSchema': {'type': 'object', 'required': ['to'], 'properties': {
                         'to': {'type': 'array', 'items': {'type': 'string'}},
                         'subject': {'type': 'string'}, 'body': {'type': 'string'}}}},
    'trash_message': {'kind': 'trash', 'description': 'Move a message to trash. Confirms every call.',
                      'inputSchema': {'type': 'object', 'required': ['id'],
                                      'properties': {'id': {'type': 'string'}}}},
}
SELF_TOOLS = ['search_threads', 'create_draft', 'trash_message']   # /mcp/v1self has no send tool


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


class Double:
    """Policy, pending challenges, standing approvals, fake mailbox, ledger."""

    def __init__(self, ledger_path, org_domain='example.com', policy=None, clock=time.time):
        self.secret = secrets.token_bytes(32)
        self.org = org_domain.lower()
        # documented defaults of "User review for external agents"
        self.policy = {'external': 'require', 'internal': 'require'}
        self.policy.update(policy or {})
        self.clock = clock
        self.pending = {}      # elicitationId -> {tool, binding, issued, client}
        self.standing = {}     # (client, tool, audience-or-*) -> expiry
        self.outbox, self.trash = [], []
        self.ledger_path = ledger_path
        self.lock = threading.Lock()

    # ---------- ledger ----------
    def log(self, row):
        row['t'] = round(self.clock(), 4)
        with self.lock, open(self.ledger_path, 'a') as f:
            f.write(canonical(row) + '\n')

    # ---------- policy ----------
    def audience(self, args):
        to = args.get('to') or []
        if isinstance(to, str):
            to = [to]
        return sorted({str(x).strip().lower() for x in to})

    def category(self, tool, args):
        kind = TOOLS[tool]['kind']
        if kind == 'send':
            ext = any(not a.endswith('@' + self.org) for a in self.audience(args))
            return 'external' if ext else 'internal'
        return kind

    def decision(self, client, tool, args):
        """'allow', 'block' or a list of choices to offer."""
        kind = TOOLS[tool]['kind']
        if kind in ('read', 'self_write'):
            return 'allow'
        if kind == 'trash':                       # documented: fresh click, no persistent options
            return ['ALLOW_ONCE', 'DENY_ONCE']
        cat = self.category(tool, args)
        rule = self.policy.get(cat, 'require')
        if rule in ('allow', 'block'):
            return rule
        now = self.clock()
        for key in ((client, tool, '*'), (client, tool, ','.join(self.audience(args)))):
            if self.standing.get(key, 0) > now:
                return 'allow'
        return ['ALLOW_ONCE', 'ALLOW_AUDIENCE_ALWAYS', 'ALLOW_TOOL_ALWAYS', 'DENY_ONCE']

    def binding(self, eid, client, tool, args):
        msg = canonical([eid, client, tool, args]).encode()
        return hmac.new(self.secret, msg, hashlib.sha256).hexdigest()

    # ---------- execution ----------
    def execute(self, tool, args):
        if tool == 'search_threads':
            text = f'0 threads match {args.get("query", "")!r} (test double mailbox is empty).'
        elif tool == 'create_draft':
            text = f'Draft created for {", ".join(self.audience(args)) or "(no recipients)"}.'
        elif tool == 'send_message':
            self.outbox.append(args)
            text = f'Message sent to {", ".join(self.audience(args))}.'
        else:
            self.trash.append(args.get('id'))
            text = f'Message {args.get("id")} moved to trash.'
        return {'resultType': 'complete', 'content': [{'type': 'text', 'text': text}], 'isError': False}

    @staticmethod
    def tool_error(text, reason):
        return {'resultType': 'complete', 'isError': True, 'content': [{'type': 'text', 'text': text}],
                '_meta': {'google.com/error': {'code': 400, 'message': text, 'status': 'FAILED_PRECONDITION',
                          'details': [{'@type': 'type.googleapis.com/google.rpc.ErrorInfo',
                                       'reason': reason, 'domain': 'mcp.googleapis.com'}]}}}

    def challenge(self, client, tool, args, choices):
        eid = secrets.token_hex(8)
        self.pending[eid] = {'tool': tool, 'binding': self.binding(eid, client, tool, args),
                             'issued': self.clock(), 'client': client, 'offered': list(choices)}
        who = ', '.join(self.audience(args)) or args.get('id', '')
        message = (f'**{tool}**  \n{who}  \n' +
                   (f'**Subject:** {args.get("subject", "")}' if 'subject' in args else ''))
        question = f'Allow {client} to use {tool}' + (' for these recipients?' if 'to' in args else '?')
        state = canonical({'elicitationId': eid, 'requestBinding': self.pending[eid]['binding']})
        return eid, {'resultType': 'input_required', 'requestState': state, 'inputRequests': {
            'approval_choice': {'method': 'elicitation/create', 'params': {
                'mode': 'form', 'message': message,
                'requestedSchema': {'type': 'object', 'required': ['approval_choice'], 'properties': {
                    'approval_choice': {'type': 'string', 'title': question, 'enum': choices,
                                        'enumNames': [LABELS[c] for c in choices]}}}}}}}

    # ---------- JSON-RPC ----------
    def handle(self, endpoint, req):
        rid, method, params = req.get('id'), req.get('method'), req.get('params') or {}
        meta = params.get('_meta') or {}
        client = ((meta.get(INFO_KEY) or {}).get('name')) or '(unnamed client)'
        caps = meta.get(CAP_KEY)
        elicit = isinstance(caps, dict) and isinstance(caps.get('elicitation'), dict)
        row = {'endpoint': endpoint, 'method': method, 'client': client, 'declares_elicitation': elicit,
               'protocol': meta.get('io.modelcontextprotocol/protocolVersion')}

        def reply(result=None, error=None, **extra):
            row.update(extra)
            self.log(row)
            out = {'jsonrpc': '2.0', 'id': rid}
            out['error' if error else 'result'] = error or result
            return out

        if method == 'server/discover':
            # Google documents only the _meta serverInfo. resultType, ttlMs, cacheScope, supportedVersions
            # and capabilities are required by the 2026-07-28 schema (MCP Python SDK 2.3.0 enforces them)
            return reply({'resultType': 'complete', 'ttlMs': 0, 'cacheScope': 'private',
                          'supportedVersions': [PROTOCOL], 'capabilities': {'tools': {}},
                          '_meta': {'io.modelcontextprotocol/serverInfo': {
                              'name': 'approval-double', 'title': 'Gmail (test double)', 'version': '0.1.0'}}},
                         outcome='discover')
        names = SELF_TOOLS if endpoint == 'v1self' else list(TOOLS)
        if method == 'tools/list':
            return reply({'resultType': 'complete', 'ttlMs': 0, 'cacheScope': 'private',
                          'tools': [{'name': n, 'description': TOOLS[n]['description'],
                                     'inputSchema': TOOLS[n]['inputSchema']} for n in names]},
                         outcome='list')
        if method != 'tools/call':
            return reply(error={'code': -32601, 'message': f'Method not found: {method}'}, outcome='bad_method')

        tool, args = params.get('name'), params.get('arguments') or {}
        row.update(tool=tool, args_sha=hashlib.sha256(canonical(args).encode()).hexdigest()[:12])
        if tool not in names:
            return reply(error={'code': -32602, 'message': f'Unknown tool: {tool}'}, outcome='unknown_tool')
        misplaced = 'inputResponses' in meta or 'requestState' in meta
        row['misplaced_retry_fields'] = misplaced
        state_raw, responses = params.get('requestState'), params.get('inputResponses')

        # ----- retry path -----
        if state_raw is not None:
            row['retry'] = True
            try:
                state = json.loads(state_raw)
                eid, bind = state['elicitationId'], state['requestBinding']
            except (TypeError, ValueError, KeyError):
                return reply(error={'code': -32602, 'message': 'Invalid requestState. Retry without inputResponses.'},
                             outcome='bad_state')
            pend = self.pending.get(eid)
            row['elicitation_id'] = eid
            if not pend or self.clock() - pend['issued'] > CHALLENGE_TTL:
                return reply(error={'code': -32602, 'message': 'Unknown or expired requestState. '
                                    'Retry without inputResponses.'}, outcome='stale_state')
            row['latency_ms'] = round((self.clock() - pend['issued']) * 1000, 1)
            if not hmac.compare_digest(bind, pend['binding']) or \
                    not hmac.compare_digest(bind, self.binding(eid, client, tool, args)):
                # documented: a modified retry is ignored and a new challenge is issued
                choices = self.decision(client, tool, args)
                if isinstance(choices, list):
                    neid, res = self.challenge(client, tool, args, choices)
                    return reply(res, outcome='rebind_challenge', binding_ok=False, new_elicitation_id=neid)
                return reply(error={'code': -32602, 'message': 'requestState is not bound to these '
                                    'arguments. Retry without inputResponses.'}, outcome='rebind_error',
                             binding_ok=False)
            del self.pending[eid]                 # DOUBLE: a challenge can be answered once
            row['binding_ok'] = True
            ans = (responses or {}).get('approval_choice') or {}
            action = ans.get('action')
            choice = (ans.get('content') or {}).get('approval_choice') if action == 'accept' else None
            row.update(action=action, choice=choice)
            if action == 'accept' and choice not in pend['offered']:
                # DOUBLE: Google does not document this case; refuse rather than run
                return reply(error={'code': -32602, 'message': f'approval_choice {choice!r} was not offered.'},
                             outcome='choice_not_offered')
            if action in ('decline', 'cancel') or choice == 'DENY_ONCE' or choice not in ALLOWING:
                return reply(self.tool_error(DENIED_TEXT, 'UserDeniedAction'), outcome='denied')
            if choice == 'ALLOW_TOOL_ALWAYS':
                self.standing[(client, tool, '*')] = self.clock() + STANDING_TTL
            elif choice == 'ALLOW_AUDIENCE_ALWAYS':
                self.standing[(client, tool, ','.join(self.audience(args)))] = self.clock() + STANDING_TTL
            return reply(self.execute(tool, args), outcome='executed_after_approval')

        # ----- first call -----
        dec = self.decision(client, tool, args)
        if dec == 'allow':
            return reply(self.execute(tool, args), outcome='executed')
        if not elicit:
            return reply(error={'code': -32021, 'message': MISSING_CAP_TEXT,
                                'data': {'requiredCapabilities': {'elicitation': {'form': {}}}}},
                         outcome='missing_capability')
        if dec == 'block':
            return reply(self.tool_error(BLOCKED_TEXT, 'AdminPolicyBlock'), outcome='blocked')
        eid, res = self.challenge(client, tool, args, dec)
        return reply(res, outcome='challenge', elicitation_id=eid, offered=dec)


def make_handler(double):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            endpoint = {'/mcp/v1': 'v1', '/mcp/v1self': 'v1self'}.get(self.path.rstrip('/'))
            if not endpoint:
                self.send_error(404)
                return
            try:
                req = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                out = double.handle(endpoint, req)
            except ValueError:
                out = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}
            body = json.dumps(out).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    return Handler


def serve(double, port=0):
    httpd = ThreadingHTTPServer(('127.0.0.1', port), make_handler(double))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--ledger', default='ledger.jsonl')
    ap.add_argument('--org', default='example.com', help='domain treated as inside the organization')
    ap.add_argument('--policy', action='append', default=[],
                    help='external=require|allow|block or internal=..., repeatable')
    a = ap.parse_args()
    pol = dict(p.split('=', 1) for p in a.policy)
    d = Double(os.path.abspath(a.ledger), a.org, pol)
    httpd = ThreadingHTTPServer(('127.0.0.1', a.port), make_handler(d))
    print(f'approval-double on http://127.0.0.1:{a.port}/mcp/v1 and /mcp/v1self; ledger {a.ledger}; policy {d.policy}')
    httpd.serve_forever()


if __name__ == '__main__':
    main()
