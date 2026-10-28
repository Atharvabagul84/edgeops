"""Idempotent telemetry processing independent of persistence and transport."""
from .fleet import add_event, incident, refresh
from .validation import device_for, utc_time, validate_events


def ingest_events(state, events, now=None):
    """Validate the entire batch, then mutate and return state.

    Event IDs are remembered for the latest 500 accepted readings. A durable
    per-device sequence high-water mark also rejects old events after ID eviction.
    Producers must preserve strictly increasing sequences across their restarts.
    This demo intentionally drops late, out-of-order samples rather than archiving
    them; current device state can never regress to an older sequence.
    """
    validated = validate_events(state, events)
    at = utc_time(now)
    for event in validated:
        device = device_for(state, event['deviceId'])
        if event['eventId'] in state['_seen'] or event['sequence'] <= device['sequence']:
            state['stats']['duplicates'] += 1
            state['pipeline']['duplicates'] += 1
            add_event(state, device['id'], 'duplicate', 'Duplicate or stale sequence ignored safely', at)
            continue
        state['_seen'].append(event['eventId'])
        del state['_seen'][:-500]
        state['_lastEvents'][device['id']] = event
        state['_nextSequences'][device['id']] = max(event['sequence'], state['_nextSequences'][device['id']])
        for key in ('sequence', 'temperature', 'battery', 'signal'):
            device[key] = event[key]
        device['lastSeen'] = event['at']
        device['received'] += 1
        device['history'].append(dict(at=event['at'], temperature=event['temperature']))
        del device['history'][:-48]
        state['stats']['ingested'] += 1
        state['pipeline']['accepted'] += 1
        state['pipeline']['processed'] += 1
        incident(state, device['id'], 'temperature', event['temperature'] >= 55, at)
    state['now'] = at
    refresh(state)
    return state
