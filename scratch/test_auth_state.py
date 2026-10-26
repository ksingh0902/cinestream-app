import os
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['ADMIN_INITIAL_PASSWORD'] = ''
os.environ['VIEWER_INITIAL_PASSWORD'] = ''
os.environ['ADMIN_PASSWORD'] = ''
os.environ['VIEWER_PASSWORD'] = ''

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.auth import config, store
from app.auth.middleware import PrivateAccessMiddleware
from app.auth.routes import auth_router


class AuthStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.overrides = patch.multiple(config, AUTH_DB_PATH=str(Path(self.temp.name)/'auth.sqlite3'),
            AUTH_DATABASE_URL='', IS_PRODUCTION=False, ALLOW_PUBLIC_SETUP=True)
        self.overrides.start()
        self.addCleanup(self.overrides.stop)
        store.init_auth_db()
        app = FastAPI()
        app.add_middleware(PrivateAccessMiddleware)
        app.include_router(auth_router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def assert_unavailable(self):
        for path in ('/', '/login', '/setup', '/api/auth/check'):
            response = self.client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 503, path)
            self.assertIn('no-store', response.headers['cache-control'])
            self.assertNotIn('name="admin_password"', response.text)
        self.assertEqual(self.client.post('/setup').status_code, 503)

    def test_missing_production_configuration(self):
        with patch.multiple(config, IS_PRODUCTION=True, ALLOW_PUBLIC_SETUP=False):
            self.assert_unavailable()

    def test_empty_database_production_never_offers_setup(self):
        with patch.object(config, 'ALLOW_PUBLIC_SETUP', False):
            self.assert_unavailable()
            self.assertFalse(store.complete_initial_setup('AdminTest123!', 'ViewerTest123!')[0])

    def test_marker_without_credentials_requires_recovery(self):
        with store.get_db_connection() as conn:
            store.set_meta_value(conn, 'setup_completed', '1')
        self.assert_unavailable()

    def test_lockfile_without_credentials_requires_recovery(self):
        store.write_setup_lockfile()
        self.assert_unavailable()

    def test_real_postgres_connection_failure(self):
        with patch.multiple(config, IS_PRODUCTION=True, ALLOW_PUBLIC_SETUP=False,
                            _raw_secret='test', AUTH_DATABASE_URL='postgresql://localhost:1/auth?sslmode=disable'):
            self.assert_unavailable()

    def test_concurrent_setup_only_one_winner(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda i: store.complete_initial_setup(
                'AdminTest123!', 'ViewerTest123!', f'admin{i}', f'viewer{i}'), range(2)))
        self.assertEqual(sum(ok for ok, _ in results), 1)
        with store.get_db_connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS cnt FROM auth_users').fetchone()['cnt'], 2)

    def test_lost_database_never_offers_production_setup(self):
        self.assertTrue(store.complete_initial_setup('AdminTest123!', 'ViewerTest123!')[0])
        with patch.multiple(config, AUTH_DB_PATH=str(Path(self.temp.name)/'replacement.sqlite3'),
                            ALLOW_PUBLIC_SETUP=False):
            store.init_auth_db()
            self.assert_unavailable()


if __name__ == '__main__':
    unittest.main()
