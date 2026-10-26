"""Run with python -m scratch.test_auth_durable. Uses only disposable storage."""
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

@contextmanager
def database(path):
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()

def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]

def run():
    with tempfile.TemporaryDirectory(prefix='auth-resilience-') as tmp:
        tmp = Path(tmp)
        db = tmp / 'auth.sqlite3'
        fault = tmp / 'fault'
        env = {**os.environ, 'PYTHON_DOTENV_DISABLED':'1', 'ENVIRONMENT':'development',
               'RENDER':'false', 'AUTH_DATABASE_URL':'', 'AUTH_DB_PATH':str(db),
               'AUTH_TEST_FAULT':str(fault), 'SESSION_SECRET':'isolated-test-secret',
               'ADMIN_INITIAL_PASSWORD':'', 'ADMIN_PASSWORD':'',
               'VIEWER_INITIAL_PASSWORD':'', 'VIEWER_PASSWORD':''}
        ports = [port(), port()]
        urls = [f'http://127.0.0.1:{p}' for p in ports]
        processes = []
        log = (tmp / 'server.log').open('w')
        def start(index):
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'scratch.auth_resilience_app:app',
                '--host','127.0.0.1','--port',str(ports[index])], cwd=ROOT, env=env, stdout=log, stderr=log)
            processes.append(process)
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('Test server exited')
                try:
                    httpx.get(urls[index] + '/login', timeout=1)
                    return process
                except httpx.TransportError:
                    time.sleep(.1)
            raise RuntimeError('Test server did not start')
        try:
            first = start(0)
            with httpx.Client(base_url=urls[0]) as client:
                assert client.get('/setup').status_code == 200
                response = client.post('/setup', data={'admin_password':'AdminTest123!',
                    'confirm_admin_password':'AdminTest123!', 'viewer_password':'ViewerTest123!',
                    'csrf_token':client.cookies['cms_csrf']})
                assert response.status_code == 303, response.text
            start(1)
            with database(db) as conn:
                initial = conn.execute('SELECT username,password_hash FROM auth_users ORDER BY username').fetchall()
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, channel=os.getenv('AUTH_TEST_BROWSER', 'msedge'))
                contexts = [browser.new_context(), browser.new_context()]
                pages = [context.new_page() for context in contexts]
                def login(page, url):
                    page.goto(url + '/login')
                    page.locator('input[name=username]').fill('viewer')
                    page.locator('input[name=password]').fill('ViewerTest123!')
                    page.locator('button[type=submit]').click()
                    page.wait_for_url(url + '/')
                    assert 'Protected catalogue' in page.content()
                for page, url in zip(pages, urls):
                    login(page, url)
                print('PASS: two independent browser contexts on two server processes')
                first.terminate()
                first.wait(timeout=10)
                start(0)
                for page, url in zip(pages, urls):
                    page.goto(url + '/')
                    assert 'Protected catalogue' in page.content()
                    page.goto(url + '/setup')
                    assert '/setup' not in page.url
                print('PASS: actual process restart preserves both sessions and locks setup')
                for page, url in zip(pages, urls):
                    page.context.clear_cookies()
                    login(page, url)
                print('PASS: original credentials work after restart')
                for mode in ('state', 'session'):
                    fault.write_text(mode)
                    for page, url in zip(pages, urls):
                        response = page.goto(url + '/')
                        assert response.status == 503
                        assert 'Service Temporarily Unavailable' in page.content()
                        assert 'name="admin_password"' not in page.content()
                        for method in ('get','post'):
                            result = getattr(httpx, method)(url + '/setup')
                            assert result.status_code in ((303, 503) if method == 'get' else (403, 503))
                            assert 'name="admin_password"' not in result.text
                    fault.unlink()
                print('PASS: state and late session-query outages deny access and setup')
                with database(db) as conn:
                    conn.execute("DELETE FROM auth_meta WHERE key='setup_completed'")
                    conn.execute("DELETE FROM auth_users WHERE role='admin'")
                for page, url in zip(pages, urls):
                    page.goto(url + '/')
                    assert 'Protected catalogue' in page.content()
                    assert httpx.post(url + '/setup').status_code == 403
                print('PASS: viewer-only credentials lock setup despite missing metadata')
                with database(db) as conn:
                    assert conn.execute("SELECT password_hash FROM auth_users WHERE username='viewer'").fetchone()[0] == dict(initial)['viewer']
                    conn.execute('UPDATE auth_sessions SET expires_at=0')
                for page, url in zip(pages, urls):
                    page.goto(url + '/')
                    assert '/login' in page.url
                    login(page, url)
                with database(db) as conn:
                    conn.execute('DELETE FROM auth_sessions')
                for page, url in zip(pages, urls):
                    page.goto(url + '/')
                    assert '/login' in page.url
                print('PASS: expired and revoked sessions go to login; hashes preserved')
                frontend = (ROOT / 'server/static/index.html').read_text(encoding='utf-8')
                helper = frontend.split('function showAuthStorageUnavailable()', 1)[1].split('const _origFetch', 1)[0]
                pages[0].evaluate('window.showAuthStorageUnavailable = function()' + helper)
                pages[0].evaluate('showAuthStorageUnavailable()')
                assert pages[0].locator('#auth-storage-unavailable').is_visible()
                assert pages[0].get_by_role('button', name='Retry Connection').is_visible()
                print('PASS: frontend storage-error overlay renders a retry action')
                browser.close()
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)
            log.close()

if __name__ == '__main__':
    run()
