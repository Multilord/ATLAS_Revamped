"""Explicit, repeatable synthetic reference library; never loaded at startup."""
from historical import DEMO_CUSTOMER, prepare_import

TOPICS = (
    dict(key='FEFO', title='Expiry-based batch selection', application='SAP Manufacturing', module='PP', component='Batch determination',
        symptom='The proposed batch list places a later-expiring batch ahead of an earlier-expiring batch.',
        observations='The fictional QA export contains three eligible batches. Two carry complete expiry dates; one has no maintained expiry value. The sort definition and the batch eligibility list were captured separately.',
        checks='Compare expiry values, stock eligibility and the configured sort direction. Reproduce with the same material, plant and order quantity. Do not assume that a batch missing from the proposal is excluded by expiry alone.',
        correction='In this fictional example, the approved QA sort direction was corrected and missing test-master expiry data was populated. This is a simulated finding, not a universal SAP configuration instruction.',
        expected='The earliest eligible expiry appears first, missing expiry values follow the agreed exception rule, and unavailable stock remains excluded.'),
    dict(key='VENDOR', title='Vendor consistency during batch selection', application='SAP Manufacturing', module='PP', component='Batch enhancement',
        symptom='A process order proposes batches from two vendors although the requester expected one vendor.',
        observations='The first vendor has insufficient eligible quantity. The original request says to keep one vendor, while a later note permits fallback. Neither note records a confirmed priority between these rules.',
        checks='Confirm whether the first selected batch fixes the vendor for the whole order. Ask whether shortage permits another vendor, a partial proposal or manual procurement. Record the answer before proposing enhancement behaviour.',
        correction='The fictional stakeholder approved a single-vendor proposal with an explicit shortage message; the demo enhancement was tested against this documented choice. A different customer may require a different rule.',
        expected='All proposed batches belong to the chosen vendor; an insufficient quantity produces the agreed advisory message and preserves the remaining quantity.'),
    dict(key='PLANT', title='Batch procedure onboarding for a new plant', application='SAP Procurement', module='MM', component='Plant configuration',
        symptom='Batch proposals work in an existing plant but are absent in a newly onboarded plant.',
        observations='The fictional comparison shows different procedure assignments and incomplete material test data. The source plant has additional custom rules that have not been approved for the target plant.',
        checks='Compare the approved process, procedure assignment and relevant master-data readiness. Verify plant scope and release. Obtain business approval rather than copying all settings from the source plant.',
        correction='The approved demo procedure assignment and required QA material attributes were completed for the target plant. Unapproved source-plant customisations were excluded.',
        expected='The target plant produces a proposal for the approved material set, rejects ineligible stock and leaves the original plant behaviour unchanged.'),
    dict(key='QUANTITY', title='Repeated-component quantity commitments', application='SAP Manufacturing', module='PP', component='Availability check',
        symptom='The second occurrence of a component receives a batch quantity already committed to the first line.',
        observations='The fictional order has two component lines sharing a material and batch. Individually each proposal fits stock; the combined allocation exceeds eligible quantity. A comparison order with one line does not reproduce the symptom.',
        checks='Capture the two line quantities, batch availability and the commitment sequence. Confirm whether the second calculation subtracts the first allocation. Reproduce with partial stock and independent batches before asserting a code defect.',
        correction='A fictional QA change accounted for prior line allocations before proposing quantity for the next line. The result must be reviewed for the actual release and customer enhancement design.',
        expected='The combined allocated quantity never exceeds eligible availability, and the remaining requirement is displayed explicitly for each line.'),
)


def library_documents(customer):
    documents = []
    modes = (
        ('validated', 'Resolution guide', 'Reviewed', 'Simulated verified resolution',
         'The fictional reviewer recorded all three acceptance cases as passed in QA and a separate post-deployment check as passed. These results are invented for the demonstration, not customer evidence.'),
        ('workaround', 'Known issue', 'Workaround', 'Temporary manual workaround',
         'A consultant manually reviewed the proposal and remaining quantity before release. The intervention restored the demo process but did not establish or remove the underlying cause. Repeat occurrences require investigation.'),
        ('unresolved', 'Investigation report', 'Unresolved findings', 'Open investigation and failed attempts',
         'Repeating the transaction and refreshing the proposed list did not remove the symptom. The evidence does not establish a root cause. Escalate with the exact release, input data and reproduction steps; no production correction is recommended.'),
        ('legacy', 'Change record', 'Reviewed', 'Outdated alternative requiring comparison',
         'This older fictional proposal assumed sufficient stock and a single component line. It conflicts with the newer acceptance scenarios. It is retained to demonstrate conflicting evidence and must not be reused without review.'),
    )
    for topic in TOPICS:
        for mode, kind, evidence, label, findings in modes:
            reference = f'HIST-DEMO-{topic["key"]}-{mode.upper()}'
            body = '\n\n'.join([
                'SYNTHETIC DEMONSTRATION DOCUMENT — all observations, decisions and results below are fictional.',
                f'Document: {reference}\nScenario: {topic["title"]}\nRecord type: {kind}\nEvidence: {label}',
                f'Environment and scope\nFictional QA plant DEMO-01; SAP S/4HANA demonstration environment. Module {topic["module"]}; component {topic["component"]}. Validate applicability to the actual platform, release and customisation before reuse.',
                f'Reported symptom\n{topic["symptom"]}',
                f'Investigation observations\n{topic["observations"]}',
                f'Diagnostic procedure\n{topic["checks"]}',
                f'Findings and disposition\n{findings}',
                f'Proposed approach\n{topic["correction"] if mode == "validated" else "No verified permanent fix is supplied by this record. Use the findings to plan investigation and obtain the missing customer decisions."}',
                f'Acceptance scenarios\n1. Baseline: {topic["expected"]}\n2. Boundary: repeat with insufficient stock and document the shortfall.\n3. Regression: repeat the established process in a separate demo order and compare the recorded outputs.',
                'Verification and limitations\n' + ('Simulated evidence IDs: QA-BASELINE, QA-BOUNDARY and QA-REGRESSION. All are fictional; no real SAP system was tested.' if mode == 'validated' else 'No permanent resolution has been verified. Record actual versus expected behaviour and preserve failed attempts.'),
                'References\nThis document is self-contained synthetic training material. No SAP documentation, customer approval or production deployment is claimed. Link it only to synthetic tickets.'])
            documents.append(dict(title=f'[SYNTHETIC] {topic["title"]} — {label}', content=body,
                customer=customer, application=topic['application'], platform='S/4HANA On-Premise',
                module=topic['module'], component=topic['component'], version='S/4HANA 2020' if mode == 'legacy' else 'S/4HANA 2023',
                document_version='1.0', source_updated_at='2021-02-01' if mode == 'legacy' else '2026-09-01',
                source_reference=reference, source_type=kind, evidence_quality=evidence,
                synthetic=True, review_notes='Reviewed for fictional demonstration use only.', demo_mode=mode, demo_topic=topic['key']))
    return documents


def install_library(store):
    customer = DEMO_CUSTOMER if store.customer in ('My Workspace', 'All') else store.customer
    documents = []
    for raw in library_documents(customer):
        doc = prepare_import({'defaults': raw, 'content': raw['content'], 'filename': raw['source_reference']+'.txt'}, store)[0]
        doc['id'] = raw['source_reference']
        doc['historical_library'] = 'synthetic-v1'
        doc['simulated_quality'] = 'Verified fix' if raw['demo_mode'] == 'validated' else ''
        if raw['demo_mode'] == 'legacy':
            doc['validation'] = 'Outdated'
            doc['conflicts_with'] = [f'HIST-DEMO-{raw["demo_topic"]}-VALIDATED']
        documents.append(doc)
    # Stable IDs and insert-only writes preserve subsequent reviews and indexing.
    for doc in documents:
        existing = store.db.sources.find_one({'id': doc['id']})
        if existing and (existing.get('historical_library') != 'synthetic-v1' or existing.get('customer') != customer):
            raise ValueError('A demo-library ID is already used in another scope.')
    saved = []
    for doc in documents:
        existing = store.db.sources.find_one({'id': doc['id']})
        if not existing:
            store.save(doc, 'source')
            saved.append(doc['id'])
    return dict(saved=saved, existing=len(documents)-len(saved), indexing_requests=0)
