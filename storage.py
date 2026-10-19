"""MongoDB is the only application datastore. No seeds or fallback database."""
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError
import security


class ConflictError(Exception):
    pass


class MongoStore:
    def __init__(self, config, client=None):
        self.customer = config.customer
        self.client = client if client is not None else MongoClient(config.mongo_uri,
            serverSelectionTimeoutMS=config.mongo_timeout, connectTimeoutMS=config.mongo_timeout,
            socketTimeoutMS=15000, tz_aware=True, appname='ATLAS-Solution-Intelligence', connect=False)
        self.db = self.client[config.database]

    def initialize(self):
        self.client.admin.command('ping')
        for name in ('investigations', 'sources'):
            self.db[name].create_index([('id', ASCENDING)], unique=True)
            self.db[name].create_index([('customer', ASCENDING), ('updated_at', ASCENDING)])
        self.db.sources.create_index([('customer', ASCENDING), ('content_hash', ASCENDING)], unique=True)

    def ping(self):
        self.client.admin.command('ping')

    def scope(self, kind):
        user = security.principal.get()
        if user:
            own = {'customer': {'$in': user['customers']}}
            shared = {'customer': 'General', 'generalization_confirmed': True, 'security.status': 'Approved', 'security.classification': 'Internal'}
            if 'Reviewer' in user['roles']:
                shared = {'customer': 'General', 'generalization_confirmed': True}
            return {'$or': [own, shared]} if kind == 'source' else own
        if self.customer in ('My Workspace', 'All'):
            return {}
        return {'$or': [{'customer': self.customer}, {'customer': 'General', 'generalization_confirmed': True}]} if kind == 'source' else {'customer': self.customer}

    def collection(self, kind):
        if kind not in ('source', 'investigation'):
            raise ValueError('Unknown record type.')
        return self.db.sources if kind == 'source' else self.db.investigations

    def records(self, kind, include_chunks=False):
        projection = {'_id': 0}
        if kind == 'source' and not include_chunks:
            projection['chunks'] = 0
        return list(self.collection(kind).find(self.scope(kind), projection).sort('updated_at', -1))

    def get(self, id, kind, include_chunks=False):
        projection = {'_id': 0}
        if kind == 'source' and not include_chunks:
            projection['chunks'] = 0
        return self.collection(kind).find_one({**self.scope(kind), 'id': id}, projection)

    def save(self, item, kind='investigation'):
        cust = item.get('customer')
        user = security.principal.get()
        if user:
            if not security.customer_allowed(cust) and not (cust == 'General' and 'Reviewer' in user['roles'] and item.get('generalization_confirmed') is True):
                raise security.SecurityError('Customer scope is not permitted for this write.')
            old = self.get(item['id'], kind, include_chunks=True)
            if old is None:
                item['created_by_id'] = user['id']
                item['content_editor_id'] = user['id']
                item['security'] = dict(status='Pending review', classification='Restricted', external_ai=False)
                if kind == 'source':
                    item['claimed_validation'] = item.get('validation')
                    item['validation'] = 'Unverified'
                    item['validation_evidence'] = {}
            elif security.content_fingerprint(old) != security.content_fingerprint(item):
                item['content_editor_id'] = user['id']
                item.setdefault('security_history', []).append(old.get('security', {}))
                item['security'] = dict(status='Pending review', classification=(old.get('security') or {}).get('classification', 'Restricted'), external_ai=False)
                if kind == 'source':
                    item.update(chunks=[], chunk_count=0, index_status='Pending', validation='Unverified', validation_evidence={})
            if kind == 'investigation' and (old is None or security.proposal_hash(old) != security.proposal_hash(item)):
                item['proposal_author_id'] = user['id']
                prior = item.get('approval_decision')
                if prior and prior.get('status') == 'Approved':
                    item.setdefault('approval_history', []).append(prior)
                    item['approval_decision'] = dict(status='Pending', notes='Proposal changed; independent approval required.')
            security.audit(self.db, 'record.write.intent', item['id'], kind=kind, content_hash=security.content_fingerprint(item))
        if cust != self.customer and self.customer not in ('My Workspace', 'All') and cust != 'General':
            raise ValueError('Customer scope is not authorised for this write.')
        if kind == 'source' and cust == 'General' and self.customer not in ('My Workspace', 'All') and item.get('generalization_confirmed') is not True:
            raise ValueError('General knowledge requires explicit de-identification confirmation.')
        document = dict(item)
        expected = document.get('revision', 0)
        document['revision'] = expected + 1
        if expected:
            query = {'id': item['id'], 'revision': expected}
            if self.customer not in ('My Workspace', 'All'):
                query['customer'] = item.get('customer', self.customer)
            result = self.collection(kind).replace_one(query, document)
            if result.matched_count != 1:
                raise ConflictError('This record changed in another request. Reload and try again.')
        else:
            try:
                self.collection(kind).insert_one(document.copy())
            except DuplicateKeyError:
                raise ConflictError('This document is already in the workspace. Use its existing source or change the content.') from None
        item['revision'] = document['revision']
        if user:
            security.audit(self.db, 'record.write.completed', item['id'], kind=kind, revision=item['revision'])
        return item

    def indexed_chunks(self, model):
        query = {**self.scope('source'), 'index_status': 'Ready', 'embedding_model': model}
        for source in self.db.sources.find(query, {'_id': 0}):
            for chunk in source.pop('chunks', []):
                yield source, chunk

    def outcome_signals(self, source_ids):
        """Summarize consultant outcomes without treating ticket closure as success."""
        signals = {source_id: dict(validated_successes=0, unsuccessful=0, workarounds=0, partly_useful=0)
            for source_id in source_ids}
        if not signals:
            return signals
        query = {**self.scope('investigation'), 'selected_source': {'$in': list(signals)}}
        projection = {'_id': 0, 'selected_source': 1, 'outcome': 1, 'type': 1}
        for item in self.db.investigations.find(query, projection):
            outcome = item.get('outcome') or {}
            source_id = item.get('selected_source')
            if source_id not in signals:
                continue
            required = ('tested', 'customer_confirmed')
            if item.get('type') == 'Change request':
                required += ('approved', 'developed', 'deployed', 'verified')
            if outcome.get('status') in ('Worked', 'Resolved') and all(outcome.get(key) for key in required):
                signals[source_id]['validated_successes'] += 1
            elif outcome.get('status') == 'Workaround':
                signals[source_id]['workarounds'] += 1
            elif outcome.get('status') in ('Did not work', 'Unresolved', 'Escalated') or outcome.get('usefulness') == 'Not useful':
                signals[source_id]['unsuccessful'] += 1
            elif outcome.get('status') == 'Partially worked' or outcome.get('usefulness') == 'Partly useful':
                signals[source_id]['partly_useful'] += 1
        return signals

    def close(self):
        self.client.close()
