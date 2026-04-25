import json
import time
import uuid
from urllib import request, error

BASE = 'http://localhost:8000'


def now():
    return time.perf_counter()


def req(method, path, data=None, headers=None, timeout=30):
    url = BASE + path
    body = None
    h = {'Accept': 'application/json'}
    if headers:
        h.update(headers)
    if data is not None:
        body = json.dumps(data).encode('utf-8')
        h['Content-Type'] = 'application/json'
    r = request.Request(url, data=body, headers=h, method=method)
    t0 = now()
    try:
        with request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
            dt = now() - t0
            ctype = resp.headers.get('Content-Type', '')
            parsed = None
            if 'application/json' in ctype:
                try:
                    parsed = json.loads(raw.decode('utf-8')) if raw else None
                except Exception:
                    parsed = None
            return resp.status, dt, parsed, raw
    except error.HTTPError as e:
        raw = e.read()
        dt = now() - t0
        parsed = None
        try:
            parsed = json.loads(raw.decode('utf-8')) if raw else None
        except Exception:
            parsed = None
        return e.code, dt, parsed, raw


def pick_token(payload):
    if not isinstance(payload, dict):
        return None
    for k in ('access_token', 'token', 'jwt', 'bearer_token'):
        v = payload.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def pick_session_id(payload):
    if not isinstance(payload, dict):
        return None
    for k in ('session_id', 'id'):
        v = payload.get(k)
        if isinstance(v, str) and v:
            return v
    s = payload.get('session')
    if isinstance(s, dict):
        for k in ('session_id', 'id'):
            v = s.get(k)
            if isinstance(v, str) and v:
                return v
    return None


def session_has_iteration(payload, n):
    if not isinstance(payload, dict):
        return False
    li = payload.get('latest_iteration')
    if isinstance(li, int) and li >= n:
        return True
    iters = payload.get('iterations')
    if isinstance(iters, list):
        if len(iters) > n:
            return True
        for it in iters:
            if isinstance(it, dict):
                iv = it.get('iteration')
                if iv == n:
                    return True
    current = payload.get('current_iteration')
    if isinstance(current, int) and current >= n:
        return True
    return False


def wait_for_iteration(session_id, iteration, auth_headers, max_wait=20.0, step=1.0):
    start = now()
    attempts = 0
    last_session_status = None
    while now() - start <= max_wait:
        attempts += 1
        s_code, s_dt, s_json, _ = req('GET', f'/sessions/{session_id}', headers=auth_headers)
        last_session_status = s_code
        found = session_has_iteration(s_json, iteration)
        i_code, i_dt, _, i_raw = req('GET', f'/sessions/{session_id}/image/{iteration}', headers=auth_headers)
        elapsed = now() - start
        print(f'poll iteration {iteration} attempt {attempts}: session={s_code} ({s_dt:.3f}s), image={i_code} ({i_dt:.3f}s), elapsed={elapsed:.2f}s')
        if i_code == 200 and i_raw:
            return True, elapsed, attempts, last_session_status
        if found and i_code == 200:
            return True, elapsed, attempts, last_session_status
        time.sleep(step)
    return False, now() - start, attempts, last_session_status


def main():
    t0 = now()

    code, dt, _, _ = req('GET', '/docs')
    print(f'1) GET /docs -> {code} in {dt:.3f}s')
    if code >= 400:
        code2, dt2, _, _ = req('GET', '/openapi.json')
        print(f'1b) GET /openapi.json -> {code2} in {dt2:.3f}s')

    suffix = uuid.uuid4().hex[:8]
    email = f'apitest_{suffix}@example.com'
    username = f'apitest_{suffix}'
    password = 'Passw0rd!'

    reg_payload = {'username': username, 'email': email, 'password': password}
    code, dt, reg_json, _ = req('POST', '/auth/register', data=reg_payload)
    print(f'2) POST /auth/register -> {code} in {dt:.3f}s')

    token = pick_token(reg_json)
    if not token:
        login_payload = {'email': email, 'password': password}
        code_l, dt_l, login_json, _ = req('POST', '/auth/login', data=login_payload)
        print(f'2b) POST /auth/login -> {code_l} in {dt_l:.3f}s')
        token = pick_token(login_json)
        if not token:
            print('FAILED: no auth token from register/login')
            return

    auth_headers = {'Authorization': f'Bearer {token}'}

    gen_payload = {'prompt': 'A small red apple on a wooden table'}
    code, dt, gen_json, _ = req('POST', '/generate-session', data=gen_payload, headers=auth_headers, timeout=60)
    print(f'3) POST /generate-session -> {code} in {dt:.3f}s')
    session_id = pick_session_id(gen_json)
    print(f'   session_id={session_id}')
    if code >= 400 or not session_id:
        print('FAILED: could not create session')
        return

    ok0, wait0, attempts0, s0 = wait_for_iteration(session_id, 0, auth_headers, max_wait=20.0, step=1.0)
    print(f'4) iteration 0 image fetchable={ok0} after {wait0:.2f}s ({attempts0} polls), last /sessions status={s0}')

    edit_payload = {'session_id': session_id, 'edit_instruction': 'Make the apple slightly brighter', 'strength': 0.35}
    code, dt, _, _ = req('POST', '/edit', data=edit_payload, headers=auth_headers, timeout=60)
    print(f'5) POST /edit -> {code} in {dt:.3f}s')

    ok1, wait1, attempts1, s1 = wait_for_iteration(session_id, 1, auth_headers, max_wait=20.0, step=1.0)
    print(f'6) iteration 1 image fetchable={ok1} after {wait1:.2f}s ({attempts1} polls), last /sessions status={s1}')

    total = now() - t0
    print(f'SUMMARY: total={total:.2f}s; iter0={ok0}; iter1={ok1}; iter1_without_refresh={ok1}')


if __name__ == '__main__':
    main()
