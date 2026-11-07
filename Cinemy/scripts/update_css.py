import os

with open('src/styles/components.css', 'r', encoding='utf-8') as f:
    text = f.read()

old_auth_block = '''
.btn-auth-logout {
  background: var(--card);
  border-color: rgba(239, 68, 68, 0.3);
  color: #f87171;
  font-size: var(--font-size-xs);
  height: 32px;
  padding: 0 10px;
}
.btn-auth-logout:hover {
  background: var(--error-bg);
  border-color: var(--error);
  color: #fff;
}

.btn-admin {
  background: var(--card);
  border-color: rgba(59, 130, 246, 0.4);
  color: #60a5fa;
  font-size: var(--font-size-xs);
  height: 32px;
  padding: 0 10px;
  text-decoration: none;
}
.btn-admin:hover {
  background: rgba(59, 130, 246, 0.15);
  color: #fff;
}'''

new_auth_block = '''
.btn-auth-logout {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: var(--dim);
  font-size: var(--font-size-xs);
  height: 32px;
  padding: 0 10px;
  transition: all var(--transition-fast);
}
.btn-auth-logout:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.25);
  color: #fff;
}

.btn-admin {
  background: rgba(255, 123, 57, 0.1);
  border: 1px solid rgba(255, 123, 57, 0.3);
  color: var(--accent);
  font-size: var(--font-size-xs);
  height: 32px;
  padding: 0 10px;
  text-decoration: none;
  transition: all var(--transition-fast);
}
.btn-admin:hover {
  background: var(--accent);
  border-color: var(--accent);
  color: #090a0f;
}'''

old_pill_select = '''
.pill-select {
  appearance: none;
  -webkit-appearance: none;
  background-color: var(--bg-elevated);
  padding: 6px 30px 6px 14px;
  border: 1.5px solid #ec4899;
  color: #f472b6;
  font-weight: 700;
  border-radius: var(--radius-full);
  font-size: var(--font-size-sm);
  cursor: pointer;
  outline: none;
  height: 33px;
  line-height: 1;
  background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23f472b6' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
  background-repeat: no-repeat;
  background-position: right 10px center;
  background-size: 12px;
}

.pill-select:focus {
  border-color: #ec4899;
  box-shadow: 0 0 0 2px rgba(236, 72, 153, 0.35);
}

.pill-select.active {
  background-color: #db2777;
  color: #fff;
  border-color: #ec4899;
  background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23ffffff' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
}'''

new_pill_select = '''
.pill-select {
  appearance: none;
  -webkit-appearance: none;
  background-color: var(--card);
  padding: 6px 30px 6px 14px;
  border: 1px solid var(--border);
  color: var(--dim);
  font-weight: 500;
  border-radius: var(--radius-full);
  font-size: var(--font-size-sm);
  cursor: pointer;
  outline: none;
  height: 33px;
  line-height: 1;
  background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
  background-repeat: no-repeat;
  background-position: right 10px center;
  background-size: 12px;
  transition: all var(--transition-fast);
}

.pill-select:hover {
  border-color: rgba(255, 255, 255, 0.25);
  color: #fff;
}

.pill-select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-glow);
}

.pill-select.active {
  background-color: var(--accent);
  color: #090a0f;
  font-weight: 700;
  border-color: var(--accent);
  background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23090a0f' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
}'''

assert old_auth_block in text, 'old_auth_block not found in components.css'
assert old_pill_select in text, 'old_pill_select not found in components.css'

text = text.replace(old_auth_block, new_auth_block).replace(old_pill_select, new_pill_select)
with open('src/styles/components.css', 'w', encoding='utf-8') as f:
    f.write(text)
print('components.css updated!')

