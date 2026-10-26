"""Operator-only initialization / credential-preserving SQLite import.

Run `python -m app.auth.provision --sqlite-backup PATH` before switching traffic.
For a genuinely new install only: `python -m app.auth.provision --new`.
Both commands refuse any nonempty or previously initialized destination.
"""
import argparse
from contextlib import closing
import getpass
from pathlib import Path
import sqlite3
import time

from . import config
from .database import connect, lock_initialization
from .security import hash_password
from .store import DDL_STATEMENTS, set_meta_value


def provision(source=None, admin_password=None, viewer_password=None):
    if not config.AUTH_DATABASE_URL:
        raise RuntimeError("Set AUTH_DATABASE_URL to the shared Postgres database")
    users = []
    if source:
        with closing(sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True)) as old:
            old.row_factory = sqlite3.Row
            users = [dict(row) for row in old.execute("SELECT * FROM auth_users WHERE role IN ('admin', 'viewer')")]
        if not users or not all(u['password_hash'] for u in users):
            raise RuntimeError('Backup contains no usable credentials; no changes made')
    else:
        now = int(time.time())
        for username, role, minimum, supplied_pw in (
            (config.ADMIN_USERNAME, 'admin', 8, admin_password),
            (config.VIEWER_USERNAME, 'viewer', 6, viewer_password),
        ):
            if supplied_pw:
                password = supplied_pw
            else:
                password = getpass.getpass(f'New {role} password: ')
                if len(password) < minimum or password != getpass.getpass('Confirm password: '):
                    raise ValueError('Password too short or confirmation does not match')
            if len(password) < minimum:
                raise ValueError(f'{role.capitalize()} password must be at least {minimum} characters long')
            users.append(dict(username=username, role=role, password_hash=hash_password(password),
                              auth_version=1, created_at=now, updated_at=now))
    if len({u['username'] for u in users}) != len(users):
        raise ValueError('Usernames must differ')
    with connect() as conn:
        lock_initialization(conn)
        conn.executescript(DDL_STATEMENTS)
        if conn.execute('SELECT username FROM auth_users LIMIT 1').fetchone() or conn.execute(
                "SELECT value FROM auth_meta WHERE key = 'setup_completed'").fetchone():
            raise RuntimeError('Destination already contains authentication state; refusing overwrite')
        for user in users:
            conn.execute('INSERT INTO auth_users (username,password_hash,role,auth_version,created_at,updated_at) VALUES (?,?,?,?,?,?)',
                         tuple(user[k] for k in ('username','password_hash','role','auth_version','created_at','updated_at')))
        set_meta_value(conn, 'setup_completed', '1')
    print('Credentials stored and setup locked. Existing users can log in; old sessions are not imported.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--sqlite-backup', help='Path to SQLite database to import admin and viewer hashes from')
    group.add_argument('--new', action='store_true', help='Interactively provision new admin and viewer credentials')
    parser.add_argument('--admin-password', help='Admin password for initial setup')
    parser.add_argument('--viewer-password', help='Viewer password for initial setup')
    args = parser.parse_args()
    provision(args.sqlite_backup, args.admin_password, args.viewer_password)
