"""Loopback-only development server. Python 3.10+, standard library only."""
import argparse
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from engine import classify, retrieve
from seed import CUSTOMER, SOURCES, investigations

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('SIE_DATABASE', str(ROOT / 'data' / 'solution-engine.sqlite3')))
TYPES = ('Incident', 'Service request', 'Problem', 'Change request')
OUTCOMES = ('Resolved', 'Workaround', 'Unresolved', 'Escalated', 'Closed - other')


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, customer TEXT NOT NULL, body TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, at TEXT, action TEXT, record_id TEXT, customer TEXT)')
        for item in SOURCES:
            db.execute('INSERT OR IGNORE INTO records VALUES (?, ?, ?, ?)', (item['id'], 'source', item['customer'], json.dumps(item)))
        for item in investigations():
            db.execute('INSERT OR IGNORE INTO records VALUES (?, ?, ?, ?)', (item['id'], 'investigation', item['customer'], json.dumps(item)))


def records(kind):
    with connect() as db:
        return [json.loads(r['body']) for r in db.execute('SELECT body FROM records WHERE kind=? AND (customer=? OR (kind=? AND customer=?))', (kind, CUSTOMER, 'source', 'General'))]


def get_record(id, kind):
    return next((r for r in records(kind) if r['id'] == id), None)


def save(item, action):
    with connect() as db:
        db.execute('INSERT INTO records VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body WHERE records.customer=excluded.customer AND records.kind=excluded.kind', (item['id'], 'investigation', CUSTOMER, json.dumps(item)))
        db.execute('INSERT INTO audit(at,action,record_id,customer) VALUES (?,?,?,?)', (now(), action, item['id'], CUSTOMER))


def required_text(data, key, limit=12000):
    value = data.get(key, '')
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{key.replace("_", " ").capitalize()} is required and must be under {limit} characters.')
    return value.strip()


def parse_intake(data):
    raw = required_text(data, 'content', 100000)
    filename = data.get('filename', '')
    if not isinstance(filename, str) or len(filename) > 255:
        raise ValueError('Invalid filename.')
    if filename and Path(filename).suffix.lower() not in ('.txt', '.json'):
        raise ValueError('This prototype supports UTF-8 TXT and JSON ticket exports.')
    obj = {}
    if filename.lower().endswith('.json') or raw.lstrip().startswith('{'):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError('Invalid JSON. Check the ticket export and try again.')
        if not isinstance(obj, dict):
            raise ValueError('Ticket JSON must be an object.')
        for key in ('title', 'description', 'application', 'version', 'ticket_id', 'error_code', 'customisation', 'type', 'priority'):
            if key in obj and not isinstance(obj[key], str):
                raise ValueError(f'{key} must be text.')
        if obj.get('customer', CUSTOMER) != CUSTOMER:
            raise ValueError('This demo session is authorised only for ' + CUSTOMER + '.')
    timeline = obj.get('timeline', [])
    if not isinstance(timeline, list) or len(timeline) > 200:
        raise ValueError('Timeline must contain at most 200 entries.')
    cleaned = []
    for event in timeline:
        if not isinstance(event, dict):
            raise ValueError('Each timeline entry must be an object.')
        stamp = required_text(event, 'at', 50)
        try:
            dt = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                raise ValueError()
            stamp = dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            raise ValueError('Timeline timestamps must be ISO 8601 with a timezone.')
        cleaned.append(dict(at=stamp, text=required_text(event, 'text'), kind='Communication', author=str(event.get('author', 'Imported'))[:120], source=filename or 'Pasted export'))
    cleaned.sort(key=lambda event: event['at'])
    description = obj.get('description', raw)
    if len(description) > 12000:
        raise ValueError('Description exceeds 12,000 characters. Split communications into a JSON timeline.')
    error = re.search(r'\b(?:[A-Z][0-9]\s?\d{3}|Z[A-Z]+_\d+|AUTH_\d+|HTTP\s\d+)\b', description)
    return dict(title=obj.get('title', next((line for line in raw.splitlines() if line.strip()), '')[:120]), description=description[:12000], ticket_id=obj.get('ticket_id', ''), application=obj.get('application', 'SAP Finance' if re.search('invoice|vendor|payment', description, re.I) else 'SAP Procurement' if re.search('purchase|approval', description, re.I) else ''), version=obj.get('version', ''), error_code=obj.get('error_code', error.group() if error else ''), customisation=obj.get('customisation', ''), type=obj.get('type', 'Incident'), priority=obj.get('priority', 'Medium'), customer=CUSTOMER, timeline=cleaned, filename=filename)


def create_investigation(data):
    if data.get('customer', CUSTOMER) != CUSTOMER:
        raise ValueError('Customer scope is not authorised.')
    item = {key: required_text(data, key, size) for key, size in [('title', 200), ('description', 12000), ('application', 100), ('version', 100)]}
    for key in ('ticket_id', 'error_code', 'customisation'):
        val = data.get(key, '')
        if not isinstance(val, str) or len(val) > 500:
            raise ValueError('Invalid ' + key)
        item[key] = val.strip()
    if data.get('type') not in TYPES or data.get('priority') not in ('Low', 'Medium', 'High', 'Critical'):
        raise ValueError('Select a valid ticket type and priority.')
    # Revalidate imported history at the write boundary.
    timeline = parse_intake({'content': json.dumps({'description': item['description'], 'timeline': data.get('timeline', [])})})['timeline']
    stamp = now()
    item.update(id='INV-' + uuid.uuid4().hex[:8].upper(), customer=CUSTOMER, type=data['type'], priority=data['priority'], status='New', created_at=stamp, updated_at=stamp, timeline=timeline, analysis=None, decisions={}, selected_source=None, outcome=None, demo=False)
    item['timeline'].append(dict(at=stamp, kind='Intake', text='Ticket context reviewed and investigation created.', author='Demo consultant', source=item['ticket_id'] or 'Manual intake'))
    save(item, 'created')
    return item


def update_investigation(item, action, data):
    if action == 'analyze':
        if item.get('outcome'):
            raise ValueError('This investigation has a recorded outcome. Create a new investigation for further work.')
        item['analysis'] = retrieve(item, records('source'))
        item['decisions'] = {}
        item['selected_source'] = None
        item['status'] = 'In progress'
        message = 'Evidence search completed: ' + item['analysis']['state'] + '.'
    elif action == 'decision':
        if item.get('outcome'):
            raise ValueError('Recommendations cannot be changed after recording an outcome.')
        source_id = required_text(data, 'source_id', 100)
        if source_id not in [r['source_id'] for r in (item.get('analysis') or {}).get('results', [])]:
            raise ValueError('Recommendation is not part of this investigation.')
        if data.get('decision') not in ('Accepted', 'Rejected'):
            raise ValueError('Invalid decision.')
        item['decisions'][source_id] = data['decision']
        if data['decision'] == 'Accepted':
            previous = item.get('selected_source')
            if previous and previous != source_id:
                item['decisions'].pop(previous, None)
            item['selected_source'] = source_id
        elif item['selected_source'] == source_id:
            item['selected_source'] = None
        item['status'] = 'Awaiting validation' if item['selected_source'] else 'In progress'
        message = data['decision'] + ' recommendation ' + source_id + '.'
    elif action == 'note':
        if data.get('kind') not in ('Note', 'Test', 'Attachment'):
            raise ValueError('Invalid note type.')
        message = required_text(data, 'text')
        if item.get('analysis') and not item.get('outcome'):
            item['analysis'] = None
            item['decisions'] = {}
            item['selected_source'] = None
            item['status'] = 'In progress'
    elif action == 'outcome':
        if item.get('outcome'):
            raise ValueError('An outcome has already been recorded.')
        status = data.get('status')
        if status not in OUTCOMES:
            raise ValueError('Select a valid outcome.')
        notes = required_text(data, 'notes')
        flags = ('tested', 'customer_confirmed', 'approved', 'developed', 'deployed', 'verified')
        if any(k in data and not isinstance(data[k], bool) for k in flags):
            raise ValueError('Validation fields must be true or false.')
        if status == 'Resolved' and not (data.get('tested') and data.get('customer_confirmed')):
            raise ValueError('A resolved outcome requires recorded testing and customer confirmation.')
        if status == 'Resolved' and item['type'] == 'Change request' and not all(data.get(k) for k in ('approved', 'developed', 'deployed', 'verified')):
            raise ValueError('A resolved change requires approval, development, deployment and verification.')
        if status in ('Resolved', 'Workaround') and not item.get('selected_source') and not data.get('alternative_solution', '').strip():
            raise ValueError('Select a recommendation or document the alternative solution used.')
        if data.get('usefulness', 'Not rated') not in ('Useful', 'Partly useful', 'Not useful', 'Not rated'):
            raise ValueError('Invalid feedback.')
        item['outcome'] = dict(status=status, notes=notes, recorded_at=now(), selected_source=item.get('selected_source'), alternative_solution=str(data.get('alternative_solution', ''))[:12000], usefulness=data.get('usefulness', 'Not rated'), **{k: bool(data.get(k)) for k in flags})
        item['status'] = status
        message = 'Consultant recorded outcome: ' + status + '. ' + notes
    else:
        raise ValueError('Unknown action.')
    item['updated_at'] = now()
    item['timeline'].append(dict(at=item['updated_at'], kind=data.get('kind', 'Note') if action == 'note' else action.capitalize(), text=message, author='Demo consultant', source='Investigation workspace'))
    save(item, action)
    return item


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, content_type='application/json; charset=utf-8'):
        payload = json.dumps(body).encode() if content_type.startswith('application/json') else body
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(payload)

    def trusted_host(self):
        return self.headers.get('Host', '') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def do_GET(self):
        if not self.trusted_host():
            return self.respond(403, {'error': 'Untrusted host.'})
        path = urlsplit(self.path).path
        if path == '/api/state':
            return self.respond(200, dict(customer=CUSTOMER, user='Alex Morgan', mode='Local prototype', investigations=sorted(records('investigation'), key=lambda r: r['updated_at'], reverse=True), sources=records('source')))
        if path == '/api/health':
            return self.respond(200, {'status': 'ok'})
        assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/styles.css': ('styles.css', 'text/css; charset=utf-8')}
        if path in assets:
            filename, mime = assets[path]
            return self.respond(200, (ROOT / 'static' / filename).read_bytes(), mime)
        return self.respond(404, {'error': 'Not found.'})

    def do_POST(self):
        origin = self.headers.get('Origin')
        if not self.trusted_host() or (origin and origin not in {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}):
            return self.respond(403, {'error': 'Untrusted request origin.'})
        if self.headers.get_content_type() != 'application/json':
            return self.respond(415, {'error': 'Use application/json.'})
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 200000:
                return self.respond(413, {'error': 'Request must be under 200 KB.'})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object.')
            path = urlsplit(self.path).path
            if path == '/api/intake':
                return self.respond(200, parse_intake(data))
            if path == '/api/investigations':
                return self.respond(201, create_investigation(data))
            match = re.fullmatch(r'/api/investigations/([A-Za-z0-9-]+)/(analyze|decision|note|outcome)', path)
            if match:
                item = get_record(match[1], 'investigation')
                if not item:
                    return self.respond(404, {'error': 'Investigation not found.'})
                return self.respond(200, update_investigation(item, match[2], data))
            return self.respond(404, {'error': 'Not found.'})
        except (ValueError, TypeError, AttributeError) as exc:
            return self.respond(400, {'error': str(exc) if isinstance(exc, ValueError) else 'Invalid request fields.'})
        except sqlite3.Error:
            return self.respond(503, {'error': 'Storage is temporarily unavailable. Please retry.'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the local Solution Intelligence Engine prototype.')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    initialize()
    service = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Solution Intelligence Engine: http://127.0.0.1:{args.port}', flush=True)
    print('Local demo identity; synthetic evidence; no external AI or connectors.', flush=True)
    try:
        service.serve_forever()
    except KeyboardInterrupt:
        service.server_close()
