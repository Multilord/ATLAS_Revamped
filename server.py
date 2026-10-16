"""Local application server with MongoDB persistence and real Gemini integration."""
import argparse
import json
import os
import re
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from pymongo.errors import PyMongoError
from config import settings
from storage import MongoStore, ConflictError
from ai import AIService, AIError
from engine import retrieve
from ingestion import create_source, index_source, extract_upload

ROOT = Path(__file__).resolve().parent
CUSTOMER = settings.customer
store = MongoStore(settings)
ai = AIService(settings)
TYPES = ('Incident', 'Service request', 'Problem', 'Change request')
OUTCOMES = ('Worked', 'Partially worked', 'Did not work', 'Alternative solution used', 'Unresolved', 'Escalated', 'Resolved', 'Workaround', 'Closed - other')
TIMELINE_KINDS = ('Communication', 'Investigation', 'Note', 'Test', 'Attachment', 'Clarification', 'Acknowledgement', 'Resolution', 'Approval', 'Development', 'Deployment', 'Verification', 'Ticket Creation', 'Ticket Acceptance', 'Solutioning', 'Closure')
CONSULTANT_NOTE_KINDS = ('Communication', 'Investigation', 'Note', 'Test', 'Attachment', 'Clarification', 'Acknowledgement')
STANDARD_LIFECYCLE = ('Ticket Creation', 'Ticket Acceptance', 'Acknowledgment', 'Clarification', 'Solutioning', 'Closure')
CHANGE_LIFECYCLE = ('Ticket Creation', 'Ticket Acceptance', 'Acknowledgment', 'Clarification', 'Solutioning', 'Approval', 'Development', 'Deployment', 'Verification', 'Closure')
SOLUTIONING_FIELDS = {
    'functional': ('expected_behaviour', 'business_requirements', 'functional_analysis', 'business_rules', 'scenarios', 'clarification_questions', 'proposed_solution', 'assumptions', 'limitations', 'unresolved_questions'),
    'technical': ('investigation_findings', 'systems_components', 'dependencies', 'implementation_approach', 'potential_changes', 'testing_requirements', 'risks', 'rollback_considerations', 'unresolved_questions'),
}
MAX_SOLUTIONING_FIELD = 12000


def now():
    return datetime.now(timezone.utc).isoformat()


def initialize():
    store.initialize()


def records(kind):
    return store.records(kind)


def get_record(id, kind):
    return store.get(id, kind)


def save(item, action):
    # The timeline and state are persisted together in one atomic document update.
    store.save(item)


def health():
    try:
        store.ping()
        database = 'Connected'
    except PyMongoError:
        database = 'Unavailable'
    return dict(database=database, ai='Configured (not yet checked)' if ai.configured else 'API key missing',
        model=settings.model, embedding_model=settings.embedding_model, customer=CUSTOMER,
        quota=ai.quota_status())


def workspace_insights(investigations):
    """Build transparent exact-error/title clusters; this is not an AI diagnosis."""
    rows = list(investigations)
    parent = list(range(len(rows)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left, right):
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    signatures = []
    for row in rows:
        title_tokens = set(re.findall(r'[a-z0-9]{3,}', (row.get('title', '') + ' ' + row.get('description', '')).casefold()))
        error = re.sub(r'\W', '', row.get('error_code', '')).casefold()
        signatures.append((row, title_tokens, error, ' '.join(row.get('application', '').casefold().split()), ' '.join(row.get('module', '').casefold().split()), row.get('customer', '')))
    for left in range(len(signatures)):
        a, a_tokens, a_error, a_app, a_module, a_customer = signatures[left]
        for right in range(left + 1, len(signatures)):
            b, b_tokens, b_error, b_app, b_module, b_customer = signatures[right]
            if not a_app or a_app != b_app or a_customer != b_customer or (a_module and b_module and a_module != b_module):
                continue
            same_error = bool(a_error and b_error and a_error == b_error)
            similarity = len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens))
            if same_error or similarity >= .42:
                union(left, right)
    buckets = {}
    for index, row in enumerate(rows):
        buckets.setdefault(find(index), []).append(row)
    clusters = []
    for members in buckets.values():
        if len(members) < 2:
            continue
        errors = [re.sub(r'\W', '', item.get('error_code', '')).casefold() for item in members]
        key = next((value for value in errors if value), '') or re.sub(r'\W', '-', members[0].get('title', '').casefold()).strip('-')[:60]
        unresolved = [item for item in members if item.get('status') in ('Unresolved', 'Escalated') or (item.get('analysis') or {}).get('state') == 'Insufficient evidence']
        clusters.append(dict(id='CL-' + key, title=members[0].get('title', 'Related tickets'), application=members[0].get('application', ''),
            ticket_ids=[item.get('ticket_id') or item['id'] for item in members], count=len(members),
            releases=sorted({item.get('version', '') for item in members if item.get('version')}),
            unresolved_count=len(unresolved), knowledge_gap=bool(unresolved)))
    clusters.sort(key=lambda item: (item['knowledge_gap'], item['count']), reverse=True)
    gaps = [{'id': item['id'], 'title': item.get('title', ''), 'reason': item.get('status', ''), 'ticket_id': item.get('ticket_id', item['id'])}
        for item in rows if item.get('status') in ('Unresolved', 'Escalated') or (item.get('analysis') or {}).get('state') == 'Insufficient evidence']
    for cluster in clusters:
        if cluster['knowledge_gap']:
            gaps.append(dict(id=cluster['id'], title=f"Recurring issue: {cluster['title']}", reason=f"{cluster['unresolved_count']} unresolved/low-evidence case(s) in a {cluster['count']}-ticket cluster", ticket_id=cluster['ticket_ids'][0]))
    return dict(ticket_clusters=clusters, knowledge_gaps=gaps)


def required_text(data, key, limit=12000):
    value = data.get(key, '')
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{key.replace("_", " ").capitalize()} is required and must be under {limit} characters.')
    return value.strip()


def parse_intake(data, use_ai=False):
    raw = required_text(data, 'content', 100000)
    filename = data.get('filename', '')
    if not isinstance(filename, str) or len(filename) > 255:
        raise ValueError('Invalid filename.')
    if filename and Path(filename).suffix.lower() not in ('.txt', '.md', '.json', '.pdf', '.docx', '.pptx', '.html', '.htm', '.xlsx', '.xlsm', '.xltx', '.csv'):
        raise ValueError('Unsupported ticket file format.')
    obj = {}
    if filename.lower().endswith('.json') or raw.lstrip().startswith('{'):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError('Invalid JSON. Check the ticket export and try again.')
        if not isinstance(obj, dict):
            raise ValueError('Ticket JSON must be an object.')
        for key in ('title', 'description', 'application', 'platform', 'module', 'business_process', 'version', 'ticket_id', 'error_code', 'customisation', 'type', 'priority'):
            if key in obj and not isinstance(obj[key], str):
                raise ValueError(f'{key} must be text.')
        if obj.get('customer', CUSTOMER) != CUSTOMER and CUSTOMER not in ('My Workspace', 'All'):
            raise ValueError('This installation is scoped to ' + CUSTOMER + '.')
    elif use_ai:
        if len(raw) > 60000:
            raise ValueError('Ticket text exceeds 60,000 characters. Split attachments into knowledge documents.')
        obj = ai.extract(raw)
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
        kind = event.get('kind', 'Communication')
        if kind not in TIMELINE_KINDS:
            raise ValueError('Timeline event kind is not supported.')
        author = event.get('author', 'Imported')
        source = event.get('source', filename or 'Pasted export')
        if not isinstance(author, str) or not isinstance(source, str):
            raise ValueError('Timeline author and source must be text.')
        cleaned.append(dict(at=stamp, text=required_text(event, 'text'), kind=kind, author=author[:120], source=source[:255]))
    cleaned.sort(key=lambda event: event['at'])
    description = obj.get('description', raw)
    if len(description) > 12000:
        raise ValueError('Description exceeds 12,000 characters. Split communications into a JSON timeline.')
    error = re.search(r'\b(?:[A-Z][0-9]\s?\d{3}|Z[A-Z]+_\d+|AUTH_\d+|HTTP\s\d+)\b', description)
    return dict(title=obj.get('title', next((line for line in raw.splitlines() if line.strip()), '')[:120]), description=description[:12000], ticket_id=obj.get('ticket_id', ''), application=obj.get('application', 'SAP Finance' if re.search('invoice|vendor|payment', description, re.I) else 'SAP Procurement' if re.search('purchase|approval', description, re.I) else ''), platform=obj.get('platform', ''), module=obj.get('module', ''), business_process=obj.get('business_process', ''), version=obj.get('version', ''), error_code=obj.get('error_code', error.group() if error else ''), customisation=obj.get('customisation', ''), type=obj.get('type', 'Incident'), priority=obj.get('priority', 'Medium'), customer=CUSTOMER, timeline=cleaned, filename=filename)


def create_investigation(data):
    target_customer = data.get('customer', CUSTOMER)
    if target_customer != CUSTOMER and CUSTOMER not in ('My Workspace', 'All'):
        raise ValueError('Customer scope is not authorised.')
    item = {key: required_text(data, key, size) for key, size in [('title', 200), ('description', 12000)]}
    for key, size in (('application', 100), ('version', 100), ('platform', 150), ('module', 100), ('business_process', 200)):
        value = data.get(key, '')
        if not isinstance(value, str) or len(value) > size:
            raise ValueError('Invalid ' + key)
        item[key] = value.strip()
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
    functional = {'customer_problem': item['description']}
    item.update(id='INV-' + uuid.uuid4().hex[:12].upper(), customer=target_customer, type=data['type'], priority=data['priority'], status='New', lifecycle_stage='Ticket Creation', lifecycle_history=[dict(stage='Ticket Creation', at=stamp, author=settings.consultant, notes='Ticket created and intake context recorded.')], lifecycle_history_tracked=True, solutioning={'functional': functional, 'technical': {}}, solutioning_history=[], created_at=stamp, updated_at=stamp, timeline=timeline, analysis=None, decisions={}, selected_source=None, outcome=None, revision=0)
    item['timeline'].append(dict(at=stamp, kind='Intake', text='Ticket context reviewed and investigation created.', author=settings.consultant, source=item['ticket_id'] or 'Manual intake'))
    save(item, 'created')
    return item


def lifecycle_stages(ticket_type):
    return CHANGE_LIFECYCLE if ticket_type == 'Change request' else STANDARD_LIFECYCLE


def lifecycle_view(item):
    """Return lifecycle progress strictly from persisted transitions, not page views."""
    stages = lifecycle_stages(item.get('type', 'Incident'))
    tracked = item.get('lifecycle_history_tracked', bool(item.get('lifecycle_history')))
    legacy_terminal = not tracked and item.get('status') in ('Resolved', 'Workaround', 'Unresolved', 'Escalated', 'Closed - other', 'Closed')
    current = item.get('lifecycle_stage') if tracked else ('Ticket Creation' if not legacy_terminal else None)
    history = item.get('lifecycle_history', []) if tracked else []
    completed = {event.get('stage') for event in history}
    return dict(stages=[dict(name=name, state='completed' if name in completed and name != current else 'current' if name == current else 'upcoming') for name in stages],
        current_stage=current or 'Lifecycle not tracked for this imported record', history=history,
        history_tracked=tracked, next_stage=(stages[stages.index(current)+1] if current in stages and stages.index(current)+1 < len(stages) and not legacy_terminal else None))


def _event(item, kind, text, source='Investigation workspace', stamp=None):
    at = stamp or now()
    item.setdefault('timeline', []).append(dict(at=at, kind=kind, text=text, author=settings.consultant, source=source))
    return at


def update_solutioning(item, data):
    section = data.get('section')
    if section not in SOLUTIONING_FIELDS:
        raise ValueError('Solutioning section must be Functional or Technical.')
    if item.get('lifecycle_stage') == 'Closure' or item.get('status') == 'Closed':
        raise ValueError('A closed ticket cannot be edited.')
    updates = data.get('fields')
    if not isinstance(updates, dict) or not updates:
        raise ValueError('Provide at least one solutioning field to save.')
    allowed = set(SOLUTIONING_FIELDS[section])
    if section == 'functional':
        allowed.add('customer_problem')
        if 'customer_problem' in updates and updates['customer_problem'] != item.get('description'):
            raise ValueError('The original customer problem is immutable; add corrections or clarification to the timeline.')
    if set(updates) - allowed:
        raise ValueError('Unknown solutioning field.')
    cleaned = {}
    for key, value in updates.items():
        if not isinstance(value, str) or len(value) > MAX_SOLUTIONING_FIELD:
            raise ValueError(f'{key.replace("_", " ").capitalize()} must be text under {MAX_SOLUTIONING_FIELD} characters.')
        cleaned[key] = value.strip()
    stamp = now()
    item.setdefault('solutioning', {'functional': {'customer_problem': item.get('description', '')}, 'technical': {}})
    entry = item['solutioning'].setdefault(section, {})
    entry.update(cleaned)
    entry['updated_at'] = stamp
    entry['updated_by'] = settings.consultant
    item.setdefault('solutioning_history', []).append(dict(section=section, fields=sorted(cleaned), at=stamp, author=settings.consultant))
    if item.get('analysis'):
        item['analysis'] = None
        item['decisions'] = {}
        item['selected_source'] = None
    item['updated_at'] = stamp
    label = 'Functional' if section == 'functional' else 'Technical'
    _event(item, 'Investigation', f'{label} solutioning updated: {", ".join(sorted(cleaned))}.', f'{label} solutioning', stamp)
    save(item, 'solutioning')
    return item


def transition_lifecycle(item, data):
    stages = lifecycle_stages(item.get('type', 'Incident'))
    history = item.get('lifecycle_history') or []
    current = item.get('lifecycle_stage') if item.get('lifecycle_history_tracked', bool(history)) else 'Ticket Creation'
    if not item.get('lifecycle_history_tracked') and item.get('status') in ('Resolved', 'Workaround', 'Unresolved', 'Escalated', 'Closed - other', 'Closed'):
        raise ValueError('This imported ticket is already terminal. Historical lifecycle tracking cannot be safely reconstructed.')
    if current not in stages:
        raise ValueError('This imported ticket has an unsupported lifecycle state; review its history before transitioning.')
    if not item.get('lifecycle_history_tracked'):
        created = item.get('created_at') or now()
        item['lifecycle_history'] = [dict(stage='Ticket Creation', at=created, author='Imported record', notes='Lifecycle tracking initialized. Earlier workflow stages were not supplied.')]
    target = data.get('stage')
    notes = required_text(data, 'notes', 4000)
    index = stages.index(current)
    next_stage = stages[index + 1] if index + 1 < len(stages) else None
    exception = data.get('exception_reason', '')
    if target != next_stage:
        allowed_rejected_close = (current == 'Approval' and target == 'Closure' and
            (item.get('approval_decision') or {}).get('status') == 'Rejected' and exception == 'Approval rejected')
        allowed_exception_close = (target == 'Closure' and exception in ('Cancelled', 'Escalated', 'Other') and
            current != 'Ticket Creation')
        if not (allowed_rejected_close or allowed_exception_close):
            raise ValueError('Invalid lifecycle transition. Advance exactly one stage; use an explicit audited closure exception when applicable.')
    if current == 'Closure':
        raise ValueError('This ticket is already closed.')
    if target == 'Solutioning':
        functional = (item.get('solutioning') or {}).get('functional') or {}
        technical = (item.get('solutioning') or {}).get('technical') or {}
        if not item.get('selected_source') and not functional.get('proposed_solution','').strip() and not technical.get('implementation_approach','').strip():
            raise ValueError('Record a proposed solution or select an evidence-backed recommendation before entering Solutioning.')
    if target == 'Approval':
        solutioning = item.get('solutioning') or {}
        if not item.get('selected_source') and not (solutioning.get('functional') or {}).get('proposed_solution','').strip() and not (solutioning.get('technical') or {}).get('implementation_approach','').strip():
            raise ValueError('A proposed solution is required before customer approval.')
        decision = data.get('approval_status', 'Pending')
        if decision not in ('Pending', 'Approved', 'Rejected'):
            raise ValueError('Select Pending, Approved, or Rejected for customer approval.')
        item['approval_decision'] = dict(status=decision, notes=notes, at=now(), author=settings.consultant)
    if current == 'Approval' and target == 'Development' and (item.get('approval_decision') or {}).get('status') != 'Approved':
        raise ValueError('Development cannot start until the change request is approved.')
    if target == 'Verification':
        deployment = next((event for event in reversed(history) if event.get('stage') == 'Deployment'), None)
        if not deployment:
            raise ValueError('Record the deployment stage before verification.')
        item.setdefault('verification_history', []).append(dict(result='Pending', notes='Verification stage entered; no test result recorded yet.', at=now(), author=settings.consultant))
        item['verification'] = item['verification_history'][-1]
    if target == 'Closure':
        outcome = item.get('outcome') or {}
        if not outcome and not exception:
            raise ValueError('Record the consultant outcome before closing the lifecycle.')
        if outcome and outcome.get('status') in ('Did not work', 'Unresolved', 'Escalated', 'Closed - other') and not exception:
            raise ValueError('An unresolved, failed, escalated, or otherwise closed outcome requires an explicit closure exception.')
        if item.get('type') == 'Change request' and not exception:
            verification = item.get('verification') or {}
            if verification.get('result') != 'Passed':
                raise ValueError('A change request cannot close until post-deployment verification has passed.')
        if exception and exception not in ('Cancelled', 'Escalated', 'Approval rejected', 'Other'):
            raise ValueError('Unsupported lifecycle closure exception.')
        if exception:
            item['closure_exception'] = dict(reason=exception, notes=notes, at=now(), author=settings.consultant)
    stamp = now()
    item.setdefault('lifecycle_history', []).append(dict(stage=target, at=stamp, author=settings.consultant, notes=notes))
    item['lifecycle_stage'] = target
    item['lifecycle_history_tracked'] = True
    item['updated_at'] = stamp
    if target == 'Closure':
        item['status'] = 'Closed'
    elif target == 'Ticket Acceptance':
        item['status'] = 'In progress'
    event_kind = target if target in TIMELINE_KINDS else 'Investigation'
    _event(item, event_kind, f'Lifecycle stage: {current} → {target}. {notes}', 'Lifecycle transition', stamp)
    save(item, 'lifecycle')
    return item


def record_approval(item, data):
    if item.get('type') != 'Change request' or item.get('lifecycle_stage') != 'Approval':
        raise ValueError('Approval decisions can only be recorded at the Approval stage of a change request.')
    decision = data.get('status')
    if decision not in ('Pending', 'Approved', 'Rejected'):
        raise ValueError('Select Pending, Approved, or Rejected.')
    notes = required_text(data, 'notes', 4000)
    stamp = now()
    item['approval_decision'] = dict(status=decision, notes=notes, at=stamp, author=settings.consultant)
    item['updated_at'] = stamp
    _event(item, 'Approval', f'Customer approval decision: {decision}. {notes}', 'Change approval', stamp)
    save(item, 'approval')
    return item


def record_verification(item, data):
    if item.get('type') != 'Change request' or item.get('lifecycle_stage') != 'Verification':
        raise ValueError('Verification results can only be recorded at the Verification stage of a change request.')
    result = data.get('result')
    if result not in ('Passed', 'Failed', 'Pending'):
        raise ValueError('Select Passed, Failed, or Pending.')
    notes = required_text(data, 'notes', 4000)
    stamp = now()
    entry = dict(result=result, notes=notes, at=stamp, author=settings.consultant)
    item.setdefault('verification_history', []).append(entry)
    item['verification'] = entry
    item['updated_at'] = stamp
    _event(item, 'Verification', f'Post-deployment verification {result.lower()}. {notes}', 'Verification evidence', stamp)
    save(item, 'verification')
    return item


def update_investigation(item, action, data):
    closed = item.get('lifecycle_stage') == 'Closure' or item.get('status') == 'Closed'
    if closed and action != 'analyze':
        raise ValueError('This ticket is closed. Reopening is not enabled for this workspace.')
    if action == 'analyze':
        item['analysis'] = retrieve(item, store, ai)
        if not item.get('outcome'):
            item['decisions'] = {}
            item['selected_source'] = None
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
        if data.get('kind') not in CONSULTANT_NOTE_KINDS:
            raise ValueError('Invalid note type.')
        message = required_text(data, 'text', 120000 if data.get('kind') == 'Attachment' else 12000)
        event_source = data.get('source_reference', 'Investigation workspace')
        if not isinstance(event_source, str) or len(event_source) > 1000:
            raise ValueError('Invalid evidence source reference.')
        if item.get('analysis') and not item.get('outcome'):
            item['analysis'] = None
            item['decisions'] = {}
            item['selected_source'] = None
            item['status'] = 'In progress'
    elif action == 'outcome':
        status = data.get('status')
        if status not in OUTCOMES:
            raise ValueError('Select a valid outcome.')
        notes = required_text(data, 'notes')
        flags = ('tested', 'customer_confirmed', 'approved', 'developed', 'deployed', 'verified')
        if any(k in data and not isinstance(data[k], bool) for k in flags):
            raise ValueError('Validation fields must be true or false.')
        if status in ('Worked', 'Resolved') and not (data.get('tested') and data.get('customer_confirmed')):
            raise ValueError('A worked/resolved outcome requires recorded testing and customer confirmation.')
        if status in ('Worked', 'Resolved') and item['type'] == 'Change request' and not all(data.get(k) for k in ('approved', 'developed', 'deployed', 'verified')):
            raise ValueError('A resolved change requires approval, development, deployment and verification.')
        alternative = data.get('alternative_solution', '')
        if not isinstance(alternative, str) or len(alternative) > 12000:
            raise ValueError('Alternative solution must be text under 12,000 characters.')
        if status in ('Worked', 'Resolved', 'Workaround') and not item.get('selected_source') and not alternative.strip():
            raise ValueError('Select a recommendation or document the solution used.')
        if status == 'Alternative solution used' and not alternative.strip():
            raise ValueError('Describe the alternative solution that was used.')
        if data.get('usefulness', 'Not rated') not in ('Useful', 'Partly useful', 'Not useful', 'Not rated'):
            raise ValueError('Invalid feedback.')
        if item.get('outcome'):
            item.setdefault('outcome_history', []).append(dict(item['outcome']))
        item['outcome'] = dict(status=status, notes=notes, recorded_at=now(), selected_source=item.get('selected_source'), alternative_solution=alternative.strip(), usefulness=data.get('usefulness', 'Not rated'), **{k: bool(data.get(k)) for k in flags})
        message = 'Consultant recorded outcome: ' + status + '. ' + notes
    else:
        raise ValueError('Unknown action.')
    item['updated_at'] = now()
    event_source = data.get('source_reference', 'Investigation workspace') if action == 'note' else 'Investigation workspace'
    item['timeline'].append(dict(at=item['updated_at'], kind=data.get('kind', 'Note') if action == 'note' else action.capitalize(), text=message, author=settings.consultant, source=event_source))
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
        try:
            self.get()
        except PyMongoError:
            self.respond(503, {'error': 'MongoDB is unavailable. Start MongoDB or check MONGODB_URI in .env, then restart the server.'})

    def get(self):
        if not self.trusted_host():
            return self.respond(403, {'error': 'Untrusted host.'})
        path = urlsplit(self.path).path
        if path == '/api/state':
            investigations = records('investigation')
            investigations = [{**item, 'lifecycle': lifecycle_view(item)} for item in investigations]
            return self.respond(200, dict(customer=CUSTOMER, user=settings.consultant, mode='MongoDB workspace', investigations=investigations, sources=records('source'), insights=workspace_insights(investigations), services=health()))
        if path == '/api/health':
            status = health()
            return self.respond(200 if status['database'] == 'Connected' else 503, status)
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
            if not 0 < length <= 8 * 1024 * 1024:
                return self.respond(413, {'error': 'Request must be under 8 MB.'})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object.')
            path = urlsplit(self.path).path
            if path == '/api/ai/check':
                return self.respond(200, ai.check())
            if path == '/api/extract':
                return self.respond(200, extract_upload(data))
            if path == '/api/intake':
                return self.respond(200, parse_intake(data, use_ai=True))
            if path == '/api/sources':
                return self.respond(201, create_source(data, store, ai))
            source_match = re.fullmatch(r'/api/sources/([A-Za-z0-9-]+)/(reindex|review)', path)
            if source_match:
                source = store.get(source_match[1], 'source', include_chunks=True)
                if not source:
                    return self.respond(404, {'error': 'Source not found.'})
                if source_match[2] == 'reindex':
                    return self.respond(200, index_source(source, store, ai))
                validation = data.get('validation')
                if validation not in ('Reviewed', 'Verified', 'Outdated'):
                    raise ValueError('Select a valid validation state.')
                review_notes = required_text(data, 'notes')
                checks = {key: data.get(key, False) for key in ('tested', 'customer_confirmed', 'deployed')}
                if any(not isinstance(v, bool) for v in checks.values()):
                    raise ValueError('Validation fields must be true or false.')
                if validation == 'Verified' and not all(checks.values()):
                    raise ValueError('Verified sources require testing, customer confirmation and deployment evidence.')
                conflict_text = data.get('conflicts_with', '')
                if not isinstance(conflict_text, str) or len(conflict_text) > 2100:
                    raise ValueError('Conflicting source IDs must be comma-separated text under 2,100 characters.')
                conflicts = [value.strip() for value in conflict_text.split(',') if value.strip()]
                if len(conflicts) > 20 or any(len(value) > 100 for value in conflicts):
                    raise ValueError('Provide at most 20 conflict source IDs, each under 100 characters.')
                if any(value != source['id'] and not store.get(value, 'source') for value in conflicts):
                    raise ValueError('Each conflicting source must exist in this customer workspace or be General knowledge.')
                source.update(validation=validation, validation_evidence=checks, review_notes=review_notes,
                    conflicts_with=list(dict.fromkeys(conflicts)), reviewed_at=now(), reviewed_by=settings.consultant)
                if validation == 'Verified' and source.get('solution_kind') != 'Workaround':
                    source['solution_kind'] = 'Verified fix'
                elif validation != 'Verified' and source.get('solution_kind') == 'Verified fix':
                    source['solution_kind'] = 'Likely solution'
                store.save(source, 'source')
                return self.respond(200, {k: v for k, v in source.items() if k != 'chunks'})
            if path == '/api/investigations':
                return self.respond(201, create_investigation(data))
            match = re.fullmatch(r'/api/investigations/([A-Za-z0-9-]+)/(analyze|decision|note|outcome|lifecycle|solutioning|approval|verification)', path)
            if match:
                item = get_record(match[1], 'investigation')
                if not item:
                    return self.respond(404, {'error': 'Investigation not found.'})
                if item.get('customer') != CUSTOMER:
                    return self.respond(404, {'error': 'Investigation not found.'})
                if match[2] == 'lifecycle':
                    return self.respond(200, transition_lifecycle(item, data))
                if match[2] == 'solutioning':
                    return self.respond(200, update_solutioning(item, data))
                if match[2] == 'approval':
                    return self.respond(200, record_approval(item, data))
                if match[2] == 'verification':
                    return self.respond(200, record_verification(item, data))
                return self.respond(200, update_investigation(item, match[2], data))
            return self.respond(404, {'error': 'Not found.'})
        except (ValueError, TypeError, AttributeError) as exc:
            return self.respond(400, {'error': str(exc) if isinstance(exc, ValueError) else 'Invalid request fields.'})
        except ConflictError as exc:
            return self.respond(409, {'error': str(exc)})
        except AIError as exc:
            return self.respond(502, {'error': str(exc)})
        except PyMongoError:
            return self.respond(503, {'error': 'MongoDB is unavailable. Check MONGODB_URI and your database connection.'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the MongoDB-backed Solution Intelligence Engine.')
    parser.add_argument('--port', type=int, default=settings.port)
    args = parser.parse_args()
    try:
        initialize()
    except PyMongoError:
        print('MongoDB unavailable. The setup screen will show connection guidance.', flush=True)
    service = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Solution Intelligence Engine: http://127.0.0.1:{args.port}', flush=True)
    print('MongoDB storage. Gemini: ' + ('key configured' if ai.configured else 'set GEMINI_API_KEY in .env'), flush=True)
    try:
        service.serve_forever()
    except KeyboardInterrupt:
        service.server_close()
