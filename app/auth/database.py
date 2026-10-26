"""Shared Postgres storage in production; SQLite for local development."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3

from . import config


def prepare_transaction(connection):
    from psycopg.pq import TransactionStatus
    if connection.info.transaction_status == TransactionStatus.IDLE:
        # Transaction-local settings work with Neon's PgBouncer pooler.
        connection.execute("SET LOCAL statement_timeout = '10s'")


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=()):
        prepare_transaction(self.connection)
        return self.connection.execute(sql.replace("?", "%s"), params)

    def cursor(self):
        return PostgresCursor(self.connection.cursor())

    def executescript(self, sql):
        for statement in sql.split(";"):
            if statement.strip():
                prepare_transaction(self.connection)
                self.connection.execute(statement)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def __getattr__(self, name):
        return getattr(self.connection, name)


class PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def execute(self, sql, params=()):
        prepare_transaction(self._cursor.connection)
        self._cursor.execute(sql.replace("?", "%s"), params)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


@contextmanager
def connect():
    if config.IS_PRODUCTION and (not config.AUTH_DATABASE_URL or not config._raw_secret):
        raise sqlite3.OperationalError("Production requires AUTH_DATABASE_URL and SESSION_SECRET")
    if config.AUTH_DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row
        try:
            with psycopg.connect(config.AUTH_DATABASE_URL, row_factory=dict_row,
                                 connect_timeout=5) as conn:
                yield PostgresConnection(conn)
        except psycopg.Error as exc:
            # Do not expose database URLs or driver diagnostics to public responses.
            raise sqlite3.OperationalError("Authentication database unavailable") from exc
    else:
        path = Path(config.AUTH_DB_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            with conn:
                yield conn
        finally:
            conn.close()


def lock_initialization(conn):
    if config.AUTH_DATABASE_URL:
        conn.execute("SELECT pg_advisory_xact_lock(721104317)")
    else:
        conn.execute("BEGIN IMMEDIATE")
