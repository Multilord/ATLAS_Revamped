"""Authenticated API boundary and administrative routes."""
import hmac
import re
import security


def establish(handler, db, write=False):
    user, session = security.authenticate(db, handler.headers.get('Cookie'))
    if write and not hmac.compare_digest(handler.headers.get('X-CSRF-Token', ''), session['csrf']):
        raise security.SecurityError('Session verification failed. Reload and retry.')
    handler.session = session
    return security.principal.set(user)


def authorize(path):
    if path.startswith('/api/auth/'):
        return
    if path.startswith('/api/admin/'):
        security.require('Administrator')
    elif path == '/api/security/screen':
        security.require('Consultant', 'Reviewer')
    elif path.endswith('/security-review') or path.endswith('/review'):
        security.require('Reviewer')
    elif path.endswith('/approval'):
        security.require('Approver')
    else:
        security.require('Consultant')


def get(handler, path, store):
    db = store.db
    if path == '/api/auth/me':
        handler.respond(200, dict(user=security.principal.get(), csrf=handler.session['csrf']))
        return True
    if path == '/api/admin/users':
        security.require('Administrator')
        handler.respond(200, {'users': [security.public(u) for u in db.users.find()]})
        return True
    if path == '/api/admin/audit':
        security.require('Administrator')
        rows = list(db.security_events.find({}, {'_id': 0}).sort('at', -1).limit(200))
        for row in rows:
            row['at'] = row['at'].isoformat()
        handler.respond(200, {'events': rows})
        return True
    return False


def post(handler, path, data, store, workspace):
    db = store.db
    if path == '/api/auth/bootstrap':
        handler.respond(201, security.bootstrap(db, data, workspace))
        return True
    if path == '/api/auth/login':
        token, csrf, user = security.login(db, data, handler.client_address[0])
        # This local-only server uses HTTP loopback. HTTPS deployments must enable Secure.
        handler.session_cookie = f'atlas_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'
        handler.respond(200, dict(user=user, csrf=csrf))
        return True
    if path == '/api/auth/logout':
        db.sessions.delete_one({'token_hash': handler.session['token_hash']})
        handler.session_cookie = 'atlas_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
        handler.respond(200, {'ok': True})
        return True
    if path == '/api/auth/password':
        user = security.principal.get()
        stored = db.users.find_one({'id': user['id']})
        if not security.password_matches(data.get('current_password'), stored['password_hash']):
            raise security.SecurityError('Current password is incorrect.')
        db.users.update_one({'id': user['id']}, {'$set': {'password_hash': security.password_hash(data.get('password'))}})
        db.sessions.delete_many({'user_id': user['id']})
        security.audit(db, 'password.changed', user['id'])
        handler.respond(200, {'ok': True})
        return True
    if path == '/api/admin/users':
        handler.respond(201, security.create_user(db, data, workspace=workspace))
        return True
    match = re.fullmatch(r'/api/admin/users/([a-f0-9]+)/disable', path)
    if match:
        user = security.require('Administrator')
        if match[1] == user['id']:
            raise ValueError('You cannot disable your own account.')
        db.users.update_one({'id': match[1]}, {'$set': {'active': False}})
        db.sessions.delete_many({'user_id': match[1]})
        security.audit(db, 'user.disabled', match[1])
        handler.respond(200, {'ok': True})
        return True
    if path == '/api/security/screen':
        if 'record_id' in data:
            kind = {'sources': 'source', 'investigations': 'investigation'}.get(data.get('record_kind'))
            if not kind or not isinstance(data['record_id'], str):
                raise ValueError('Select a valid record to screen.')
            record = store.get(data['record_id'], kind, include_chunks=True)
            if not record:
                raise security.SecurityError('Record not found.', 404)
            if data.get('revision') != record.get('revision'):
                raise security.SecurityError('Record changed. Reload before reviewing.', 409)
            handler.respond(200, {'findings': security.screen(security.record_text(record)), 'revision': record['revision']})
            return True
        text = data.get('content')
        if not isinstance(text, str) or len(text) > 120000:
            raise ValueError('Screen at most 120,000 characters.')
        handler.respond(200, {'findings': security.screen(text)})
        return True
    match = re.fullmatch(r'/api/(sources|investigations)/([A-Za-z0-9-]+)/redact', path)
    if match:
        kind = 'source' if match[1] == 'sources' else 'investigation'
        record = store.get(match[2], kind, include_chunks=True)
        if not record:
            raise security.SecurityError('Record not found.', 404)
        if data.get('revision') != record.get('revision'):
            raise security.SecurityError('Record changed. Reload before editing.', 409)
        if record.get('lifecycle_stage') == 'Closure':
            raise ValueError('Closed tickets cannot be revised through this editor.')
        title, content, notes = data.get('title'), data.get('content'), data.get('notes')
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200 or not isinstance(content, str) or not 1 <= len(content.strip()) <= (120000 if kind == 'source' else 12000) or not isinstance(notes, str) or not 5 <= len(notes.strip()) <= 4000:
            raise ValueError('Provide a title, bounded content and a revision reason.')
        record['title'] = title.strip()
        record['content' if kind == 'source' else 'description'] = content.strip()
        record['updated_at'] = security.now().isoformat()
        if kind == 'source':
            record['content_hash'] = security.digest(content.strip())
        else:
            record['analysis'] = None
            record['selected_source'] = None
            record['decisions'] = {}
            record.setdefault('solutioning', {}).setdefault('functional', {})['customer_problem'] = content.strip()
        record.setdefault('revision_history', []).append(dict(at=security.now().isoformat(), actor_id=security.principal.get()['id'], reason=notes.strip()))
        store.save(record, kind)
        handler.respond(200, {'ok': True})
        return True
    match = re.fullmatch(r'/api/(sources|investigations)/([A-Za-z0-9-]+)/security-review', path)
    if match:
        kind = 'source' if match[1] == 'sources' else 'investigation'
        record = store.get(match[2], kind, include_chunks=True)
        if not record:
            raise security.SecurityError('Record not found.', 404)
        if data.get('revision') != record.get('revision'):
            raise security.SecurityError('Record changed. Reload before reviewing.', 409)
        security.review_record(db, record, data)
        store.save(record, kind)
        handler.respond(200, {'security': record['security']})
        return True
    return False
