"""Deterministic, evidence-only baseline. No model calls or external data transfer."""
import re
from datetime import datetime, timezone

STOP = set('the a an and or is are was were to of for in on with this that it by from unable cannot can not error issue sap reported user please'.split())
SYNONYMS = {'supplier': 'vendor', 'invoices': 'invoice', 'posting': 'post', 'posted': 'post', 'payments': 'payment', 'orders': 'order', 'approvals': 'approval', 'authorisation': 'authorization', 'permissions': 'authorization', 'login': 'logon', 'failed': 'failure', 'fails': 'failure'}


def tokens(text):
    return {SYNONYMS.get(t, t) for t in re.findall(r'[a-z0-9_]+', text.lower()) if t not in STOP and len(t) > 1}


def classify(text):
    if re.search(r'\b[zy][a-z0-9_]{3,}\b|customi[sz]|custom workflow', text, re.I):
        return 'Customer customisation'
    if re.search(r'payment terms|master data|approval|business process|account assignment', text, re.I):
        return 'Functional / business process'
    if re.search(r'\bSAP\b|dump|standard|logon|timeout', text, re.I):
        return 'Standard product'
    return 'Unknown'


def retrieve(ticket, sources):
    text = ' '.join([ticket['title'], ticket['description'], ticket.get('error_code', ''), ticket.get('customisation', '')] + [x['text'] for x in ticket.get('timeline', []) if x['kind'] in ('Note', 'Test', 'Communication', 'Attachment')])
    query = tokens(text)
    results = []
    for source in sources:
        # Defense in depth: do not trust a caller to pre-filter its candidate set.
        if source['customer'] not in ('General', ticket['customer']):
            continue
        match = query & tokens(source['title'] + ' ' + source['content'] + ' ' + ' '.join(source['tags']))
        exact = bool(source['error_code']) and re.sub(r'\W', '', source['error_code'].lower()) in re.sub(r'\W', '', text.lower())
        if len(match) < 2 and not exact:
            continue
        relevant = len(match) / max(1, len(query))
        if relevant < .10 and not exact:
            continue
        same_app = source['application'] == ticket['application']
        if not same_app and not exact:
            continue
        same_version = source['version'] == ticket['version']
        compatible = same_app and same_version
        missing_context = not ticket.get('version') or not ticket.get('application')
        warnings = []
        if not same_app:
            warnings.append('Application mismatch: verify applicability before using this source.')
        if not same_version:
            warnings.append('Version mismatch: source covers ' + source['version'] + '.')
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(source['updated_at']).replace(tzinfo=timezone.utc)).days
        if age > 540 or source['validation'] == 'Outdated':
            warnings.append('Outdated evidence: confirm against the current customer system.')
        checks = source.get('validation_evidence', {})
        verified = source['validation'] == 'Verified' and all(checks.get(k) for k in ('tested', 'customer_confirmed', 'deployed'))
        score = round(40 * min(relevant, 1) + 20 * exact + 10 * same_app + 10 * same_version + 10 * verified + 5 * (age <= 540) + 5 * (source['customer'] == ticket['customer']))
        reasons = ['Matching terms: ' + ', '.join(sorted(match)[:7])]
        if exact:
            reasons.append('Exact error code match')
        if compatible:
            reasons.append('Application and release match')
        if verified:
            reasons.append('Source records testing, customer confirmation and deployment')
        label = 'Workaround' if source['solution_kind'] == 'Workaround' else 'Verified historical fix' if verified else 'Likely solution'
        confidence = 'High' if compatible and verified and exact and not warnings else 'Medium' if compatible and (exact or relevant >= .25) else 'Low'
        if missing_context or warnings:
            confidence = 'Low'
        results.append({'source_id': source['id'], 'title': source['solution'], 'source_title': source['title'], 'source_type': source['source_type'], 'score': score, 'confidence': confidence, 'label': label, 'reasons': reasons, 'warnings': warnings, 'steps': source['steps'], 'version': source['version'], 'updated_at': source['updated_at'], 'conflicts_with': source.get('conflicts_with', []), 'compatible': compatible})
    results.sort(key=lambda r: (r['compatible'], r['score']), reverse=True)
    visible_ids = {r['source_id'] for r in results}
    for result in results:
        conflicts = [c for c in result.pop('conflicts_with') if c in visible_ids]
        if conflicts:
            result['warnings'].append('Conflicting guidance in ' + ', '.join(conflicts) + '. Verify the current system configuration.')
            if result['confidence'] == 'High':
                result['confidence'] = 'Medium'
    results = results[:5]
    sufficient = any(r['compatible'] and r['confidence'] != 'Low' for r in results)
    return {'classification': classify(text), 'state': 'Evidence found' if sufficient else 'Insufficient evidence', 'summary': 'Review the evidence and reproduce the issue in a quality environment before selecting a solution.' if sufficient else 'No sufficiently supported solution for this context. Capture the exact error, confirm the release and recent changes, and involve the appropriate specialist.', 'results': results, 'engine': 'Local lexical retrieval with synonyms and context ranking. Scores are heuristic relevance, not probabilities.'}
