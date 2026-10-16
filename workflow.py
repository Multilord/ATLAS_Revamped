"""Consultant-authored lifecycle evidence. These operations never call AI."""
import uuid
from storage import ConflictError

SAP_FIELDS = ('plant', 'transaction', 'program_include', 'enhancement', 'configuration_path', 'affected_process')
BASE_STAGES = ('Acceptance', 'Acknowledgment', 'Clarification', 'Solutioning')


def stages(ticket):
    return BASE_STAGES + (('Approval', 'Development', 'Deployment', 'Verification') if ticket['type'] == 'Change request' else ())


def text(data, key, required=False, limit=12000):
    value = data.get(key, '')
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError('Invalid or missing ' + key.replace('_', ' '))
    return value.strip()


def update_workspace(ticket, data, store, stamp, author):
    if data.get('revision') != ticket.get('revision', 0):
        raise ConflictError('This ticket changed. Reload before saving your edits.')
    kind = data.get('kind')
    record = dict(updated_at=stamp, author=author)
    if kind == 'context':
        ticket.setdefault('itil', {}).update({k: text(data, k, limit=500) for k in SAP_FIELDS})
        return 'SAP applicability updated.'
    if kind == 'stage':
        name = text(data, 'name', True, 100)
        if name not in stages(ticket) or data.get('status') not in ('Not started', 'In progress', 'Blocked', 'Completed'):
            raise ValueError('Invalid lifecycle stage or status.')
        record.update(name=name, status=data['status'], owner=text(data, 'owner', True, 200), evidence=text(data, 'evidence', data['status'] == 'Completed'))
        ticket.setdefault('workflow', {}).setdefault('stages', {})[name] = record
        return name + ': ' + record['status'] + '.'
    if kind == 'requirement':
        if data.get('status') not in ('Needs confirmation', 'Confirmed', 'Rejected'):
            raise ValueError('Invalid requirement status.')
        record.update(title=text(data, 'title', True, 300), detail=text(data, 'detail'), status=data['status'], evidence=text(data, 'evidence', data['status'] != 'Needs confirmation'))
    elif kind == 'scenario':
        if data.get('status') not in ('Not run', 'Passed', 'Failed', 'Blocked'):
            raise ValueError('Invalid test status.')
        executed = data['status'] in ('Passed', 'Failed')
        record.update(title=text(data, 'title', True, 300), expected=text(data, 'expected', True), actual=text(data, 'actual', executed), environment=text(data, 'environment', executed, 200), tester=text(data, 'tester', executed, 200), evidence=text(data, 'evidence', executed), status=data['status'])
    elif kind == 'proposal':
        if data.get('category') not in ('Functional', 'Technical'):
            raise ValueError('Invalid proposal category.')
        record.update(category=data['category'], title=text(data, 'title', True, 300), detail=text(data, 'detail', True), limitations=text(data, 'limitations'))
        citations = data.get('citations', [])
        if not isinstance(citations, list) or len(citations) > 5:
            raise ValueError('Use at most five citations.')
        record['citations'] = []
        for citation in citations:
            if not isinstance(citation, dict):
                raise ValueError('Invalid citation.')
            source_id = text(citation, 'source_id', True, 100)
            source = store.get(source_id, 'source', include_chunks=True)
            quote = text(citation, 'quote', True, 3000)
            if not source or source['customer'] not in (ticket['customer'], 'General'):
                raise ValueError('Citation source is outside this customer scope.')
            if ' '.join(quote.split()).casefold() not in ' '.join(source['content'].split()).casefold():
                raise ValueError('Citation quotation must match the original source.')
            record['citations'].append(dict(source_id=source_id, quote=quote, content_hash=source.get('content_hash', ''), section=text(citation, 'section', limit=300)))
    elif kind == 'evaluation':
        record.update(title=text(data, 'title', True, 300), reviewer=text(data, 'reviewer', True, 200), evidence=text(data, 'evidence', True))
        for key in ('summary_complete', 'claims_supported', 'scenarios_covered'):
            if data.get(key) not in ('Yes', 'No', 'Not assessed'):
                raise ValueError('Invalid evaluation rating.')
            record[key] = data[key]
        record['ticket_revision'] = ticket.get('revision', 0)
    else:
        raise ValueError('Invalid workspace record type.')
    rows = ticket.setdefault('workflow', {}).setdefault(kind + 's', [])
    requested = text(data, 'id', limit=100)
    old = next((r for r in rows if r['id'] == requested), None)
    if requested and old is None:
        raise ValueError('Workspace record not found.')
    if old:
        rows.remove(old)
    elif len(rows) >= 100:
        raise ValueError('At most 100 records of each type are allowed.')
    record['id'] = requested or uuid.uuid4().hex
    rows.append(record)
    return kind.capitalize() + ' saved: ' + record['title']


def validate_closure(ticket):
    """Do not infer historical stages; validate structured evidence when supplied."""
    work = ticket.get('workflow', {})
    if any(r['status'] == 'Needs confirmation' for r in work.get('requirements', [])):
        raise ValueError('Confirm or reject outstanding requirements before resolving.')
    tests = work.get('scenarios', [])
    if tests and any(r['status'] != 'Passed' for r in tests):
        raise ValueError('All recorded verification scenarios must pass before resolving.')
    if ticket['type'] == 'Change request' and work.get('stages'):
        if any(work['stages'].get(s, {}).get('status') != 'Completed' for s in stages(ticket)):
            raise ValueError('Complete every recorded change lifecycle stage before resolving.')
