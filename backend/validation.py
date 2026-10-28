"""Input validation shared by the local and AWS adapters."""
import math
import re
from datetime import datetime, timezone


def utc_time(value=None):
    if value is None:
        value = datetime.now(timezone.utc)
    if isinstance(value, str):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)', value):
            raise ValueError('Timestamp must be an ISO 8601 UTC timestamp with Z or +00:00.')
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError as error:
            raise ValueError('Timestamp is not a valid calendar time.') from error
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset().total_seconds() != 0:
        raise ValueError('Timestamp must use UTC.')
    return value.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def number(value, name, minimum, maximum, integer=False):
    valid_type = type(value) is int if integer else type(value) in (int, float)
    if not valid_type or not minimum <= value <= maximum or not math.isfinite(value):
        raise ValueError(f'{name} must be {"an integer" if integer else "a finite number"} from {minimum} to {maximum}.')
    return value


def device_for(state, device_id):
    if not isinstance(device_id, str):
        raise ValueError('deviceId must identify a registered demo device.')
    for device in state['devices']:
        if device['id'] == device_id:
            return device
    raise ValueError('Unknown deviceId. Use edge-001, edge-002, or edge-003.')


def validate_events(state, events):
    if not isinstance(events, list) or not 1 <= len(events) <= 100:
        raise ValueError('events must contain between 1 and 100 readings.')
    normalized = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('Each telemetry event must be an object.')
        event_id = event.get('eventId')
        if not isinstance(event_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', event_id):
            raise ValueError('eventId must be 1-128 letters, numbers, dots, colons, underscores or hyphens.')
        device = device_for(state, event.get('deviceId'))
        normalized.append(dict(eventId=event_id, deviceId=device['id'],
                               sequence=number(event.get('sequence'), 'sequence', 0, 2**53 - 1, integer=True),
                               at=utc_time(event.get('at')) if event.get('at') is not None else _missing_time(),
                               temperature=number(event.get('temperature'), 'temperature', -50, 150),
                               battery=number(event.get('battery'), 'battery', 0, 100),
                               signal=number(event.get('signal'), 'signal', 0, 100)))
    return normalized


def _missing_time():
    raise ValueError('Every telemetry event requires an at timestamp.')
