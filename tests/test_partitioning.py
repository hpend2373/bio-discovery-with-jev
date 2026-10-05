import json,tempfile,unittest
from copy import deepcopy
from pathlib import Path
from bio_topics.partitioning import atoms,make_pages,restore_pages
from bio_topics.util import canonical
from bio_topics.runtime import create_plan,run,verify
from bio_topics.ingest import read_table
from bio_topics.ledger import linkage_audit
from test_engine import TestBackend,ROOT

class PartitionTests(unittest.TestCase):
    def checker(self,state):
        size=len(canonical(state).encode())
        if size>4300:raise ValueError('Full evidence exceeds token budget: '+str(size))
        return {'ok':True,'bytes':size}

    def parent(self):
        return {'id':'u','kind':'cell','scope':{'clinical_question_id':'q'},'record_ids':['r'],
                'state':{'research_question':'Why?', 'domain':'meta','payload':{'null':None,'empty':[], 'dict':{}, 'ko':'연구 증거 '+('가나다😀'*3500),'opposite':[-1,0,1]},'limits':['No imputation']}}

    def test_all_typed_values_and_unicode_fragments_preserved(self):
        parent=self.parent();pages,spec=make_pages(parent,self.checker)
        self.assertGreater(len(pages),1)
        self.assertEqual([a for p in pages for a in p['state']['evidence_entries']],list(atoms(parent['state'])))
        pieces=[a for p in pages for a in p['state']['evidence_entries'] if a['path']==['payload','ko']]
        self.assertEqual(''.join(a['text'] for a in pieces),parent['state']['payload']['ko'])
        self.assertEqual(restore_pages(parent,spec),pages)
        for p in pages:self.checker(p['state'])

    def test_missing_reordered_or_modified_parts_rejected(self):
        parent=self.parent();_,spec=make_pages(parent,self.checker)
        for mutation in ['drop','overlap','change']:
            bad=deepcopy(spec)
            if mutation=='drop':bad['ranges'].pop()
            elif mutation=='overlap':bad['ranges'][1][0]-=1
            else:bad['entries_hash']='wrong'
            with self.assertRaises(ValueError):restore_pages(parent,bad)

    def test_joint_pair_endpoints_on_every_page(self):
        p=self.parent();p['kind']='pair';p['state']['records']=[{'id':'a','fields':{'value':0.5,'model':'adjusted'}},{'id':'b','fields':{'value':1.5,'model':'crude'}}]
        pages,_=make_pages(p,self.checker)
        for pg in pages:
            self.assertEqual([r['id'] for r in pg['state']['joint_pair_context']['rows']],['a','b'])
        p['state']['records'][0]['fields']['unbounded']='a'*10000
        with self.assertRaisesRegex(ValueError,'indivisible'):make_pages(p,self.checker)

    def test_partition_runtime_resume_and_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);p={
                'schema_version':1,'domain':'deg','question':'test','columns':{'entity_id':'gene','comparison':'contrast'},
                'inspection':{'pairs':'none','cell_fields':['comparison'],'partition_long_evidence':True}}
            (d/'profile.json').write_text(json.dumps(p));(d/'input.csv').write_text('gene,contrast,note\nA,x,'+'text '*4000+'\n')
            plan=create_plan(d/'input.csv',d/'profile.json',d/'run',context_checker=self.checker)
            self.assertGreater(plan['unit_count'],plan['logical_unit_count'])
            result=run(d/'run',backend=TestBackend(fail_at=2))
            self.assertEqual(result['counts']['failed'],8)
            result=run(d/'run',backend=TestBackend(),retry_failed=True)
            self.assertEqual(result['counts']['pending'],0)
            self.assertEqual(result['counts']['failed'],0)
            self.assertIn('simulated_backend_not_scientific_coverage',result['errors'])

class LedgerLinkTests(unittest.TestCase):
    def test_exact_effect_join_numeric_fill_and_coverage_requirements(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'rows.csv';source.write_text('id,measure,value,adjusted\nE1,HR,,adjusted\nE2,HR,0.9,crude\n')
            p={'domain':'meta','columns':{'source_effect_id':'id','measure':'measure','value':'value','effect_adjusted':'adjusted'},
               'clinical':{'ledger':{'effects':[{'id':'E1','confirmed':True,'source_reference':'ledger:row2','fields':{'value':1.2,'population':'adults','treatment_stage':'after_surgery','publication_id':'P1'}},
                                              {'id':'E3','confirmed':True,'source_reference':'ledger:row3','fields':{'value':2}}]}}}
            records,_=read_table(source,p);self.assertEqual(records[0]['fields']['value'],1.2);self.assertEqual(records[0]['raw']['value'],'')
            self.assertEqual([r['fields']['effect_adjusted'] for r in records],[True,False])
            audit=linkage_audit(records,p);self.assertEqual(audit['coverage']['effects']['confirmed_links'],1);self.assertEqual(audit['unused_ledger_entries'][0]['id'],'E3')
            p['clinical']['ledger_requirements']={'effects':'all_input_rows'}
            with self.assertRaisesRegex(ValueError,'incomplete'):linkage_audit(records,p)
            p['clinical']['ledger']['effects'].append({'id':'E2','confirmed':True,'source_reference':'ledger:row4','fields':{'value':1.1}})
            records,_=read_table(source,p)
            self.assertIsNone(records[1]['fields']['value'])
            with self.assertRaisesRegex(ValueError,'conflicted'):linkage_audit(records,p)

    def test_full_ledger_file_can_supply_missing_effect_columns(self):
        from bio_topics.ledger_import import prepare_effect_ledger
        from bio_topics.ingest import read_profile
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            (d/'input.csv').write_text('effect_row_id\nE1\nE2\n')
            (d/'ledger.csv').write_text('effect_row_id,rec_id,effect_measure,effect_point,ci_level,effect_adjusted\nE1,P1,HR,0.8,95,adjusted\nE2,P2,HR,1.2,95,crude\n')
            (d/'profile.json').write_text(json.dumps({'schema_version':1,'domain':'meta','question':'test','columns':{'source_effect_id':'effect_row_id'},'transforms':{'ci_level':'percent_to_fraction'},'inspection':{'pairs':'none','cell_fields':['clinical_question_id']}}))
            result=prepare_effect_ledger(d/'input.csv',d/'profile.json',d/'ledger.csv',d/'linked',ci_level_percent=True)
            p=read_profile(result['profile']);r,_=read_table(d/'input.csv',p)
            self.assertEqual([x['fields']['value'] for x in r],[0.8,1.2])
            self.assertEqual([x['fields']['ci_level'] for x in r],[0.95,0.95])
            self.assertEqual(result['coverage']['effects']['confirmed_links'],2)
            self.assertEqual(r[0]['raw'],{'effect_row_id':'E1'})
            self.assertNotIn('source_verification_status',r[0]['fields'])

    def test_qualifiers_do_not_overwrite_conflicting_ledger_values(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'x.csv';path.write_text('study,measure,value,timing\nS1,HR,1.1,postdiagnostic 1y lag\n')
            p={'domain':'meta','columns':{'study_id':'study','measure':'measure','value':'value','exposure_timing':'timing'},
               'clinical':{'normalization':{'exposure_timing':[{'canonical':'postdiagnostic','aliases':['postdiagnostic 1y lag'],
                   'assign':{'lag':'1 years'},'confirmed':True,'source_reference':'explicit source string'}]}}}
            r,_=read_table(path,p)
            self.assertEqual(r[0]['fields']['lag'],'1 years');self.assertEqual(r[0]['fields']['exposure_timing'],'postdiagnostic')
            self.assertEqual(r[0]['raw']['timing'],'postdiagnostic 1y lag')
            p['declarations']={'lag':'2 years'};r,_=read_table(path,p)
            self.assertIsNone(r[0]['fields']['lag']);self.assertIn('lag',r[0]['clinical']['conflicts'])
