"""Validate every reply the double produces against the MCP Python SDK's 2026-07-28 wire schemas.

Skipped unless the SDK is importable:  python3 -m venv venv && venv/bin/pip install mcp==2.3.0
"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import Double   # noqa: E402

try:
    import mcp_types._v2026_07_28 as V
except ImportError:          # pragma: no cover
    V = None

META = {'io.modelcontextprotocol/protocolVersion': '2026-07-28',
        'io.modelcontextprotocol/clientInfo': {'name': 'schema-test', 'version': '1'},
        'io.modelcontextprotocol/clientCapabilities': {'elicitation': {'form': {}}}}
EXT = {'to': ['bob@other.org'], 'subject': 's', 'body': 'b'}


@unittest.skipIf(V is None, 'mcp SDK not installed')
class WireSchemas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Double(os.path.join(self.tmp.name, 'l.jsonl'))

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, method, params, endpoint='v1'):
        return self.d.handle(endpoint, {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})

    def test_discover_and_list(self):
        V.DiscoverResult.model_validate(self.call('server/discover', {})['result'])
        for ep in ('v1', 'v1self'):
            V.ListToolsResult.model_validate(self.call('tools/list', {'_meta': META}, ep)['result'])

    def test_challenge_retry_and_errors(self):
        ch = self.call('tools/call', {'name': 'send_message', 'arguments': EXT, '_meta': META})['result']
        V.InputRequiredResult.model_validate(ch)
        retry = {'name': 'send_message', 'arguments': EXT, '_meta': META, 'requestState': ch['requestState'],
                 'inputResponses': {'approval_choice': {'action': 'accept',
                                                        'content': {'approval_choice': 'ALLOW_ONCE'}}}}
        V.CallToolRequestParams.model_validate(retry)        # the retry our client sends is spec-shaped
        V.CallToolResult.model_validate(self.call('tools/call', retry)['result'])
        ch = self.call('tools/call', {'name': 'send_message', 'arguments': EXT, '_meta': META})['result']
        denied = self.call('tools/call', dict(retry, requestState=ch['requestState'], inputResponses={
            'approval_choice': {'action': 'decline'}}))['result']
        V.CallToolResult.model_validate(denied)
        self.assertTrue(denied['isError'])
        err = self.call('tools/call', {'name': 'send_message', 'arguments': EXT, '_meta': {}})['error']
        self.assertEqual(err['code'], -32021)


if __name__ == '__main__':
    unittest.main()
