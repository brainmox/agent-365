import io, json, os, sys, tempfile, unittest, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import Double, serve, STANDING_TTL, CHALLENGE_TTL   # noqa: E402
from client import Client                                       # noqa: E402
import report                                                   # noqa: E402

EXT = {'to': ['bob@other.org'], 'subject': 'Hi', 'body': 'x'}
INT = {'to': ['ann@example.com'], 'subject': 'Hi', 'body': 'x'}


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


class Base(unittest.TestCase):
    policy = None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, 'l.jsonl')
        self.clock = Clock()
        self.d = Double(self.ledger, policy=self.policy, clock=self.clock)
        self.httpd = serve(self.d)
        self.base = f'http://127.0.0.1:{self.httpd.server_address[1]}'

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def client(self, approver='auto:ALLOW_ONCE', name='agent', endpoint='v1', answers=''):
        out = io.StringIO()
        c = Client(f'{self.base}/mcp/{endpoint}', name, approver, stdin=io.StringIO(answers), stdout=out)
        c.out = out
        return c

    def raw(self, params, endpoint='v1', method='tools/call'):
        body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode()
        r = urllib.request.Request(f'{self.base}/mcp/{endpoint}', body, {'Content-Type': 'application/json'})
        return json.loads(urllib.request.urlopen(r).read())

    def rows(self):
        with open(self.ledger) as f:
            return [json.loads(l) for l in f]

    def text(self, out):
        return out['result']['content'][0]['text']


class ServerContract(Base):
    def test_challenge_shape_matches_google_docs(self):
        c = self.client()
        res = c.rpc('tools/call', {'name': 'send_message', 'arguments': EXT, '_meta': c.meta()})['result']
        self.assertEqual(res['resultType'], 'input_required')
        form = res['inputRequests']['approval_choice']
        self.assertEqual(form['method'], 'elicitation/create')
        self.assertEqual(form['params']['mode'], 'form')
        prop = form['params']['requestedSchema']['properties']['approval_choice']
        self.assertEqual(prop['enum'], ['ALLOW_ONCE', 'ALLOW_AUDIENCE_ALWAYS', 'ALLOW_TOOL_ALWAYS', 'DENY_ONCE'])
        self.assertEqual(len(prop['enum']), len(prop['enumNames']))
        self.assertIn('agent', prop['title'])
        self.assertEqual(set(json.loads(res['requestState'])), {'elicitationId', 'requestBinding'})
        self.assertEqual(self.d.outbox, [])

    def test_missing_capability_is_32021_on_both_endpoints(self):
        for ep in ('v1', 'v1self'):
            c = self.client('none', endpoint=ep)
            tool, args = ('send_message', EXT) if ep == 'v1' else ('trash_message', {'id': 'm1'})
            err = c.call(tool, args)['error']
            self.assertEqual(err['code'], -32021)
            self.assertEqual(err['data']['requiredCapabilities'], {'elicitation': {'form': {}}})

    def test_reads_and_drafts_need_no_capability(self):
        c = self.client('none')
        self.assertFalse(c.call('search_threads', {'query': 'x'})['result']['isError'])
        self.assertFalse(c.call('create_draft', EXT)['result']['isError'])

    def test_v1self_has_no_send_tool(self):
        c = self.client(endpoint='v1self')
        names = [t['name'] for t in c.rpc('tools/list', {'_meta': c.meta()})['result']['tools']]
        self.assertNotIn('send_message', names)
        self.assertEqual(c.call('send_message', EXT)['error']['code'], -32602)

    def test_allow_once_sends_and_asks_again_next_time(self):
        c = self.client()
        self.assertIn('Message sent', self.text(c.call('send_message', EXT)))
        self.assertEqual(len(self.d.outbox), 1)
        first = c.rpc('tools/call', {'name': 'send_message', 'arguments': EXT, '_meta': c.meta()})
        self.assertEqual(first['result']['resultType'], 'input_required')

    def test_deny_and_cancel_are_user_denied_action(self):
        for approver in ('auto:DENY_ONCE', 'terminal'):
            res = self.client(approver, answers='\n').call('send_message', EXT)['result']
            self.assertTrue(res['isError'])
            reason = res['_meta']['google.com/error']['details'][0]['reason']
            self.assertEqual(reason, 'UserDeniedAction')
        self.assertEqual(self.d.outbox, [])

    def test_terminal_approver_renders_labels_and_sends_choice(self):
        c = self.client('terminal', answers='1\n')
        self.assertIn('Message sent', self.text(c.call('send_message', EXT)))
        shown = c.out.getvalue()
        self.assertIn('[4] Don\'t allow (DENY_ONCE)', shown)
        self.assertIn('bob@other.org', shown)

    def test_modified_arguments_on_retry_get_a_new_challenge(self):
        c = self.client()
        res = c.rpc('tools/call', {'name': 'send_message', 'arguments': EXT, '_meta': c.meta()})['result']
        swapped = dict(EXT, to=['eve@evil.test'])
        out = c.rpc('tools/call', {'name': 'send_message', 'arguments': swapped, '_meta': c.meta(),
                                   'requestState': res['requestState'],
                                   'inputResponses': {'approval_choice': {
                                       'action': 'accept', 'content': {'approval_choice': 'ALLOW_ONCE'}}}})
        self.assertEqual(out['result']['resultType'], 'input_required')
        self.assertEqual(self.d.outbox, [])

    def test_state_is_single_use_and_expires(self):
        c = self.client()
        res = c.rpc('tools/call', {'name': 'send_message', 'arguments': EXT, '_meta': c.meta()})['result']
        retry = {'name': 'send_message', 'arguments': EXT, '_meta': c.meta(), 'requestState': res['requestState'],
                 'inputResponses': {'approval_choice': {'action': 'accept',
                                                        'content': {'approval_choice': 'ALLOW_ONCE'}}}}
        self.assertFalse(c.rpc('tools/call', retry)['result']['isError'])
        self.assertEqual(c.rpc('tools/call', retry)['error']['code'], -32602)        # replay refused
        res = c.rpc('tools/call', {'name': 'send_message', 'arguments': EXT, '_meta': c.meta()})['result']
        self.clock.now += CHALLENGE_TTL + 1
        retry['requestState'] = res['requestState']
        self.assertEqual(c.rpc('tools/call', retry)['error']['code'], -32602)
        self.assertEqual(c.rpc('tools/call', dict(retry, requestState='not json'))['error']['code'], -32602)
        self.assertEqual(len(self.d.outbox), 1)

    def test_state_from_another_client_is_not_accepted(self):
        a, b = self.client(name='agent-a'), self.client(name='agent-b')
        res = a.rpc('tools/call', {'name': 'send_message', 'arguments': EXT, '_meta': a.meta()})['result']
        out = b.rpc('tools/call', {'name': 'send_message', 'arguments': EXT, '_meta': b.meta(),
                                   'requestState': res['requestState'],
                                   'inputResponses': {'approval_choice': {
                                       'action': 'accept', 'content': {'approval_choice': 'ALLOW_ONCE'}}}})
        self.assertEqual(out['result']['resultType'], 'input_required')

    def test_standing_approvals_scope_and_90_day_expiry(self):
        c = self.client('auto:ALLOW_AUDIENCE_ALWAYS')
        c.call('send_message', EXT)
        quiet = self.client('none')                       # no capability needed once standing approval exists
        self.assertFalse(quiet.call('send_message', EXT).get('error'))
        self.assertEqual(quiet.call('send_message', INT)['error']['code'], -32021)   # other audience
        self.assertEqual(self.client('none', name='other').call('send_message', EXT)['error']['code'], -32021)
        self.clock.now += STANDING_TTL + 1
        self.assertEqual(quiet.call('send_message', EXT)['error']['code'], -32021)
        self.client('auto:ALLOW_TOOL_ALWAYS').call('send_message', EXT)
        self.assertFalse(quiet.call('send_message', INT).get('error'))

    def test_trash_offers_no_standing_choice(self):
        c = self.client()
        res = c.rpc('tools/call', {'name': 'trash_message', 'arguments': {'id': 'm1'}, '_meta': c.meta()})['result']
        prop = res['inputRequests']['approval_choice']['params']['requestedSchema']['properties']['approval_choice']
        self.assertEqual(prop['enum'], ['ALLOW_ONCE', 'DENY_ONCE'])
        out = self.client('auto:ALLOW_TOOL_ALWAYS').call('trash_message', {'id': 'm1'})
        self.assertEqual(out['error']['code'], -32602)
        self.assertEqual(self.d.trash, [])
        self.assertFalse(report.grade(self.rows())['agent']['checks']['chooses_offered'])


class AdminPolicy(Base):
    policy = {'external': 'block', 'internal': 'allow'}

    def test_admin_block_and_allow(self):
        res = self.client().call('send_message', EXT)['result']
        self.assertEqual(res['_meta']['google.com/error']['details'][0]['reason'], 'AdminPolicyBlock')
        self.assertIn('Message sent', self.text(self.client('none').call('send_message', INT)))


class Report(Base):
    def test_auto_approver_passes_every_wire_check(self):
        """The point of the project: a client with no person in the loop is indistinguishable on the wire."""
        human = self.client('terminal', name='human', answers='1\n')
        bot = self.client('auto:ALLOW_TOOL_ALWAYS', name='bot')
        human.call('send_message', EXT)
        bot.call('send_message', EXT)
        rep = report.grade(self.rows(), human_floor_ms=400)
        for who in ('human', 'bot'):
            self.assertTrue(all(rep[who]['checks'].values()), rep[who])
        self.assertEqual(rep['bot']['choices'], {'ALLOW_TOOL_ALWAYS': 1})
        self.assertEqual(rep['bot']['answers_under_floor'], 1)
        self.assertIn('not proof', report.render(rep, 400))

    def test_sloppy_client_fails_checks(self):
        meta = self.client().meta()
        res = self.raw({'name': 'send_message', 'arguments': EXT, '_meta': meta})['result']
        bad_meta = dict(meta, requestState=res['requestState'])
        self.raw({'name': 'send_message', 'arguments': EXT, '_meta': bad_meta})           # misplaced
        self.raw({'name': 'send_message', 'arguments': dict(EXT, subject='changed'), '_meta': meta,
                  'requestState': res['requestState'],
                  'inputResponses': {'approval_choice': {'action': 'accept',
                                                         'content': {'approval_choice': 'ALLOW_ONCE'}}}})
        self.raw({'name': 'send_message', 'arguments': EXT, '_meta': meta, 'requestState': '{}',
                  'inputResponses': {}})
        self.raw({'name': 'search_threads', 'arguments': {},
                  '_meta': {'io.modelcontextprotocol/clientInfo': {'name': 'agent'}}})
        checks = report.grade(self.rows())['agent']['checks']
        self.assertEqual(checks, {'declares_every_call': False, 'echoes_state': False, 'same_arguments': False,
                                  'fields_placed': False, 'chooses_offered': True,
                                  'stops_after_denial': True})

    def test_write_after_denial_is_flagged(self):
        c = self.client('auto:DENY_ONCE')
        c.call('send_message', EXT)
        self.clock.now += 5
        c.call('create_draft', EXT)
        g = report.grade(self.rows())['agent']
        self.assertFalse(g['checks']['stops_after_denial'])
        self.assertEqual(g['writes_after_denial'], ['create_draft'])


if __name__ == '__main__':
    unittest.main()
