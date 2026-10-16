"""Import client ITIL CSV data; back up and replace the previous seed dataset."""
import argparse
import csv
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ai import AIService, AIError
from config import settings
from ingestion import chunks, now
from storage import MongoStore

DATASET = 'client-itil-v1'
STAGES = [('clarification', 'Clarification'), ('investigation_notes', 'Investigation'),
    ('functional_solutioning', 'Functional solutioning'), ('technical_solutioning', 'Technical solutioning'),
    ('change_stages', 'Change stages'), ('verification', 'Verification')]
REQUIRED = ('ticket_id', 'ticket_type', 'customer', 'platform', 'release', 'module',
    'component', 'title', 'problem_statement', 'resolution_quality', 'status', 'priority',
    'created', 'closed', 'resolution', 'lifecycle_path') + tuple(k for k, _ in STAGES)


def date_value(value):
    # Source dates use month/day/year, unambiguously shown by 4/13/2025.
    return datetime.strptime(value.strip(), '%m/%d/%Y').replace(tzinfo=timezone.utc).isoformat() if value.strip() else None


def load_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if set(REQUIRED) - set(reader.fieldnames or []):
            raise ValueError('CSV is missing required ITIL columns.')
        rows = list(reader)
    if not rows or len(rows) > 1000:
        raise ValueError('Import must contain 1–1000 tickets.')
    ids = set()
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError('Malformed CSV row.')
        identity = row['ticket_id']
        if not identity or identity in ids or len(identity) > 100:
            raise ValueError('Ticket IDs must be unique, non-empty and at most 100 characters.')
        ids.add(identity)
        if row['ticket_type'].casefold() not in ('incident', 'service request', 'change request', 'problem'):
            raise ValueError('Unsupported ticket type.')
        if row['priority'] not in ('Low', 'Medium', 'High', 'Critical'):
            raise ValueError('Unsupported priority.')
        date_value(row['created'])
        date_value(row['closed'])
        if row.get('resolution_hours'):
            float(row['resolution_hours'])
    return rows


def build_records(row, filename):
    created, closed = date_value(row['created']) or now(), date_value(row['closed'])
    quality = row['resolution_quality']
    status = ('Workaround' if quality == 'Workaround only' else
        'Closed - other' if quality == 'Unverified' else 'Resolved') if row['status'] == 'Closed' else 'New'
    kind = {'incident': 'Incident', 'service request': 'Service request',
        'change request': 'Change request', 'problem': 'Problem'}[row['ticket_type'].casefold()]
    keys = ('platform', 'module', 'component', 'scenario_group', 'visibility',
        'clarification', 'investigation_notes', 'functional_solutioning', 'technical_solutioning',
        'change_stages', 'verification', 'lifecycle_path', 'resolution_quality', 'root_cause',
        'sources', 'linked_ticket_ids')
    metadata = {key: row.get(key, '') for key in keys}
    metadata.update(customized=row.get('customized', '').casefold() == 'true',
        resolution_hours=float(row['resolution_hours']) if row.get('resolution_hours') else None,
        original_status=row['status'], source_dates=dict(created=row['created'], closed=row['closed']))
    provenance = dict(dataset=DATASET, filename=filename, imported_at=now(), original=dict(row))
    timeline = [dict(at=created, kind='Intake', text=row['problem_statement'],
        author='Imported ticket', source=row['ticket_id'])]
    timeline += [dict(at=created, kind=label, text=row[key], author='Imported ticket',
        source=row['ticket_id'], date_known=False) for key, label in STAGES if row[key].strip()]
    if closed:
        timeline.append(dict(at=closed, kind='Closure', text=row['resolution'] or quality,
            author='Imported ticket', source=row['ticket_id']))
    investigation = dict(id='INV-' + row['ticket_id'], ticket_id=row['ticket_id'], title=row['title'],
        description=row['problem_statement'], application=row['module'] + ' (' + row['platform'] + ')',
        version=row['release'], error_code=row.get('error_message', ''),
        customisation=row['component'] if metadata['customized'] else '', type=kind,
        priority=row['priority'], customer=row['customer'], status=status, created_at=created,
        updated_at=closed or created, timeline=timeline, analysis=None, decisions={},
        selected_source=None, outcome=None, revision=1, itil=metadata, import_info=provenance)
    if closed:
        investigation['outcome'] = dict(status=status, notes=row['resolution'],
            alternative_solution=row['resolution'], recorded_at=closed, selected_source=None,
            usefulness='Not rated', tested=bool(row['verification'].strip()), customer_confirmed=False,
            approved=False, developed=False, deployed=False, verified=False,
            imported=True, verification_notes=row['verification'], resolution_quality=quality)
    content = '\n'.join(f'{key.replace("_", " ").title()}: {value}'
        for key, value in row.items() if value.strip())
    source = dict(id=row['ticket_id'], title=row['title'], content=content,
        application=investigation['application'], version=row['release'], error_code=row.get('error_message', ''),
        customer='General' if row.get('visibility') == 'shared_generalized' else row['customer'],
        source_type='Historical ticket', filename=filename, source_reference=row['ticket_id'],
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        validation='Unverified' if quality == 'Unverified' else 'Reviewed', validation_evidence={},
        solution_kind='Workaround' if quality == 'Workaround only' else 'Likely solution',
        solution=row['resolution'], steps=[row['resolution']] if row['resolution'] else [],
        conflicts_with=[], created_at=created, updated_at=closed or created,
        index_status='Pending', index_error='', chunks=[], chunk_count=0, embedding_model='',
        revision=1, itil=metadata, import_info=provenance,
        review_notes='Imported quality: ' + quality + '. Original verification: ' + row['verification'])
    return investigation, source


def legacy_query(kind):
    # Match only the previous seed namespace, never the new SYN-D client IDs.
    pattern = r'^SYN-(H\d{3}|Q\d{2})$'
    if kind == 'sources':
        return {'id': {'$regex': pattern}}
    return {'$or': [{'id': {'$regex': r'^INV-SYN-(H\d{3}|Q\d{2})$'}},
        {'ticket_id': {'$regex': pattern}}]}


def replace_records(store, records, backup_dir):
    from bson import json_util
    snapshots = {name: list(store.db[name].find({'$or': [legacy_query(name),
        {'import_info.dataset': DATASET}]})) for name in ('sources', 'investigations')}
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / ('before-itil-import-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.json')
    backup.write_text(json_util.dumps(snapshots), encoding='utf-8')
    for investigation, source in records:
        for name, document in [('investigations', investigation), ('sources', source)]:
            existing = store.db[name].find_one({'id': document['id']})
            if existing and existing.get('import_info', {}).get('dataset') != DATASET:
                raise ValueError('Import ID collides with an unrelated record: ' + document['id'])
    for investigation, source in records:
        store.db.investigations.replace_one({'id': investigation['id']}, investigation, upsert=True)
        store.db.sources.replace_one({'id': source['id']}, source, upsert=True)
    for investigation, source in records:
        assert store.db.investigations.count_documents({'id': investigation['id']}) == 1
        assert store.db.sources.count_documents({'id': source['id']}) == 1
    for name in ('sources', 'investigations'):
        store.db[name].delete_many(legacy_query(name))
    return backup, {key: len(value) for key, value in snapshots.items()}


def index_pending(store, ai):
    sources = list(store.db.sources.find({'import_info.dataset': DATASET, 'index_status': {'$ne': 'Ready'}}))
    pending = []
    for source in sources:
        source['chunks'] = chunks(source['content'])
        pending.extend((source, chunk) for chunk in source['chunks'])
    for start in range(0, len(pending), 16):
        quota = ai.quota_status(needed=1)
        if not quota['daily_remaining']:
            break
        if not quota['minute_remaining']:
            time.sleep(quota['retry_after_seconds'] + 1)
        batch = pending[start:start + 16]
        try:
            vectors = ai.embed([source['title'] + '\n' + chunk['text'] for source, chunk in batch])
        except AIError as exc:
            print('Indexing paused:', exc, flush=True)
            break
        for (_, chunk), vector in zip(batch, vectors):
            chunk['embedding'] = vector
        for source in sources:
            if source['chunks'] and all('embedding' in c for c in source['chunks']):
                store.db.sources.update_one({'id': source['id']}, {'$set': dict(chunks=source['chunks'],
                    chunk_count=len(source['chunks']), index_status='Ready', index_error='',
                    embedding_model=ai.config.embedding_model, indexed_at=now())})
        print(f'Embedded {min(start + 16, len(pending))}/{len(pending)} chunks', flush=True)
    return store.db.sources.count_documents({'import_info.dataset': DATASET, 'index_status': 'Ready'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--index', action='store_true')
    parser.add_argument('--index-only', action='store_true')
    args = parser.parse_args()
    rows = load_rows(args.csv)
    records = [build_records(row, args.csv.name) for row in rows]
    count = sum(len(chunks(s['content'])) for _, s in records)
    print(json.dumps(dict(tickets=len(records), knowledge_sources=len(records), chunks=count,
        embedding_requests=(count+15)//16), indent=2), flush=True)
    if not (args.apply or args.index_only):
        return
    store = MongoStore(settings)
    try:
        store.initialize()
        if args.apply:
            backup, previous = replace_records(store, records, ROOT / 'data' / 'backups')
            print('Backup:', backup, 'Previous records:', previous, flush=True)
        if args.index or args.index_only:
            print('Indexed sources:', index_pending(store, AIService(settings)), flush=True)
    finally:
        store.close()


if __name__ == '__main__':
    main()
