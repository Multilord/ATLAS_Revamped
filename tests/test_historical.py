import base64
import copy
import io
from openpyxl import Workbook
from test_system import StoreCase, source_data, response
from ingestion import create_source
from historical import preview, prepare_import, import_documents, search, attach, permitted, index_estimate
from historical_demo import install_library
from storage import ConflictError
from engine import rank_candidates, retrieve


class HistoricalTests(StoreCase):
    def upload(self, name, raw):
        return preview(dict(filename=name, file_base64=base64.b64encode(raw).decode()))

    def payload(self, **changes):
        defaults=dict(title='Historical investigation', application='Test App', customer=self.cfg.customer,
            source_type='Investigation report', evidence_quality='Unresolved findings')
        defaults.update(changes)
        return dict(defaults=defaults, content='The connection failed. Restarting did not establish a cause.', filename='case.txt')

    def test_csv_mapping_preserves_all_columns_and_does_not_call_ai(self):
        p=self.upload('history.csv',b'ticket_id,title,problem_statement,module,resolution,closed\nOLD-1,Connection failure,Timeout,FI,Restart failed,12/31/2025\n')
        data=dict(rows=p['rows'],mapping=p['mapping'],defaults={'customer':self.cfg.customer,'source_type':'Historical ticket'},date_format='MM/DD/YYYY',filename='history.csv')
        result=import_documents(data,self.store)
        source=self.store.get(result['saved'][0],'source')
        self.assertIn('resolution: Restart failed',source['content'])
        self.assertEqual(source['source_updated_at'][:10],'2025-12-31')
        self.assertEqual(source['source_reference'],'OLD-1')
        self.assertEqual(source['validation'],'Unverified')
        self.assertEqual(source['index_status'],'Pending')
        self.assertEqual(import_documents(data,self.store)['duplicates'],result['saved'])
        self.ai.embed.assert_not_called()

    def test_workbook_sheet_selection_and_dates(self):
        book=Workbook();book.active.title='First';book.active.append(['title','content']);book.active.append(['One','First case'])
        sheet=book.create_sheet('Second');sheet.append(['title','content']);sheet.append(['Two','Second case'])
        raw=io.BytesIO();book.save(raw)
        data=dict(filename='case.xlsx',file_base64=base64.b64encode(raw.getvalue()).decode(),sheet='Second')
        p=preview(data)
        self.assertEqual(p['rows'][0]['title'],'Two')
        self.assertEqual(p['sheets'],['First','Second'])

    def test_bad_mapping_or_row_rejects_entire_batch(self):
        data=dict(rows=[dict(title='Valid',content='Symptoms'),dict(title='',content='Symptoms')],mapping=dict(title='title',content='content'),defaults=dict(application='Test App',customer=self.cfg.customer))
        with self.assertRaises(ValueError):import_documents(data,self.store)
        self.assertEqual(self.store.records('source'),[])
        with self.assertRaises(ValueError):self.upload('bad.csv',b'title,title\nA,B\n')

    def test_review_and_verified_require_evidence(self):
        with self.assertRaises(ValueError):import_documents(self.payload(evidence_quality='Verified fix'),self.store)
        data=self.payload(evidence_quality='Verified fix',tested=True,customer_confirmed=True,deployed=True,review_notes='Test and approval references')
        source=prepare_import(data,self.store)[0]
        self.assertEqual(source['validation'],'Verified')
        data['defaults']['synthetic']=True
        source=prepare_import(data,self.store)[0]
        self.assertEqual(source['validation'],'Reviewed')
        self.assertEqual(source['simulated_quality'],'Verified fix')

    def test_general_and_customer_scope_validation(self):
        with self.assertRaises(ValueError):import_documents(self.payload(customer='General'),self.store)
        with self.assertRaises(ValueError):import_documents(self.payload(customer='Other'),self.store)
        data=self.payload(customer='General',generalized_confirmed=True)
        source=prepare_import(data,self.store)[0]
        self.assertTrue(permitted(source,dict(customer=self.cfg.customer)))

    def test_plain_source_creation_now_defers_indexing(self):
        data=source_data();data.pop('index_now')
        source=create_source(data,self.store,self.ai)
        self.assertEqual(source['index_status'],'Pending')
        self.ai.embed.assert_not_called()
        self.assertEqual(index_estimate(source,self.cfg.embedding_model)['requests'],1)

    def test_search_pending_and_link_without_choosing_fix(self):
        ids=import_documents(self.payload(),self.store)['saved'];t=self.ticket()
        t['analysis']={'summary':'Old analysis'}
        results=search(t,{'query':'connection'},self.store)['results']
        self.assertEqual(results[0]['source_id'],ids[0])
        self.assertEqual(results[0]['evidence_quality'],'Unresolved findings')
        attach(t,dict(source_id=ids[0],quote='Restarting did not establish a cause.',reason='Same symptom, cause unknown',revision=t['revision']),self.store,'Tester')
        self.assertEqual(t['lifecycle_stage'],'Ticket Creation')
        self.assertIsNone(t['selected_source'])
        self.assertIsNone(t['analysis'])
        self.assertEqual(t['timeline'][-1]['kind'],'Attachment')
        self.ai.embed.assert_not_called()

    def test_link_rejects_cross_scope_fabricated_quote_and_stale_revision(self):
        source=prepare_import(self.payload(),self.store)[0];self.store.save(source,'source');t=self.ticket()
        with self.assertRaises(ConflictError):attach(t,dict(source_id=source['id'],revision=-1,reason='Test'),self.store,'Tester')
        with self.assertRaises(ValueError):attach(t,dict(source_id=source['id'],revision=t['revision'],reason='Test',quote='Invented quote'),self.store,'Tester')
        self.store.db.sources.update_one({'id':source['id']},{'$set':{'customer':'Other'}})
        with self.assertRaises(ValueError):attach(t,dict(source_id=source['id'],revision=t['revision'],reason='Test'),self.store,'Tester')

    def test_synthetic_library_repeatable_and_excluded_from_real_tickets(self):
        r=install_library(self.store);self.assertEqual(len(r['saved']),16)
        self.assertEqual(install_library(self.store)['existing'],16)
        t=self.ticket()
        self.assertEqual(search(t,{'query':'batch'},self.store)['results'],[])
        t['data_origin']='Synthetic demo'
        self.assertGreater(len(search(t,{'query':'batch'},self.store)['results']),0)
        for s in self.store.records('source'):
            self.assertEqual(s['index_status'],'Pending')
            self.assertNotEqual(s['validation'],'Verified')

    def test_synthetic_exclusion_and_unresolved_quality_in_ai_results(self):
        s=self.source()
        self.store.db.sources.update_one({'id':s['id']},{'$set':{'synthetic':True}})
        t=self.ticket()
        self.assertEqual(rank_candidates(t,self.store,self.ai,query_vector=[1.,0.,0.])[0],[])
        self.store.db.sources.update_one({'id':s['id']},{'$set':{'synthetic':False,'evidence_quality':'Unresolved findings'}})
        self.ai.investigate.return_value=response([self.recommendation(s)])
        result=retrieve(t,self.store,self.ai)
        self.assertEqual(result['results'][0]['label'],'Investigation findings')
        self.assertEqual(result['results'][0]['confidence'],'Low')
