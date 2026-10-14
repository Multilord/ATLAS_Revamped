"""Scoped hybrid retrieval with real embeddings and citation-checked AI synthesis."""
import math
import re
import time
from datetime import datetime, timezone
from ai import AIError

STOP = set('the a an and or is are was were to of for in on with this that it by from unable cannot can not error issue sap reported user please'.split())


def tokens(text):
    return set(re.findall(r'[a-z0-9_]{2,}', text.lower())) - STOP


def cosine(left, right):
    if len(left) != len(right) or not left:
        raise AIError('Stored embeddings do not match the current model. Reindex knowledge before analysing.')
    denominator = math.sqrt(sum(x*x for x in left) * sum(x*x for x in right))
    return sum(a*b for a, b in zip(left, right)) / denominator if denominator else 0


def normalized(text):
    return ' '.join(text.split()).casefold()


def retrieve(ticket, store, ai):
    started = time.monotonic()
    # Search requires one query embedding plus one generation. Avoid a partial
    # result when a constrained account has capacity for only one request.
    ai.ensure_capacity(2)
    notes = [e['text'] for e in ticket.get('timeline', []) if e['kind'] in ('Note', 'Test', 'Communication', 'Attachment')][-15:]
    query = '\n'.join([ticket['title'], ticket['description'], ticket.get('error_code', ''), ticket.get('customisation', '')] + notes)[:16000]
    query_vector = ai.embed([query])[0]
    query_tokens = tokens(query)
    candidates = []
    for source, chunk in store.indexed_chunks(ai.config.embedding_model):
        if source['customer'] not in (ticket['customer'], 'General'):
            continue
        similarity = cosine(query_vector, chunk['embedding'])
        overlap = len(query_tokens & tokens(chunk['text'])) / max(1, len(query_tokens))
        exact = bool(source.get('error_code')) and re.sub(r'\W', '', source['error_code']).lower() in re.sub(r'\W', '', query).lower()
        if similarity < .25 and overlap < .1 and not exact:
            continue
        same_app = normalized(source['application']) == normalized(ticket['application'])
        same_version = bool(source.get('version')) and normalized(source['version']) == normalized(ticket['version'])
        score = .6 * max(0, similarity) + .2 * overlap + .1 * exact + .05 * same_app + .05 * same_version
        candidates.append((score, source, chunk, same_app, same_version))
    candidates.sort(key=lambda c: c[0], reverse=True)
    selected, per_source = [], {}
    for candidate in candidates:
        id = candidate[1]['id']
        if per_source.get(id, 0) >= 2:
            continue
        selected.append(candidate)
        per_source[id] = per_source.get(id, 0) + 1
        if len(selected) == 10:
            break
    evidence = [{'source_id': s['id'], 'chunk_id': c['id'], 'title': s['title'], 'application': s['application'], 'version': s['version'], 'updated_at': s['updated_at'], 'validation': s['validation'], 'text': c['text']} for _, s, c, _, _ in selected]
    result = ai.investigate({k: ticket.get(k, '') for k in ('title', 'description', 'application', 'version', 'error_code', 'customisation', 'type')} | {'recent_notes': [n[:2000] for n in notes]}, evidence)
    lookup = {(s['id'], c['id']): (score, s, c, app, version) for score, s, c, app, version in selected}
    recommendations, seen = [], set()
    for recommendation in result.recommendations:
        key = (recommendation.source_id, recommendation.chunk_id)
        if key not in lookup:
            raise AIError('AI returned a citation outside the authorised evidence. No analysis was saved.')
        score, source, chunk, same_app, same_version = lookup[key]
        if normalized(recommendation.quote) not in normalized(chunk['text']):
            raise AIError('AI evidence quotation did not match the source. No analysis was saved; retry.')
        if source['id'] in seen:
            continue
        seen.add(source['id'])
        warnings = list(recommendation.warnings)
        if not same_app:
            warnings.append('Application differs or is unspecified. Confirm applicability.')
        if not same_version:
            warnings.append('Release differs or is unspecified. Confirm applicability in the current system.')
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(source['updated_at'].replace('Z', '+00:00'))).days
        if age > 540 or source['validation'] == 'Outdated':
            warnings.append('This source may be outdated. Validate against the current environment.')
        verified = source['validation'] == 'Verified' and all(source.get('validation_evidence', {}).get(k) for k in ('tested', 'customer_confirmed', 'deployed'))
        confidence = recommendation.confidence
        if not same_app or not same_version or age > 540 or source['validation'] == 'Outdated':
            confidence = 'Low'
        elif confidence == 'High' and (not verified or warnings):
            confidence = 'Medium'
        label = 'Workaround' if source.get('solution_kind') == 'Workaround' or recommendation.kind == 'Workaround' else 'Verified historical fix' if verified else 'Likely solution'
        recommendations.append(dict(source_id=source['id'], chunk_id=chunk['id'], quote=recommendation.quote,
            title=recommendation.title, source_title=source['title'], source_type=source['source_type'],
            score=round(score * 100), confidence=confidence, label=label, reasons=[recommendation.reason],
            warnings=warnings, steps=recommendation.steps, version=source['version'], updated_at=source['updated_at'], compatible=same_app and same_version))
    sufficient = any(r['confidence'] != 'Low' for r in recommendations)
    return dict(classification=result.classification, state='Evidence found' if sufficient else 'Insufficient evidence',
        summary=result.summary, next_steps=result.next_steps, results=recommendations,
        engine=f'Gemini {ai.config.model} + {ai.config.embedding_model}; hybrid retrieval',
        model=ai.config.model, duration_seconds=round(time.monotonic() - started, 2),
        analysed_at=datetime.now(timezone.utc).isoformat(), evidence_count=len(evidence))
