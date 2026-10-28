"""Fleet projections, bounded activity log, and incident lifecycle."""
import copy
import uuid


def add_event(state, device_id, kind, message, at):
    state['events'].insert(0, dict(id=str(uuid.uuid4()), deviceId=device_id,
                                 type=kind, message=message, at=at))
    del state['events'][150:]


def refresh(state):
    for device in state['devices']:
        device['buffered'] = len(state['_outbox'][device['id']])
        device['status'] = 'offline' if not device['connected'] else (
            'warning' if device['temperature'] >= 55 else 'healthy')
    state['stats']['buffered'] = sum(device['buffered'] for device in state['devices'])
    state['stats']['activeIncidents'] = sum(incident['status'] == 'open' for incident in state['incidents'])


def incident(state, device_id, kind, active, at):
    current = next((item for item in state['incidents'] if item['deviceId'] == device_id
                    and item['kind'] == kind and item['status'] == 'open'), None)
    if active and current is None:
        title = 'Device disconnected' if kind == 'offline' else 'Temperature above 55°C'
        state['incidents'].insert(0, dict(id=str(uuid.uuid4()), deviceId=device_id, kind=kind,
                                        title=title, severity='critical' if kind == 'offline' else 'warning',
                                        openedAt=at, resolvedAt=None, acknowledgedAt=None, status='open'))
        # At most six incidents can be open for this three-device demonstration.
        state['incidents'] = (list(filter(lambda item: item['status'] == 'open', state['incidents'])) +
                              list(filter(lambda item: item['status'] == 'resolved', state['incidents'])))[:100]
        add_event(state, device_id, 'incident', title, at)
    if not active and current:
        current['status'] = 'resolved'
        current['resolvedAt'] = at
        add_event(state, device_id, 'resolved', f"Resolved: {current['title']}", at)


def public_state(state):
    """Return an independent JSON-safe projection without inbox/outbox internals."""
    return copy.deepcopy({key: value for key, value in state.items() if not key.startswith('_')})
