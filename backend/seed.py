"""Small explicit synthetic fleet; all timestamps and readings are demo data."""
from datetime import datetime, timedelta
from .fleet import add_event
from .telemetry import ingest_events
from .validation import utc_time


def initial_state(now=None):
    at = utc_time(now)
    definitions = [('edge-001', 'Nashik Gateway', 'Nashik, India', 27.2, 92, 96),
                   ('edge-002', 'Pune Cold Store', 'Pune, India', 4.3, 86, 88),
                   ('edge-003', 'Bengaluru Rover', 'Bengaluru, India', 31.1, 78, 91)]
    state = dict(mode='local', now=at, demo=True, dataSource='Synthetic device telemetry',
                 devices=[], incidents=[], events=[],
                 stats=dict(ingested=0, duplicates=0, replayed=0, buffered=0, activeIncidents=0),
                 pipeline=dict(accepted=0, processed=0, duplicates=0, deadLetters=0),
                 _seen=[], _outbox={}, _lastEvents={}, _nextSequences={}, _hot={}, _base={})
    for device_id, name, location, temperature, battery, signal in definitions:
        state['devices'].append(dict(id=device_id, name=name, location=location, status='healthy',
                                    connected=True, temperature=temperature, battery=battery, signal=signal,
                                    lastSeen=at, firmware='1.4.2', sequence=0, buffered=0, received=0, history=[]))
        state['_outbox'][device_id] = []
        state['_nextSequences'][device_id] = 0
        state['_hot'][device_id] = False
        state['_base'][device_id] = temperature
    instant = datetime.fromisoformat(at.replace('Z', '+00:00'))
    for sequence in range(1, 13):
        sample_at = utc_time(instant - timedelta(seconds=(12 - sequence) * 30))
        events = [dict(eventId=f"seed-{item['id']}-{sequence}", deviceId=item['id'], sequence=sequence,
                       at=sample_at, temperature=round(item['temperature'] + (sequence % 3 - 1) * .2, 1),
                       battery=item['battery'], signal=item['signal']) for item in state['devices']]
        ingest_events(state, events, at)
    add_event(state, None, 'system', 'Local demo initialized with three synthetic devices', at)
    return state
