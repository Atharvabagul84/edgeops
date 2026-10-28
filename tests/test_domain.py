import copy
import concurrent.futures
import importlib
import tempfile
import unittest
from pathlib import Path


NOW = '2026-10-06T10:00:00Z'


class DomainTests(unittest.TestCase):
    def setUp(self):
        try:
            self.domain = importlib.import_module('backend.domain')
        except ModuleNotFoundError:
            self.fail('The telemetry domain must exist before its behavior can pass.')
        self.state = self.domain.initial_state(NOW)

    def event(self, sequence=100, **changes):
        value = dict(eventId=f'edge-001-external-{sequence}', deviceId='edge-001',
                     sequence=sequence, at=NOW, temperature=24.5, battery=87, signal=94)
        value.update(changes)
        return value

    def test_seed_has_three_explicitly_synthetic_devices(self):
        self.assertEqual(len(self.state['devices']), 3)
        self.assertEqual(self.state['mode'], 'local')
        self.assertTrue(all(device['status'] == 'healthy' for device in self.state['devices']))

    def test_duplicate_delivery_has_one_business_effect(self):
        event = self.event()
        self.domain.ingest_events(self.state, [event], NOW)
        before = self.state['stats']['ingested']
        received = self.state['devices'][0]['received']
        self.domain.ingest_events(self.state, [event], NOW)
        self.assertEqual(self.state['stats']['ingested'], before)
        self.assertEqual(self.state['devices'][0]['received'], received)
        self.assertEqual(self.state['stats']['duplicates'], 1)

    def test_old_sequence_cannot_overwrite_latest_reading(self):
        self.domain.ingest_events(self.state, [self.event(101, temperature=31)], NOW)
        self.domain.ingest_events(self.state, [self.event(100, temperature=15)], NOW)
        self.assertEqual(self.state['devices'][0]['temperature'], 31)
        self.assertEqual(self.state['devices'][0]['sequence'], 101)

    def test_offline_buffer_replays_on_reconnect(self):
        before = self.state['devices'][0]['received']
        self.domain.apply_command(self.state, dict(action='disconnect', deviceId='edge-001'), NOW)
        self.domain.apply_command(self.state, dict(action='tick', steps=4), NOW)
        self.assertEqual(self.state['devices'][0]['buffered'], 4)
        self.assertEqual(self.state['devices'][0]['received'], before)
        self.domain.apply_command(self.state, dict(action='reconnect', deviceId='edge-001'), NOW)
        self.assertEqual(self.state['devices'][0]['buffered'], 0)
        self.assertEqual(self.state['devices'][0]['received'], before + 4)
        self.assertEqual(self.state['stats']['replayed'], 4)
        self.assertEqual(self.state['stats']['activeIncidents'], 0)

    def test_heat_acknowledge_and_cool_preserve_incident_lifecycle(self):
        self.domain.apply_command(self.state, dict(action='heat', deviceId='edge-001'), NOW)
        self.assertEqual(self.state['devices'][0]['status'], 'warning')
        incident = self.state['incidents'][0]
        self.domain.apply_command(self.state, dict(action='acknowledge', incidentId=incident['id']), NOW)
        self.assertEqual(incident['status'], 'open')
        self.assertIsNotNone(incident['acknowledgedAt'])
        self.domain.apply_command(self.state, dict(action='cool', deviceId='edge-001'), NOW)
        self.assertEqual(incident['status'], 'resolved')
        self.assertEqual(self.state['devices'][0]['status'], 'healthy')

    def test_bad_batch_has_no_partial_effect(self):
        before = copy.deepcopy(self.state)
        with self.assertRaises(ValueError):
            self.domain.ingest_events(self.state, [self.event(), self.event(101, temperature='oops')], NOW)
        self.assertEqual(self.state, before)

    def test_invalid_timestamp_and_nonfinite_numbers_are_rejected(self):
        for changes in ({'at': 'yesterday'}, {'at': '2026-10-06T10:00:00'},
                        {'temperature': float('nan')}, {'battery': 101}, {'sequence': True},
                        {'temperature': 10**400}, {'signal': -1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.domain.ingest_events(self.state, [self.event(**changes)], NOW)

    def test_full_offline_buffer_preserves_readings_without_silent_eviction(self):
        self.domain.apply_command(self.state, dict(action='disconnect', deviceId='edge-001'), NOW)
        self.domain.apply_command(self.state, dict(action='tick', steps=100), NOW)
        buffered = copy.deepcopy(self.state['_outbox']['edge-001'])
        self.domain.apply_command(self.state, dict(action='tick', steps=1), NOW)
        self.assertEqual(self.state['_outbox']['edge-001'], buffered)
        self.domain.apply_command(self.state, dict(action='reconnect', deviceId='edge-001'), NOW)
        self.assertEqual(self.state['stats']['replayed'], 100)

    def test_concurrent_repository_commands_do_not_lose_updates(self):
        repository = importlib.import_module('backend.repository')
        with tempfile.TemporaryDirectory() as folder:
            store = repository.StateRepository(Path(folder) / 'state.sqlite3')
            before = store.read()['stats']['ingested']
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                results = list(pool.map(lambda _: store.command(dict(action='tick', steps=1)), range(20)))
            self.assertEqual(len(results), 20)
            self.assertEqual(store.read()['stats']['ingested'], before + 60)

    def test_invalid_commands_and_unknown_devices_are_rejected(self):
        for command in ({'action': 'tick', 'steps': 101}, {'action': 'tick', 'steps': True},
                        {'action': 'disconnect', 'deviceId': 'missing'}, {'action': 'shell'}):
            with self.subTest(command=command), self.assertRaises(ValueError):
                self.domain.apply_command(self.state, command, NOW)

    def test_persisted_offline_buffer_survives_repository_restart(self):
        try:
            repository = importlib.import_module('backend.repository')
        except ModuleNotFoundError:
            self.fail('A durable state repository is required.')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.sqlite3'
            store = repository.StateRepository(path)
            store.command(dict(action='disconnect', deviceId='edge-001'))
            store.command(dict(action='tick', steps=3))
            restored = repository.StateRepository(path)
            self.assertEqual(restored.read()['devices'][0]['buffered'], 3)
            final = restored.command(dict(action='reconnect', deviceId='edge-001'))
            self.assertEqual(final['stats']['replayed'], 3)
            self.assertEqual(final['devices'][0]['buffered'], 0)
            self.assertFalse(any(key.startswith('_') for key in final))


if __name__ == '__main__':
    unittest.main()

