"""SQLite transaction boundary for durable, race-safe local fleet state."""
import json
import sqlite3
from pathlib import Path
from .domain import apply_command, ingest_events, initial_state, public_state


class StateRepository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('CREATE TABLE IF NOT EXISTS fleet (id INTEGER PRIMARY KEY CHECK(id=1), state TEXT NOT NULL)')
            connection.execute('INSERT OR IGNORE INTO fleet VALUES (1, ?)', (json.dumps(initial_state()),))
            connection.commit()
        finally:
            connection.close()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute('PRAGMA busy_timeout=10000')
        return connection

    def read(self):
        connection = self._connect()
        try:
            state = json.loads(connection.execute('SELECT state FROM fleet WHERE id=1').fetchone()[0])
            return public_state(state)
        finally:
            connection.close()

    def _mutate(self, operation, argument):
        connection = self._connect()
        try:
            connection.execute('BEGIN IMMEDIATE')
            state = json.loads(connection.execute('SELECT state FROM fleet WHERE id=1').fetchone()[0])
            operation(state, argument)
            connection.execute('UPDATE fleet SET state=? WHERE id=1', (json.dumps(state, allow_nan=False),))
            connection.commit()
            return public_state(state)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def command(self, command):
        return self._mutate(apply_command, command)

    def ingest(self, events):
        return self._mutate(ingest_events, events)
