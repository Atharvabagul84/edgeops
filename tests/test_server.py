import importlib
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path


class ServerTests(unittest.TestCase):
    def setUp(self):
        try:
            module = importlib.import_module('backend.server')
        except ModuleNotFoundError:
            self.fail('The local HTTP application must exist.')
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        static = root / 'frontend'
        static.mkdir()
        (static / 'index.html').write_text('<h1>EdgeOps</h1>', encoding='utf-8')
        self.server = module.create_server(root / 'state.sqlite3', port=0, frontend=static)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        if hasattr(self, 'server'):
            self.server.shutdown()
            self.server.server_close()
            self.thread.join()
            self.temp.cleanup()

    def request(self, path, body=None, headers=None):
        values = {'Content-Type': 'application/json'}
        values.update(headers or {})
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, data=data, headers=values)
        return urllib.request.urlopen(request, timeout=3)

    def test_state_health_and_frontend_are_available(self):
        with self.request('/cloud-config.json') as response:
            self.assertEqual(json.load(response), {'mode': 'local'})
        with self.request('/api/health') as response:
            self.assertEqual(json.load(response)['status'], 'ok')
        with self.request('/api/state') as response:
            state = json.load(response)
            self.assertEqual(len(state['devices']), 3)
            self.assertFalse(any(key.startswith('_') for key in state))
        with self.request('/') as response:
            self.assertIn(b'EdgeOps', response.read())

    def test_actions_tick_export_and_reset(self):
        with self.request('/api/actions', {'action': 'disconnect', 'deviceId': 'edge-001'}) as response:
            self.assertEqual(json.load(response)['devices'][0]['status'], 'offline')
        with self.request('/api/tick', {'steps': 2}) as response:
            self.assertEqual(json.load(response)['devices'][0]['buffered'], 2)
        with self.request('/api/export') as response:
            self.assertIn('attachment', response.headers['Content-Disposition'])
            self.assertEqual(json.load(response)['mode'], 'local')
        with self.request('/api/reset', {}) as response:
            self.assertEqual(json.load(response)['stats']['activeIncidents'], 0)

    def test_release_identifies_successful_api_responses_without_becoming_fleet_state(self):
        reading = dict(eventId='release-contract', deviceId='edge-003', sequence=100,
                       at='2026-10-06T10:00:00Z', temperature=25, battery=99, signal=90)
        requests = [('/api/health', None), ('/api/state', None), ('/api/export', None),
                    ('/api/reset', {}), ('/api/tick', {'steps': 1}),
                    ('/api/actions', {'action': 'disconnect', 'deviceId': 'edge-001'}),
                    ('/api/telemetry', {'events': [reading]})]
        for path, body in requests:
            with self.subTest(path=path), self.request(path, body) as response:
                payload = json.load(response)
                self.assertEqual(payload.get('release'), {'version': '0.3.0', 'id': 'edgeops-0.3.0'})
                self.assertNotIn('release', self.server.repository.read())

    def test_bad_input_is_json_400(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/tick', {'steps': 'bad'})
        self.assertEqual(caught.exception.code, 400)
        self.assertIn('error', json.load(caught.exception))

    def test_external_origin_cannot_mutate_local_state(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/reset', {}, {'Origin': 'https://evil.example'})
        self.assertEqual(caught.exception.code, 403)

    def test_local_origin_is_allowed(self):
        with self.request('/api/tick', {'steps': 1}, {'Origin': self.base}) as response:
            self.assertEqual(response.status, 200)

    def test_api_unknown_route_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/missing')
        self.assertEqual(caught.exception.code, 404)

    def test_oversized_body_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/reset', {'padding': 'x' * 65536})
        self.assertEqual(caught.exception.code, 413)

    def test_path_traversal_cannot_read_sqlite(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/%2e%2e/state.sqlite3')
        self.assertEqual(caught.exception.code, 404)

    def test_rebinding_host_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/state', headers={'Host': 'attacker.example'})
        self.assertEqual(caught.exception.code, 403)

    def test_deeply_nested_json_is_a_bad_request(self):
        body = b'{"value":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}'
        request = urllib.request.Request(self.base + '/api/reset', data=body,
                                         headers={'Content-Type': 'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, 400)


if __name__ == '__main__':
    unittest.main()
