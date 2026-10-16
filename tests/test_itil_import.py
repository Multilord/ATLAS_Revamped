"""Client importer checks use isolated fixtures, never client content."""
import csv
import tempfile
import unittest
from pathlib import Path
import mongomock
from config import Settings
from storage import MongoStore
from scripts.seed_tickets import REQUIRED, build_records, load_rows, replace_records


def fixture(**changes):
    row = dict.fromkeys(REQUIRED, '')
    row.update(ticket_id='CLIENT-001', ticket_type='Change Request', customer='Customer A',
        platform='ECC', release='6.0', module='PP', component='LO-BM', title='Batch requirement',
        problem_statement='Batch proposals require a vendor rule.', resolution_quality='Verified solution',
        status='Closed', priority='High', created='3/10/2025', closed='4/13/2025',
        resolution='Configured the selection strategy.', verification='Tested in QA.',
        visibility='customer_only', clarification='Confirmed scope', functional_solutioning='Configuration',
        technical_solutioning='No code', change_stages='Approved and transported', lifecycle_path='Creation > Closure')
    row.update(changes)
    return row


class ImportTests(unittest.TestCase):
    def test_full_structure_preserved_without_invented_validation(self):
        row=fixture()
        inv, source=build_records(row,'client.csv')
        self.assertEqual(inv['type'],'Change request')
        self.assertEqual(inv['created_at'][:10],'2025-03-10')
        self.assertEqual(inv['import_info']['original'],row)
        self.assertEqual(inv['itil']['functional_solutioning'],'Configuration')
        self.assertFalse(inv['outcome']['customer_confirmed'])
        self.assertFalse(inv['outcome']['deployed'])
        self.assertEqual(source['validation'],'Reviewed')
        self.assertEqual(source['customer'],'Customer A')
        self.assertTrue(all(e['date_known'] is False for e in inv['timeline'][1:-1]))

    def test_workaround_and_unverified_closures(self):
        inv, source=build_records(fixture(resolution_quality='Workaround only'),'client.csv')
        self.assertEqual(inv['status'],'Workaround')
        self.assertEqual(source['solution_kind'],'Workaround')
        inv, source=build_records(fixture(resolution_quality='Unverified'),'client.csv')
        self.assertEqual(inv['status'],'Closed - other')
        self.assertEqual(source['validation'],'Unverified')

    def test_shared_visibility_and_stable_hash(self):
        row=fixture(visibility='shared_generalized')
        _, source=build_records(row,'client.csv')
        self.assertEqual(source['customer'],'General')
        self.assertEqual(source['content_hash'],build_records(row,'client.csv')[1]['content_hash'])

    def test_replacement_removes_only_previous_seed_and_is_repeatable(self):
        store=MongoStore(Settings(),client=mongomock.MongoClient())
        store.db.sources.insert_many([{'id':'SYN-H001'}, {'id':'real-source'}])
        store.db.investigations.insert_many([{'id':'INV-SYN-Q01'}, {'id':'real-case'},
            {'id':'manually-created-test', 'ticket_id':'SYN-H001'}])
        with tempfile.TemporaryDirectory() as directory:
            records=[build_records(fixture(),'client.csv')]
            backup, counts=replace_records(store,records,directory)
            self.assertTrue(backup.exists())
            self.assertEqual(counts,{'sources':1,'investigations':2})
            replace_records(store,records,directory)
            self.assertEqual(store.db.sources.count_documents({}),2)
            self.assertIsNotNone(store.db.investigations.find_one({'id':'real-case'}))
            self.assertIsNone(store.db.investigations.find_one({'id':'INV-SYN-Q01'}))
            self.assertIsNone(store.db.investigations.find_one({'id':'manually-created-test'}))
        store.close()

    def test_duplicate_input_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'client.csv'
            with path.open('w',newline='',encoding='utf-8') as stream:
                writer=csv.DictWriter(stream,fieldnames=fixture().keys())
                writer.writeheader()
                writer.writerows([fixture(),fixture()])
            with self.assertRaisesRegex(ValueError,'unique'):
                load_rows(path)
