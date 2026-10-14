"""Isolated test fixtures only. No test documents are loaded by the application."""
import base64
import copy
import io
import json
import os
import threading
import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import Mock, patch

import httpx
import mongomock
from openai import OpenAI
from docx import Document
from pypdf import PdfWriter
import server
from config import Settings
from storage import MongoStore, ConflictError
from ai import AIService, AIError, InvestigationResponse
from engine import retrieve
from ingestion import create_source, extract_upload, chunks, index_source


def config(**changes):
    return replace(Settings(), customer='Test Customer', database='atlas_test_unit', api_key='', **changes)


def response(recommendations=None):
    return InvestigationResponse(classification='Unknown', summary='Review the supplied evidence.', recommendations=recommendations or [], next_steps=['Confirm the release and reproduce the issue in quality.'])


def source_data():
    return dict(title='Test maintenance procedure', content='Inspect the connection configuration and validate the correction in quality.', application='Test App', version='1.0', source_type='Internal KB')


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.cfg = config()
        self.store = MongoStore(self.cfg, client=mongomock.MongoClient())
        self.store.initialize()
        self.ai = Mock()
        self.ai.config = self.cfg
        self.ai.embed.side_effect = lambda texts: [[1., 0., 0.] for _ in texts]
        self.ai.investigate.return_value = response()
        self.old_store, self.old_ai, self.old_customer = server.store, server.ai, server.CUSTOMER
        server.store, server.ai, server.CUSTOMER = self.store, self.ai, self.cfg.customer

    def tearDown(self):
        server.store, server.ai, server.CUSTOMER = self.old_store, self.old_ai, self.old_customer
        self.store.close()

    def ticket(self, kind='Incident'):
        return server.create_investigation(dict(title='Connection problem',description='Inspect connection configuration',application='Test App',version='1.0',type=kind,priority='Medium'))

    def source(self):
        return create_source(source_data(),self.store,self.ai)

    def recommendation(self, source):
        return dict(source_id=source['id'],chunk_id='C0001',quote=source['content'],title='Validate the connection',reason='The supplied procedure describes the symptom.',steps=['Inspect the connection configuration in quality.'],warnings=[],confidence='High',kind='Likely solution')


class DatabaseTests(StoreCase):
    def test_database_starts_empty_and_initialize_never_seeds(self):
        self.assertEqual(self.store.records('investigation'),[])
        self.assertEqual(self.store.records('source'),[])
        self.store.initialize()
        self.assertEqual(self.store.records('source'),[])

    def test_scoped_reads_and_writes(self):
        self.store.db.sources.insert_one(dict(id='private',customer='Other Customer',content='secret',index_status='Ready',embedding_model=self.cfg.embedding_model,chunks=[{'id':'C1','text':'secret','embedding':[1,0,0]}]))
        self.assertIsNone(self.store.get('private','source'))
        self.assertEqual(list(self.store.indexed_chunks(self.cfg.embedding_model)),[])
        with self.assertRaises(ValueError):
            self.store.save(dict(id='bad',customer='Other Customer'))

    def test_concurrent_edits_conflict_instead_of_overwriting(self):
        ticket=self.ticket()
        left=self.store.get(ticket['id'],'investigation')
        right=copy.deepcopy(left)
        left['status']='In progress'
        self.store.save(left)
        with self.assertRaises(ConflictError):
            self.store.save(right)

    def test_vectors_never_sent_to_ui(self):
        source=self.source()
        self.assertEqual(source['index_status'],'Ready')
        self.assertNotIn('chunks',self.store.records('source')[0])
        self.assertTrue(self.store.get(source['id'],'source',True)['chunks'])

    def test_duplicate_documents_rejected(self):
        self.source()
        with self.assertRaises(ConflictError):
            self.source()

    def test_model_change_requires_reindex(self):
        self.source()
        self.assertEqual(list(self.store.indexed_chunks('different-model')),[])


class AIGroundingTests(StoreCase):
    def test_analysis_uses_actual_ai_result_and_quote(self):
        source=self.source()
        self.ai.investigate.return_value=response([self.recommendation(source)])
        result=retrieve(self.ticket(),self.store,self.ai)
        self.assertEqual(result['results'][0]['quote'],source['content'])
        self.assertEqual(result['results'][0]['confidence'],'Medium')
        self.assertEqual(result['results'][0]['label'],'Likely solution')

    def test_fabricated_citation_rejected(self):
        source=self.source()
        rec=self.recommendation(source)
        rec['source_id']='invented'
        self.ai.investigate.return_value=response([rec])
        with self.assertRaises(AIError):
            retrieve(self.ticket(),self.store,self.ai)

    def test_fabricated_quote_rejected(self):
        source=self.source()
        rec=self.recommendation(source)
        rec['quote']='A fabricated supporting excerpt.'
        self.ai.investigate.return_value=response([rec])
        with self.assertRaises(AIError):
            retrieve(self.ticket(),self.store,self.ai)

    def test_empty_corpus_returns_no_fake_recommendations(self):
        result=retrieve(self.ticket(),self.store,self.ai)
        self.assertEqual(result['state'],'Insufficient evidence')
        self.assertEqual(result['results'],[])
        self.assertEqual(self.ai.investigate.call_args.args[1],[])

    def test_version_mismatch_cannot_be_high_confidence(self):
        source=self.source()
        self.ai.investigate.return_value=response([self.recommendation(source)])
        ticket=self.ticket()
        ticket['version']='2.0'
        result=retrieve(ticket,self.store,self.ai)
        self.assertEqual(result['results'][0]['confidence'],'Low')
        self.assertEqual(result['state'],'Insufficient evidence')

    def test_indexing_failure_preserves_real_document_for_retry(self):
        self.ai.embed.side_effect=AIError('API key missing')
        source=self.source()
        self.assertEqual(source['index_status'],'Error')
        self.assertEqual(self.store.get(source['id'],'source')['content'],source_data()['content'])
        self.assertEqual(list(self.store.indexed_chunks(self.cfg.embedding_model)),[])
        self.ai.embed.side_effect=lambda texts:[[1.,0.,0.] for _ in texts]
        updated=index_source(self.store.get(source['id'],'source',True),self.store,self.ai)
        self.assertEqual(updated['index_status'],'Ready')

    def test_failed_ai_analysis_does_not_save_fake_success(self):
        ticket=self.ticket()
        self.ai.investigate.side_effect=AIError('Provider failed')
        with self.assertRaises(AIError):
            server.update_investigation(ticket,'analyze',{})
        self.assertIsNone(self.store.get(ticket['id'],'investigation')['analysis'])


class WorkflowTests(StoreCase):
    def test_full_workflow_persistence(self):
        source=self.source()
        self.ai.investigate.return_value=response([self.recommendation(source)])
        ticket=server.update_investigation(self.ticket(),'analyze',{})
        ticket=server.update_investigation(ticket,'decision',dict(source_id=source['id'],decision='Accepted'))
        ticket=server.update_investigation(ticket,'outcome',dict(status='Resolved',notes='Validated against quality test record.',tested=True,customer_confirmed=True))
        stored=self.store.get(ticket['id'],'investigation')
        self.assertEqual(stored['status'],'Resolved')
        self.assertEqual(len(stored['timeline']),4)

    def test_invalid_resolution_validation(self):
        for flags in [dict(tested=False,customer_confirmed=True),dict(tested='yes',customer_confirmed=True)]:
            with self.subTest(flags=flags),self.assertRaises(ValueError):
                server.update_investigation(self.ticket(),'outcome',dict(status='Resolved',notes='Reviewed',alternative_solution='Procedure',**flags))

    def test_change_request_requires_change_stages(self):
        with self.assertRaises(ValueError):
            server.update_investigation(self.ticket('Change request'),'outcome',dict(status='Resolved',notes='Reviewed',tested=True,customer_confirmed=True,alternative_solution='Procedure'))

    def test_new_evidence_invalidates_recommendations(self):
        ticket=server.update_investigation(self.ticket(),'analyze',{})
        ticket=server.update_investigation(ticket,'note',dict(kind='Test',text='A different result was observed.'))
        self.assertIsNone(ticket['analysis'])

    def test_imported_chronology_is_preserved(self):
        data=dict(title='Actual ticket',description='Details',timeline=[dict(at='2026-10-14T10:00:00+08:00',text='Later'),dict(at='2026-10-14T00:00:00Z',text='Earlier')])
        result=server.parse_intake(dict(content=json.dumps(data)),use_ai=True)
        self.assertEqual([e['text'] for e in result['timeline']],['Earlier','Later'])
        self.ai.extract.assert_not_called()

    def test_unstructured_intake_calls_ai(self):
        self.ai.extract.return_value=dict(title='Extracted title',description='Reported issue',timeline=[])
        parsed=server.parse_intake(dict(content='Unstructured original ticket'),use_ai=True)
        self.ai.extract.assert_called_once_with('Unstructured original ticket')
        self.assertEqual(parsed['title'],'Extracted title')

    def test_other_customer_intake_rejected(self):
        with self.assertRaises(ValueError):
            server.parse_intake(dict(content=json.dumps({'customer':'Other Customer'})))


class FileTests(unittest.TestCase):
    def upload(self,name,content):
        return extract_upload(dict(filename=name,file_base64=base64.b64encode(content).decode()))

    def test_utf8_and_docx_extraction(self):
        self.assertEqual(self.upload('ticket.txt','Invoice café'.encode())['content'],'Invoice café')
        doc=Document()
        doc.add_paragraph('Observed application error')
        data=io.BytesIO()
        doc.save(data)
        self.assertIn('Observed application error',self.upload('source.docx',data.getvalue())['content'])

    def test_scanned_or_blank_pdf_explicitly_rejected(self):
        writer=PdfWriter()
        writer.add_blank_page(width=200,height=200)
        data=io.BytesIO()
        writer.write(data)
        with self.assertRaisesRegex(ValueError,'OCR'):
            self.upload('blank.pdf',data.getvalue())

    def test_bad_and_unsupported_uploads(self):
        for name,data in [('bad.json',b'{broken'),('script.exe',b'content'),('empty.txt',b'')]:
            with self.subTest(name=name),self.assertRaises(ValueError):
                self.upload(name,data)

    def test_chunk_coverage_and_boundaries(self):
        text='word ' * 1400
        parts=chunks(text)
        self.assertGreater(len(parts),1)
        self.assertTrue(all(p['text'] in text and len(p['text'])<=2200 for p in parts))
        self.assertTrue(text.rstrip().endswith(parts[-1]['text']))


class ProviderTests(unittest.TestCase):
    def test_missing_key_is_explicit(self):
        with self.assertRaisesRegex(AIError,'OPENAI_API_KEY'):
            AIService(config()).embed(['text'])

    def test_responses_and_embeddings_wire_contract(self):
        requests=[]
        def transport(request):
            body=json.loads(request.content)
            requests.append((request.url.path,body))
            if request.url.path.endswith('/embeddings'):
                return httpx.Response(200,json={'object':'list','data':[{'object':'embedding','index':0,'embedding':[1.,0.,0.]}],'model':'text-embedding-3-small','usage':{'prompt_tokens':1,'total_tokens':1}})
            return httpx.Response(200,json={'id':'resp_test','object':'response','created_at':1,'status':'completed','model':'gpt-4.1-mini','output':[{'id':'msg_test','type':'message','status':'completed','role':'assistant','content':[{'type':'output_text','text':response().model_dump_json(),'annotations':[]}]}]})
        cfg=replace(config(),api_key='test-key-not-real')
        client=OpenAI(api_key=cfg.api_key,http_client=httpx.Client(transport=httpx.MockTransport(transport)))
        ai=AIService(cfg,client)
        self.assertEqual(ai.embed(['ticket']),[[1.,0.,0.]])
        self.assertEqual(ai.investigate({'title':'Ticket'},[]).recommendations,[])
        self.assertFalse(requests[1][1]['store'])
        self.assertEqual(requests[1][1]['text']['format']['type'],'json_schema')
        client.close()

    def test_auth_error_never_exposes_key_or_provider_body(self):
        cfg=replace(config(),api_key='secret-test-key')
        client=OpenAI(api_key=cfg.api_key,http_client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(401,json={'error':{'message':'secret-test-key','type':'invalid_request_error','code':'invalid_api_key'}}))))
        with self.assertRaises(AIError) as caught:
            AIService(cfg,client).embed(['text'])
        self.assertNotIn('secret-test-key',str(caught.exception))
        client.close()


class HttpTests(StoreCase):
    def setUp(self):
        super().setUp()
        server.ai=AIService(self.cfg)
        self.service=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.service.serve_forever,daemon=True)
        self.thread.start()
        self.url=f'http://127.0.0.1:{self.service.server_port}'

    def tearDown(self):
        self.service.shutdown()
        self.service.server_close()
        self.thread.join()
        super().tearDown()

    def test_state_empty_and_no_credentials_exposed(self):
        with urlopen(self.url+'/api/state') as res:
            state=json.load(res)
        self.assertEqual(state['investigations'],[])
        self.assertEqual(state['sources'],[])
        self.assertNotIn('mongo_uri',json.dumps(state))
        self.assertEqual(state['services']['ai'],'API key missing')

    def test_ai_without_key_returns_actionable_failure(self):
        request=Request(self.url+'/api/ai/check',data=b'{}',headers={'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code,502)
        self.assertIn('OPENAI_API_KEY',caught.exception.read().decode())

    def test_cross_origin_rejected(self):
        request=Request(self.url+'/api/sources',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://example.com'})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code,403)


@unittest.skipUnless(os.getenv('RUN_MONGO_TESTS')=='1','Set RUN_MONGO_TESTS=1 to test a real MongoDB instance.')
class RealMongoTests(unittest.TestCase):
    def test_real_persistence_and_empty_initial_state(self):
        name='atlas_test_'+uuid.uuid4().hex
        cfg=replace(config(),database=name)
        store=MongoStore(cfg)
        try:
            store.initialize()
            self.assertEqual(store.records('source'),[])
            item=dict(id='integration-record',customer=cfg.customer,updated_at=datetime.now(timezone.utc).isoformat(),timeline=[],status='New')
            store.save(item)
            reopened=MongoStore(cfg)
            try:
                self.assertEqual(reopened.get(item['id'],'investigation')['status'],'New')
            finally:
                reopened.close()
        finally:
            assert name.startswith('atlas_test_') and name!=Settings().database
            store.client.drop_database(name)
            store.close()


if __name__=='__main__':
    unittest.main()
