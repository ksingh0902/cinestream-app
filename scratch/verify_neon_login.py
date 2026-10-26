"""Verify live Neon through the app driver; URL is read privately, never saved."""
import getpass
import os

os.environ['AUTH_DATABASE_URL'] = getpass.getpass('Neon connection URL (hidden): ')
os.environ['ENVIRONMENT'] = 'production'

from dotenv import dotenv_values
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.auth.middleware import PrivateAccessMiddleware
from app.auth.routes import auth_router

app = FastAPI()
app.add_middleware(PrivateAccessMiddleware)
app.include_router(auth_router)

def verify():
    values = dotenv_values('.env')
    for username in ('admin', 'viewer'):
        with TestClient(app, base_url='https://testserver') as client:
            response = client.get('/login')
            assert response.status_code == 200, response.status_code
            password = values[username.upper() + '_INITIAL_PASSWORD']
            if username == 'viewer':
                password = password.strip()
            response = client.post('/login', data={
                'username': username, 'password': password,
                'csrf_token': client.cookies['cms_csrf'],
            }, follow_redirects=False)
            assert response.status_code == 303, response.status_code
            try:
                state = client.get('/api/auth/check').json()
                assert state['authenticated'] and state['role'] == username
                assert client.post('/setup', follow_redirects=False).status_code == 403
                print(f'PASS: {username} authenticates through psycopg against Neon; setup denied', flush=True)
            finally:
                client.post('/logout', follow_redirects=False)

if __name__ == '__main__':
    verify()
