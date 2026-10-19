"""Local identity, request authorization, disclosure policy and security events.

No provider calls. Company SSO and external malware scanning are deployment integrations.
"""
import hashlib
import hmac
import json
import re
import secrets
import threading
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie, CookieError
from pathlib import Path

principal = ContextVar('principal', default=None)
ROLES = ('Viewer', 'Consultant', 'Reviewer', 'Approver', 'Administrator')
CLASSIFICATIONS = ('Internal', 'Confidential', 'Restricted')
_lock = threading.Lock()


class SecurityError(Exception):
    def __init__(self, message, status=403):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def actor():
    user = principal.get()
    return f'{user["name"]} ({user["id"]})' if user else 'Local maintenance'


def public(user):
    return {k: user[k] for k in ('id', 'name', 'username', 'roles', 'customers', 'active')}


def require(*roles):
    user = principal.get()
    if not user:
        raise SecurityError('Sign in to continue.', 401)
    if not set(roles) & set(user['roles']):
        raise SecurityError('Your role does not permit this action.')
    return user


def customer_allowed(customer, general=False):
    user = principal.get()
    return bool(user and (customer in user['customers'] or (general and customer == 'General')))


def password_hash(password, salt=None):
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError('Use a password of 12–256 characters.')
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return salt + ':' + value


def password_matches(password, stored):
    try:
        return hmac.compare_digest(password_hash(password, stored.split(':')[0]), stored)
    except (ValueError, TypeError, AttributeError):
        return False


def initialize(db):
    db.users.create_index('username', unique=True)
    db.users.create_index('id', unique=True)
    db.sessions.create_index('token_hash', unique=True)
    db.sessions.create_index('expires_at', expireAfterSeconds=0)
    db.auth_attempts.create_index('key', unique=True)
    db.auth_attempts.create_index('expires_at', expireAfterSeconds=0)
    db.security_events.create_index('at')


def audit(db, action, record_id='', result='allowed', **details):
    user = principal.get()
    # Only caller-controlled metadata; never request bodies, passwords or document text.
    db.security_events.insert_one(dict(id=secrets.token_hex(16), at=now(),
        actor_id=user['id'] if user else 'anonymous', action=action,
        record_id=record_id, result=result, **details))


def bootstrap_path():
    return Path(__file__).resolve().parent / 'data' / 'bootstrap-token.txt'


def prepare_bootstrap(db):
    if db.users.count_documents({}):
        return
    path = bootstrap_path()
    path.parent.mkdir(exist_ok=True)
    try:
        with path.open('x', encoding='utf-8') as stream:
            stream.write(secrets.token_urlsafe(32))
    except FileExistsError:
        pass


def create_user(db, data, bootstrap=False, workspace='My Workspace'):
    if not bootstrap:
        require('Administrator')
    username = data.get('username', '').strip().casefold()
    name = data.get('name', '').strip()
    roles, customers = data.get('roles', ['Consultant']), data.get('customers', [workspace])
    if not re.fullmatch(r'[a-z0-9@._+-]{3,150}', username) or not 1 <= len(name) <= 150:
        raise ValueError('Provide a name and a username using letters, numbers, @, dot, dash or underscore.')
    if not isinstance(roles, list) or not roles or any(r not in ROLES for r in roles):
        raise ValueError('Select valid roles.')
    if not isinstance(customers, list) or not customers or len(customers) > 50 or any(not isinstance(c, str) or not c.strip() or len(c) > 200 or c == 'General' for c in customers):
        raise ValueError('Assign 1–50 explicit customer scopes. General is not a membership.')
    if bootstrap:
        roles = ['Administrator', 'Consultant', 'Reviewer', 'Approver']
    user = dict(id=secrets.token_hex(16), username=username, name=name, roles=roles,
        customers=list(dict.fromkeys(c.strip() for c in customers)), active=True,
        password_hash=password_hash(data.get('password')), created_at=now())
    if db.users.find_one({'username': username}):
        raise ValueError('This username already exists.')
    db.users.insert_one(user.copy())
    audit(db, 'user.created', user['id'])
    return public(user)


def bootstrap(db, data, workspace):
    with _lock:
        if db.users.count_documents({}):
            raise SecurityError('Initial setup is already complete.')
        path = bootstrap_path()
        if not path.exists() or not hmac.compare_digest(str(data.get('token', '')), path.read_text().strip()):
            raise SecurityError('Invalid local setup token.')
        customers = [workspace]
        if workspace in ('My Workspace', 'All'):
            customers += db.sources.distinct('customer') + db.investigations.distinct('customer')
        customers = sorted({c for c in customers if isinstance(c, str) and c and c != 'General'})
        result = create_user(db, {**data, 'customers': customers}, bootstrap=True, workspace=workspace)
        path.unlink(missing_ok=True)
        return result


def login(db, data, peer):
    username = str(data.get('username', '')).strip().casefold()[:150]
    # Both account and client limits: changing usernames does not bypass the client limit.
    keys = [digest('user:' + username), digest('peer:' + peer)]
    with _lock:
        for key in keys:
            attempts = db.auth_attempts.find_one({'key': key})
            if attempts and attempts['expires_at'].replace(tzinfo=timezone.utc) > now() and attempts['count'] >= 10:
                raise SecurityError('Too many sign-in attempts. Retry in 15 minutes.', 429)
        user = db.users.find_one({'username': username, 'active': True})
        valid = password_matches(data.get('password'), user['password_hash'] if user else 'invalid:invalid')
        if not user or not valid:
            for key in keys:
                old = db.auth_attempts.find_one({'key': key})
                count = old['count'] if old and old['expires_at'].replace(tzinfo=timezone.utc) > now() else 0
                db.auth_attempts.update_one({'key': key}, {'$set': {'count': count + 1, 'expires_at': now() + timedelta(minutes=15)}}, upsert=True)
            audit(db, 'login', result='denied')
            raise SecurityError('Incorrect username or password.', 401)
        db.auth_attempts.delete_one({'key': keys[0]})
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.sessions.insert_one(dict(token_hash=digest(token), user_id=user['id'], csrf=csrf,
        expires_at=now() + timedelta(hours=8), last_seen=now()))
    identity_token = principal.set(public(user))
    try:
        audit(db, 'login', result='allowed')
    finally:
        principal.reset(identity_token)
    return token, csrf, public(user)


def authenticate(db, cookie_header):
    try:
        cookies = SimpleCookie(cookie_header or '')
        token = cookies['atlas_session'].value
    except (KeyError, ValueError, CookieError):
        raise SecurityError('Sign in to continue.', 401) from None
    session = db.sessions.find_one({'token_hash': digest(token)})
    if not session or session['expires_at'].replace(tzinfo=timezone.utc) <= now() or session['last_seen'].replace(tzinfo=timezone.utc) < now() - timedelta(minutes=30):
        raise SecurityError('Session expired. Sign in again.', 401)
    user = db.users.find_one({'id': session['user_id'], 'active': True})
    if not user:
        raise SecurityError('Account disabled. Contact an administrator.', 401)
    db.sessions.update_one({'token_hash': session['token_hash']}, {'$set': {'last_seen': now()}})
    return public(user), session


PATTERNS = (
    ('Possible credential', r'(?i)\b(?:password|passwd|api[_ -]?key|client[_ -]?secret|access[_ -]?token)\s*[:=]\s*["\']?[^\s"\']{4,}'),
    ('Private key', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    ('Credential in connection URL', r'(?i)\b(?:mongodb(?:\+srv)?|https?|postgres(?:ql)?)://[^\s/:]+:[^\s/@]+@'),
    ('Email address', r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
    ('Possible instruction injection', r'(?i)(?:ignore|disregard|override)\s+(?:(?:all|the|your|previous|prior|system)\s+){0,5}(?:instructions|rules|prompt)|(?:system|developer)\s*(?:message|prompt)\s*:|(?:reveal|exfiltrate)\s+(?:the\s+)?(?:secrets|credentials|system prompt)'),
    ('Hidden direction/control character', '[\u200b-\u200f\u202a-\u202e\u2066-\u2069]'),
)


def screen(text):
    return [label for label, pattern in PATTERNS if re.search(pattern, text)]


def content_payload(record):
    # Everything submitted to retrieval, including metadata and later consultant context.
    keys = ('title', 'content', 'description', 'application', 'platform', 'module', 'version',
        'business_process', 'error_code', 'customisation', 'solution', 'steps', 'source_updated_at',
        'solutioning', 'timeline', 'source_links', 'type', 'priority', 'customer')
    payload = {k: record.get(k) for k in keys}
    payload['timeline'] = [e.get('text', '') for e in record.get('timeline', []) if e.get('kind') in ('Note', 'Test', 'Communication', 'Attachment')][-15:]
    return payload


def content_fingerprint(record):
    return digest(json.dumps(content_payload(record), sort_keys=True, default=str))


def record_text(record):
    return json.dumps(content_payload(record), ensure_ascii=False, default=str)


def ai_allowed(record):
    policy = record.get('security') or {}
    return (policy.get('status') == 'Approved' and policy.get('classification') == 'Internal'
        and policy.get('external_ai') is True and policy.get('hash') == content_fingerprint(record)
        and not screen(record_text(record)))


def enforce_ai(record):
    if not ai_allowed(record):
        raise SecurityError('AI processing is blocked. An independent reviewer must approve the current content as Internal and allow external AI; sensitive or suspicious content must be removed first.')


def review_record(db, record, data):
    user = require('Reviewer')
    if user['id'] in (record.get('created_by_id'), record.get('content_editor_id')):
        raise SecurityError('An independent reviewer must review this record.')
    classification, status = data.get('classification'), data.get('status')
    if classification not in CLASSIFICATIONS or status not in ('Approved', 'Rejected'):
        raise ValueError('Select a classification and review decision.')
    notes = data.get('notes', '')
    if not isinstance(notes, str) or not 5 <= len(notes.strip()) <= 4000:
        raise ValueError('Provide review notes (5–4000 characters).')
    if not isinstance(data.get('external_ai', False), bool):
        raise ValueError('External AI permission must be a boolean.')
    findings = screen(record_text(record))
    external = data.get('external_ai', False)
    if external and classification != 'Internal':
        raise SecurityError('Confidential and Restricted content must remain local. External AI permission requires Internal classification under your company policy.')
    if external and status != 'Approved':
        raise SecurityError('External AI permission requires an Approved review decision.')
    if external and findings:
        raise SecurityError('External AI is blocked by screening findings: ' + ', '.join(findings) + '. Redact or revise the flagged content before review.')
    previous = record.get('security')
    if previous:
        record.setdefault('security_history', []).append(previous)
    record['security'] = dict(status=status, classification=classification, external_ai=external,
        findings=findings, reviewer_id=user['id'], reviewer=actor(), at=now().isoformat(),
        notes=notes.strip(), hash=content_fingerprint(record))
    audit(db, 'security.review.intent', record['id'], decision=status, content_hash=record['security']['hash'])


def proposal_hash(item):
    return digest(json.dumps({'solutioning': item.get('solutioning'), 'selected_source': item.get('selected_source')}, sort_keys=True))


def approval(item, status, notes):
    user = require('Approver')
    if user['id'] in (item.get('created_by_id'), item.get('proposal_author_id')):
        raise SecurityError('An independent approver must decide this change.')
    return dict(status=status, notes=notes, at=now().isoformat(), author=actor(),
        actor_id=user['id'], proposal_hash=proposal_hash(item), revision=item.get('revision'))
