"""Isolated test server: real auth routes/middleware, no catalogue crawler."""
import os
from pathlib import Path
import sqlite3
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from app.auth import store, service
from app.auth.middleware import PrivateAccessMiddleware
from app.auth.routes import auth_router

store.init_auth_db()
original_connect = store.get_db_connection
original_session = service.get_session
fault = Path(os.environ['AUTH_TEST_FAULT'])

def connect():
    if fault.exists() and fault.read_text() == 'state':
        raise sqlite3.OperationalError('Injected storage outage')
    return original_connect()

def session(session_id):
    if fault.exists() and fault.read_text() == 'session':
        raise sqlite3.OperationalError('Injected session query outage')
    return original_session(session_id)

store.get_db_connection = connect
service.get_session = session
app = FastAPI()
app.add_middleware(PrivateAccessMiddleware)
app.include_router(auth_router)

@app.get('/')
def protected():
    return HTMLResponse('<h1>Protected catalogue</h1>')
