"""Identity of the running application, added at the HTTP response boundary."""

RELEASE = {'version': '0.3.0', 'id': 'edgeops-0.3.0'}


def with_release(payload):
    """Copy the response envelope without adding release data to fleet storage."""
    return {**payload, 'release': dict(RELEASE)}
