"""Public domain entry points. Commands mutate and return the supplied state."""
import math
from .fleet import add_event, incident, public_state, refresh
from .seed import initial_state
from .telemetry import ingest_events
from .validation import device_for, number, utc_time


def _sample(state, device, at):
    device_id = device['id']
    sequence = state['_nextSequences'][device_id] + 1
    state['_nextSequences'][device_id] = sequence
    base = 69 if state['_hot'][device_id] else state['_base'][device_id]
    return dict(eventId=f'{device_id}-{sequence}', deviceId=device_id, sequence=sequence, at=at,
                temperature=round(base + math.sin(sequence % 360) * 1.4, 1),
                battery=max(0, round(device['battery'] - 0.01, 2)),
                signal=round(92 + math.sin(sequence % 360) * 5))


def _record_sample(state, device, at):
    event = _sample(state, device, at)
    if device['connected']:
        ingest_events(state, [event], at)
        return
    outbox = state['_outbox'][device['id']]
    if len(outbox) >= 100:
        # Bounded demo storage; stop generating rather than silently lose samples.
        state['_nextSequences'][device['id']] -= 1
        add_event(state, device['id'], 'buffer-full', 'Demo buffer full (100). Reconnect to resume sampling.', at)
        return
    outbox.append(event)


def _reconnect(state, device, at):
    device_id = device['id']
    device['connected'] = True
    incident(state, device_id, 'offline', False, at)
    buffered = state['_outbox'][device_id]
    if buffered:
        before = state['stats']['ingested']
        ingest_events(state, buffered, at)
        state['stats']['replayed'] += state['stats']['ingested'] - before
        state['_outbox'][device_id] = []
    add_event(state, device_id, 'reconnected', 'Connection restored; persisted buffer replayed', at)


def _acknowledge(state, command, at):
    incident_id, device_id = command.get('incidentId'), command.get('deviceId')
    if incident_id is not None and not isinstance(incident_id, str):
        raise ValueError('incidentId must be a string.')
    if incident_id is None:
        device_for(state, device_id)
    matches = [item for item in state['incidents'] if item['status'] == 'open' and
               (item['id'] == incident_id if incident_id else item['deviceId'] == device_id)]
    if not matches:
        raise ValueError('No matching open incident was found.')
    for item in matches:
        if item['acknowledgedAt'] is None:
            item['acknowledgedAt'] = at
            add_event(state, item['deviceId'], 'acknowledged', f"Acknowledged: {item['title']}", at)


def apply_command(state, command, now=None):
    """Apply one validated operator command. Persistence adapters own transactions."""
    if not isinstance(command, dict):
        raise ValueError('Command must be a JSON object.')
    action = command.get('action')
    at = utc_time(now)
    if action == 'reset':
        state.clear()
        state.update(initial_state(at))
        return state
    if action == 'tick':
        steps = number(command.get('steps', 1), 'steps', 1, 100, integer=True)
        for _ in range(steps):
            for device in state['devices']:
                _record_sample(state, device, at)
    elif action == 'acknowledge':
        _acknowledge(state, command, at)
    elif action in ('disconnect', 'reconnect', 'heat', 'cool', 'replay'):
        device = device_for(state, command.get('deviceId'))
        _device_action(state, device, action, at)
    else:
        raise ValueError('Unknown action.')
    state['now'] = at
    refresh(state)
    return state


def _device_action(state, device, action, at):
    device_id = device['id']
    if action == 'disconnect':
        device['connected'] = False
        incident(state, device_id, 'offline', True, at)
    elif action == 'reconnect':
        _reconnect(state, device, at)
    elif action in ('heat', 'cool'):
        state['_hot'][device_id] = action == 'heat'
        _record_sample(state, device, at)
    elif action == 'replay':
        event = state['_lastEvents'].get(device_id)
        if event is None:
            raise ValueError('This device has no ingested event to replay.')
        ingest_events(state, [event], at)
