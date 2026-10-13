import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server
from engine import classify, retrieve
from seed import SOURCES, investigations


class RetrievalTests(unittest.TestCase):
    def test_customer_boundary_applied_before_retrieval(self):
        result = retrieve(investigations()[0], SOURCES)
        self.assertNotIn('PRIVATE-900', json.dumps(result))
        self.assertNotIn('OTHER_CUSTOMER_SECRET', json.dumps(result))

    def test_current_release_ranks_above_legacy_and_conflicts_visible(self):
        result = retrieve(investigations()[0], SOURCES)
        ids = [r['source_id'] for r in result['results']]
        self.assertIn('INC-18372', ids)
        self.assertLess(ids.index('INC-18372'), ids.index('INC-09014'))
        legacy = next(r for r in result['results'] if r['source_id'] == 'INC-09014')
        self.assertEqual(legacy['confidence'], 'Low')
        self.assertTrue(any('Version mismatch' in w for w in legacy['warnings']))
        self.assertTrue(any('Conflicting' in w for r in result['results'] for w in r['warnings']))

    def test_no_evidence_abstains(self):
        ticket = {**investigations()[0], 'title':'Printer toner streaks', 'description':'Paper jam cyan cartridge', 'error_code':'', 'timeline':[]}
        result = retrieve(ticket, SOURCES)
        self.assertEqual(result['state'], 'Insufficient evidence')
        self.assertEqual(result['results'], [])

    def test_custom_workflow_prefers_matching_case(self):
        result = retrieve(investigations()[1], SOURCES)
        self.assertEqual(result['classification'], 'Customer customisation')
        self.assertEqual(result['results'][0]['source_id'], 'INC-2041')

    def test_generic_words_do_not_pull_unrelated_applications(self):
        result = retrieve(investigations()[0], SOURCES)
        self.assertNotIn('INC-3022', [r['source_id'] for r in result['results']])

    def test_unverified_closure_is_not_a_verified_fix(self):
        sources = copy.deepcopy(SOURCES)
        sources[0]['validation_evidence']['customer_confirmed'] = False
        result = retrieve(investigations()[0], sources)
        match = next(r for r in result['results'] if r['source_id'] == 'INC-18372')
        self.assertEqual(match['label'], 'Likely solution')

    def test_notes_participate_in_retrieval(self):
        ticket = {**investigations()[0], 'title':'Need assistance', 'description':'Investigating', 'error_code':'', 'timeline':[{'kind':'Note','text':'Invoice posting vendor payment terms F5 808'}]}
        self.assertTrue(retrieve(ticket, SOURCES)['results'])

    def test_version_mismatch_abstains(self):
        ticket = {**investigations()[0], 'version':'Unknown release'}
        self.assertEqual(retrieve(ticket, SOURCES)['state'], 'Insufficient evidence')


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        temp_root = server.ROOT / 'tmp' / 'tests'
        temp_root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=temp_root)
        self.assertTrue(Path(self.tmp.name).resolve().is_relative_to(temp_root.resolve()))
        self.old_db = server.DB
        server.DB = Path(self.tmp.name) / 'test.sqlite3'
        server.initialize()

    def tearDown(self):
        server.DB = self.old_db
        self.tmp.cleanup()

    def new_case(self, kind='Incident'):
        return server.create_investigation(dict(title='Invoice posting fails', description='Vendor payment terms missing. Error F5 808.', application='SAP Finance', version='S/4HANA 2023', type=kind, priority='High'))


class WorkflowTests(DatabaseCase):
    def test_full_flow_persists_and_audits(self):
        case = self.new_case()
        case = server.update_investigation(case, 'analyze', {})
        source_id = case['analysis']['results'][0]['source_id']
        case = server.update_investigation(case, 'decision', {'source_id':source_id,'decision':'Accepted'})
        server.update_investigation(case, 'outcome', dict(status='Resolved', notes='Tested in QA, user confirmed.', tested=True, customer_confirmed=True, usefulness='Useful'))
        stored = server.get_record(case['id'], 'investigation')
        self.assertEqual(stored['status'], 'Resolved')
        self.assertEqual(stored['outcome']['selected_source'], source_id)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM audit WHERE record_id=?', (case['id'],)).fetchone()[0], 4)
        server.initialize()
        self.assertEqual(server.get_record(case['id'], 'investigation')['status'], 'Resolved')

    def test_customer_write_and_read_isolation(self):
        with self.assertRaises(ValueError):
            server.create_investigation({'customer':'Beacon Retail'})
        self.assertIsNone(server.get_record('PRIVATE-900', 'source'))
        self.assertEqual(len(server.records('source')), 9)

    def test_intake_preserves_chronology_and_rejects_bad_timestamps(self):
        obj = dict(title='Case',description='SAP issue', timeline=[dict(at='2026-10-12T12:00:00+08:00',text='Later'),dict(at='2026-10-12T02:00:00Z',text='Earlier')])
        parsed = server.parse_intake({'content':json.dumps(obj)})
        self.assertEqual([e['text'] for e in parsed['timeline']], ['Earlier','Later'])
        obj['timeline'][0]['at'] = 'yesterday'
        with self.assertRaises(ValueError):
            server.parse_intake({'content':json.dumps(obj)})

    def test_malformed_uploads_rejected(self):
        for data in [{'content':'{wrong','filename':'ticket.json'}, {'content':'text','filename':'ticket.pdf'}, {'content':' '}, {'content':'{"title": 42}'}, {'content':'{"customer": "Beacon Retail"}'}]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                server.parse_intake(data)

    def test_resolved_requires_real_booleans_and_confirmation(self):
        case = self.new_case()
        for data in [dict(tested=False,customer_confirmed=True),dict(tested=True,customer_confirmed=False),dict(tested='false',customer_confirmed='true')]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                server.update_investigation(case,'outcome',dict(status='Resolved',notes='Done',alternative_solution='Manual fix',**data))

    def test_change_requires_all_stages(self):
        case = self.new_case('Change request')
        outcome = dict(status='Resolved',notes='Documented change',alternative_solution='Approved threshold update',tested=True,customer_confirmed=True)
        with self.assertRaises(ValueError):
            server.update_investigation(case,'outcome',outcome)
        outcome.update(approved=True,developed=True,deployed=True,verified=True)
        self.assertEqual(server.update_investigation(case,'outcome',outcome)['status'],'Resolved')

    def test_selection_must_reference_retrieved_evidence(self):
        case = self.new_case()
        with self.assertRaises(ValueError):
            server.update_investigation(case,'decision',dict(source_id='PRIVATE-900',decision='Accepted'))

    def test_new_evidence_invalidates_old_recommendations(self):
        case = server.update_investigation(self.new_case(),'analyze',{})
        case = server.update_investigation(case,'decision',dict(source_id=case['analysis']['results'][0]['source_id'],decision='Accepted'))
        case = server.update_investigation(case,'note',dict(kind='Test',text='Different cause observed in QA.'))
        self.assertIsNone(case['analysis'])
        self.assertIsNone(case['selected_source'])

    def test_workaround_can_be_recorded_without_claiming_resolution(self):
        case = server.update_investigation(self.new_case(),'outcome',dict(status='Workaround',notes='Temporary relief only.',alternative_solution='Approved manual processing'))
        self.assertEqual(case['status'],'Workaround')
        self.assertFalse(case['outcome']['tested'])

    def test_recorded_outcome_cannot_be_silently_overwritten(self):
        case = server.update_investigation(self.new_case(),'outcome',dict(status='Unresolved',notes='Escalation needed'))
        for action,data in [('outcome',dict(status='Resolved',notes='Changed')),('analyze',{}),('decision',dict(source_id='INC-18372',decision='Accepted'))]:
            with self.assertRaises(ValueError):
                server.update_investigation(case,action,data)


class HttpTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        self.service = server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread = threading.Thread(target=self.service.serve_forever,daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.service.server_port}'

    def tearDown(self):
        self.service.shutdown()
        self.service.server_close()
        self.thread.join()
        super().tearDown()

    def test_http_state_and_static_page(self):
        with urlopen(self.url+'/api/state') as res:
            body = res.read().decode()
            self.assertNotIn('OTHER_CUSTOMER_SECRET',body)
            self.assertNotIn('PRIVATE-900',body)
        with urlopen(self.url) as res:
            self.assertEqual(res.status,200)
            self.assertIn("frame-ancestors 'none'",res.headers['Content-Security-Policy'])

    def test_http_rejects_cross_origin_and_unauthorized_id(self):
        req = Request(self.url+'/api/investigations',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://example.com'})
        with self.assertRaises(HTTPError) as err:
            urlopen(req)
        self.assertEqual(err.exception.code,403)
        req = Request(self.url+'/api/investigations/PRIVATE-900/analyze',data=b'{}',headers={'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as err:
            urlopen(req)
        self.assertEqual(err.exception.code,404)

    def test_http_rejects_invalid_content_type(self):
        req = Request(self.url+'/api/intake',data=b'{}',headers={'Content-Type':'text/plain'})
        with self.assertRaises(HTTPError) as err:
            urlopen(req)
        self.assertEqual(err.exception.code,415)


if __name__ == '__main__':
    unittest.main()
