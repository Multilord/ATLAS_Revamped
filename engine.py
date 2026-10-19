"""Scoped contextual retrieval and citation-checked AI synthesis."""
import math
import re
import time
from datetime import datetime, timezone
from ai import AIError
from historical import permitted, quality, synthetic
import security

STOP = set('the a an and or is are was were to of for in on with this that it by from unable cannot can not error issue sap reported user please'.split())
MAX_SOURCE_AGE_DAYS = 540


def tokens(text):
    return set(re.findall(r'[a-z0-9_]{2,}', str(text or '').lower())) - STOP


def cosine(left, right):
    if len(left) != len(right) or not left:
        raise AIError('Stored embeddings do not match the current model. Reindex knowledge before analysing.')
    denominator = math.sqrt(sum(x*x for x in left) * sum(y*y for y in right))
    return sum(a*b for a, b in zip(left, right)) / denominator if denominator else 0


def normalized(text):
    return ' '.join(str(text or '').split()).casefold()


def same(left, right):
    return bool(normalized(left) and normalized(right) and normalized(left) == normalized(right))


def source_age(source):
    """Upload/index timestamps are not evidence of when source guidance changed."""
    value = source.get('source_updated_at')
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).days)
    except (TypeError, ValueError):
        return None


def rank_candidates(ticket, store, ai, query_vector=None, limit=10):
    """Context-aware evidence ranking, reusable by the offline evaluator."""
    notes = [e.get('text', '') for e in ticket.get('timeline', []) if e.get('kind') in ('Note', 'Test', 'Communication', 'Attachment')][-15:]
    solutioning = ticket.get('solutioning') or {}
    consultant_context = [f'{section}: {key}: {value}' for section, fields in solutioning.items()
        if isinstance(fields, dict) for key, value in fields.items() if isinstance(value, str) and value.strip()]
    query = '\n'.join([ticket.get('title', ''), ticket.get('description', ''), ticket.get('error_code', ''), ticket.get('customisation', ''), ticket.get('module', ''), ticket.get('business_process', '')] + notes + consultant_context)[:16000]
    if query_vector is None:
        query_vector = ai.embed([query])[0]
    query_tokens = tokens(query)
    query_error = re.sub(r'\W', '', ticket.get('error_code', '')).casefold()
    indexed = list(store.indexed_chunks(ai.config.embedding_model))
    outcome_signals = store.outcome_signals(list({source['id'] for source, _ in indexed})) if hasattr(store, 'outcome_signals') else {}
    candidates = []
    for source, chunk in indexed:
        if security.principal.get() and not security.ai_allowed(source):
            continue
        if not permitted(source, ticket):
            continue
        similarity = max(0, cosine(query_vector, chunk['embedding']))
        overlap = len(query_tokens & tokens(chunk.get('text', ''))) / max(1, len(query_tokens))
        source_error = re.sub(r'\W', '', source.get('error_code', '')).casefold()
        exact_error = bool(query_error and source_error and (
            query_error == source_error or
            (min(len(query_error), len(source_error)) >= 4 and
             (query_error in source_error or source_error in query_error))))
        matches = {field: same(source.get(field), ticket.get(field)) for field in ('application', 'version', 'module', 'platform', 'business_process', 'customisation')}
        mismatch_version = bool(source.get('version') and ticket.get('version') and not matches['version'])
        mismatch_platform = bool(source.get('platform') and ticket.get('platform') and not matches['platform'])
        age = source_age(source)
        stale = source.get('validation') == 'Outdated' or (age is not None and age > MAX_SOURCE_AGE_DAYS)
        validation = source.get('validation_evidence') or {}
        verified = not synthetic(source) and quality(source) != 'Unresolved findings' and source.get('validation') == 'Verified' and all(validation.get(k) for k in ('tested', 'customer_confirmed', 'deployed'))
        outcome = outcome_signals.get(source['id'], {})
        successes, failures = outcome.get('validated_successes', 0), outcome.get('unsuccessful', 0)
        score = (.44 * similarity + .18 * overlap + .14 * exact_error + .06 * matches['application'] +
                 .04 * matches['version'] + .05 * matches['module'] + .03 * matches['platform'] +
                 .025 * matches['business_process'] + .025 * matches['customisation'])
        score += min(.04, successes * .01) + (.035 if verified else 0)
        score -= min(.08, failures * .02) + (.12 if stale else 0)
        score -= (.10 if mismatch_platform else 0) + (.08 if mismatch_version else 0)
        if similarity < .20 and overlap < .08 and not exact_error:
            continue
        reasons = []
        if exact_error: reasons.append('Exact error code match')
        for field, label in [('application','Same application'),('module','Same module'),('platform','Same platform'),('version','Same release'),('business_process','Same business process'),('customisation','Matching customer customization')]:
            if matches[field]: reasons.append(label)
        if successes: reasons.append(f'{successes} validated successful outcome(s) recorded')
        if verified: reasons.append('Source includes testing, customer confirmation and deployment evidence')
        candidates.append(dict(score=max(0, score), source=source, chunk=chunk, matches=matches,
            mismatch_version=mismatch_version, mismatch_platform=mismatch_platform, age=age,
            stale=stale, verified=verified, reasons=reasons, outcome=outcome, exact_error=exact_error))
    candidates.sort(key=lambda item: (item['score'], item['exact_error'], item['matches']['version']), reverse=True)
    selected, per_source = [], {}
    for row in candidates:
        source_id = row['source']['id']
        if per_source.get(source_id, 0) >= 2: continue
        selected.append(row)
        per_source[source_id] = per_source.get(source_id, 0) + 1
        if len(selected) >= limit: break
    return selected, notes


def conflicting_sources(selected):
    """Return selected source IDs with explicitly or contextually conflicting evidence."""
    by_id = {row['source']['id']: row for row in selected}
    conflicts = {source_id: set() for source_id in by_id}
    for source_id, row in by_id.items():
        for other in row['source'].get('conflicts_with', []):
            conflicts[source_id].add(other)
            if other in by_id:
                conflicts[other].add(source_id)
    rows = list(by_id.items())
    for index, (left_id, left) in enumerate(rows):
        a = left['source']
        left_solution = normalized(a.get('solution') or ' '.join(a.get('steps') or []))
        if not a.get('error_code') or not left_solution: continue
        for right_id, right in rows[index + 1:]:
            b = right['source']
            right_solution = normalized(b.get('solution') or ' '.join(b.get('steps') or []))
            same_context = (same(a.get('error_code'), b.get('error_code')) and same(a.get('application'), b.get('application')) and same(a.get('version'), b.get('version')))
            if same_context and right_solution and left_solution != right_solution:
                conflicts[left_id].add(right_id)
                conflicts[right_id].add(left_id)
    return conflicts


def retrieve(ticket, store, ai):
    if security.principal.get():
        security.enforce_ai(ticket)
    started = time.monotonic()
    ai.ensure_capacity(2)
    selected, notes = rank_candidates(ticket, store, ai)
    evidence = []
    for row in selected:
        source, chunk = row['source'], row['chunk']
        evidence.append(dict(source_id=source['id'], chunk_id=chunk['id'], title=source['title'],
            application=source.get('application', ''), platform=source.get('platform', ''), module=source.get('module', ''),
            business_process=source.get('business_process', ''), customisation=source.get('customisation', ''),
            version=source.get('version', ''), source_updated_at=source.get('source_updated_at'),
            validation=source.get('validation', 'Unverified'), solution_kind=source.get('solution_kind', 'Unknown'),
            evidence_quality=quality(source), synthetic=synthetic(source),
            outcome_signals=row['outcome'], conflicts_with=source.get('conflicts_with', []), text=chunk['text']))
    ticket_context = {k: ticket.get(k, '') for k in ('title','description','application','platform','module','business_process','version','error_code','customisation','type','priority')}
    ticket_context['consultant_solutioning'] = ticket.get('solutioning') or {}
    ticket_context['recent_notes'] = [note[:2000] for note in notes]
    result = ai.investigate(ticket_context, evidence)
    lookup = {(row['source']['id'], row['chunk']['id']): row for row in selected}
    conflicts = conflicting_sources(selected)
    recommendations, seen = [], set()
    for recommendation in result.recommendations:
        key = (recommendation.source_id, recommendation.chunk_id)
        if key not in lookup:
            raise AIError('AI returned a citation outside the authorised evidence. No analysis was saved.')
        row = lookup[key]
        source, chunk = row['source'], row['chunk']
        if normalized(recommendation.quote) not in normalized(chunk['text']):
            raise AIError('AI evidence quotation did not match the source. No analysis was saved; retry.')
        if source['id'] in seen: continue
        seen.add(source['id'])
        warnings = list(recommendation.warnings)
        if synthetic(source): warnings.append('Synthetic demonstration evidence; not real customer validation.')
        if quality(source) == 'Unresolved findings': warnings.append('Unresolved historical findings support diagnosis only; no confirmed fix is recorded.')
        if not row['matches']['application']: warnings.append('Application differs or is unspecified. Confirm applicability.')
        if row['mismatch_platform']: warnings.append('SAP platform differs. Check system-specific behavior before applying this guidance.')
        elif ticket.get('platform') and not row['matches']['platform']: warnings.append('Source platform is unspecified. Confirm applicability.')
        if row['mismatch_version']: warnings.append('Release differs. Confirm applicability in the current system.')
        elif ticket.get('version') and not row['matches']['version']: warnings.append('Source release is unspecified. Confirm applicability.')
        if ticket.get('module') and source.get('module') and not row['matches']['module']: warnings.append('SAP module differs from the ticket context.')
        if row['age'] is None and source.get('validation') != 'Outdated': warnings.append('Original source freshness is unknown; upload date was not used as a proxy.')
        elif row['stale']: warnings.append('This source may be outdated. Validate against current product guidance and system version.')
        if row['outcome'].get('unsuccessful'): warnings.append(f"{row['outcome']['unsuccessful']} unsuccessful or not-useful outcome(s) recorded for this source.")
        if conflicts.get(source['id']): warnings.append('Conflicting solution evidence exists for the same context. Compare these sources before acting: ' + ', '.join(sorted(conflicts[source['id']])) + '.')
        if source.get('solution_kind') == 'Workaround': warnings.append('Historical source is labeled as a workaround, not a confirmed permanent fix.')
        confidence = recommendation.confidence
        if (not row['matches']['application'] or row['mismatch_platform'] or row['mismatch_version'] or row['stale'] or conflicts.get(source['id'])): confidence = 'Low'
        elif confidence == 'High' and (not row['verified'] or warnings): confidence = 'Medium'
        label = 'Workaround' if source.get('solution_kind') == 'Workaround' or recommendation.kind == 'Workaround' else 'Verified historical fix' if row['verified'] else 'Likely solution'
        if quality(source) == 'Unresolved findings':
            label, confidence = 'Investigation findings', 'Low'
        reasons = list(dict.fromkeys(row['reasons'] + [recommendation.reason]))
        recommendations.append(dict(source_id=source['id'], chunk_id=chunk['id'], quote=recommendation.quote,
            title=recommendation.title, source_title=source['title'], source_type=source['source_type'],
            score=round(row['score'] * 100), confidence=confidence, label=label, reasons=reasons,
            warnings=list(dict.fromkeys(warnings)), steps=recommendation.steps, version=source.get('version',''),
            platform=source.get('platform',''), module=source.get('module',''), source_updated_at=source.get('source_updated_at'),
            age_days=row['age'], compatible=not row['mismatch_version'] and not row['mismatch_platform'],
            conflicts_with=sorted(conflicts.get(source['id'], [])), outcome_signals=row['outcome']))
    recommendations.sort(key=lambda item: (item['score'], item['confidence'] != 'Low'), reverse=True)
    sufficient = any(r['confidence'] != 'Low' for r in recommendations)
    conflict_pairs = sorted({tuple(sorted((source_id, other))) for source_id, others in conflicts.items() for other in others})
    return dict(classification=result.classification, state='Evidence found' if sufficient else 'Insufficient evidence',
        summary=result.summary, next_steps=result.next_steps,
        ai_solutioning=dict(provenance='AI-generated; not consultant-verified', functional_assessment=result.functional_assessment,
            technical_investigation_areas=result.technical_investigation_areas,
            clarification_questions=result.clarification_questions, assumptions=result.assumptions,
            risks=result.risks, validation_steps=result.validation_steps),
        results=recommendations, conflicting_evidence=conflict_pairs,
        engine=f'Gemini {ai.config.model} + {ai.config.embedding_model}; contextual hybrid retrieval',
        model=ai.config.model, duration_seconds=round(time.monotonic() - started, 2),
        analysed_at=datetime.now(timezone.utc).isoformat(), evidence_count=len(evidence))
