import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from bio_topics import cellchat as cc
from bio_topics.util import digest, canonical

HEAD = ['source','target','interaction_name','ligand','receptor','prob','pval','condition','patient_id']
ROWS = [['KC','CD4','A_B','A','B_complex','0.1','0.01','before','P1'],
        ['KC','CD4','A_B','A','B_complex','0','1','after','P1'],
        ['CD4','KC','A_B','A','B_complex','0.2','','before','P2']]
PROFILE = {'study_id':'synthetic', 'question':'Which follow-ups?', 'context':{'dataset_id':'D'},'backend':{'kind':'laya'}}

class Guard:
    def check(self, state, questions, *args):
        return {'ok':True,'question_lengths':{q:10 for q in questions},'expected_input_tokens':10*len(questions)}
class Backend:
    kind='laya'; simulated=True; max_len=8192; head_max_len=384; guard=Guard()
    identity={'kind':'laya','model':'synthetic','max_len':8192,'head_max_len':384}
    def evaluate(self,state,questions):
        body={'state':state,'questions':questions,'model':'synthetic','max_len':8192,'head_max_len':384}
        return {'provider_identity':self.identity, 'request_hash':digest(body),'context_receipt':self.guard.check(state,questions),
                'payload':{'model':'synthetic','usage':{'input_tokens':10*len(questions)},'answers':{q:{'type':'choice','choice':'followup','probabilities':{'followup':.8,'background':.1,'needs_data':.1}} for q in questions}}}

class CellChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name); self.addCleanup(self.tmp.cleanup)
        self.input=self.root/'edges.csv';self.profile=self.root/'profile.json';self.profile.write_text(json.dumps(PROFILE))
        self.write(ROWS)
    def write(self,rows,head=HEAD):
        with self.input.open('w',newline='') as f:
            w=csv.writer(f);w.writerow(head);w.writerows(rows)
    def test_all_rows_zero_missing_and_direction_preserved(self):
        rows,src=cc.read_sources(self.input,PROFILE); units=cc.make_units(rows,PROFILE)
        self.assertEqual(len(rows),3);self.assertEqual(len(units),2)
        self.assertEqual(rows[1]['parsed']['prob'],0);self.assertIsNone(rows[2]['parsed']['pval'])
        self.assertEqual(rows[0]['raw']['receptor'],'B_complex')
        self.assertEqual(sum(len(u['state']['records']) for u in units),3)
        self.assertTrue(all(len(u['questions'])==1 for u in units))
    def test_comparison_requires_declared_compatibility_and_keeps_repeated_patient(self):
        p=copy.deepcopy(PROFILE);p['context']['analysis_group']='same-settings-reviewed'
        rows,_=cc.read_sources(self.input,p); units=cc.make_units(rows,p)
        u=next(u for u in units if len(u['state']['records'])==2)
        self.assertIn('condition_comparison',u['questions']);self.assertEqual(u['state']['facts']['identified_patient_ids'],['P1'])
        self.assertEqual(u['state']['facts']['independent_patient_replication'],'not_established')
    def test_invalid_values_and_missing_identity_remain_inspectable(self):
        self.write([['','CD4','A_B','A','B','NaN','2','before','']])
        rr,_=cc.read_sources(self.input,PROFILE);self.assertIn('invalid_range:pval',rr[0]['issues'])
        self.assertEqual(len(cc.make_units(rr,PROFILE)),1)
    def test_duplicate_observations_keep_distinct_source_ids(self):
        self.write([ROWS[0],ROWS[0]])
        rr,_=cc.read_sources(self.input,PROFILE);self.assertEqual(len(cc.make_units(rr,PROFILE)[0]['state']['records']),2)
        self.assertNotEqual(rr[0]['id'],rr[1]['id'])
    def test_tensor_missing_duplicate_foreign_rows_are_rejected(self):
        spec={'file':'edges.csv','level':'LR','coverage':'stored_tensor','axes':{'source':['KC'],'target':['CD4'],'interaction_name':['A_B']}}
        m=self.root/'manifest.json';m.write_text(json.dumps({'format':'cellchat-export-v1','files':[spec]}))
        for rows in [[],[ROWS[0],ROWS[0]],[ROWS[2]]]:
            self.write(rows)
            with self.assertRaises(ValueError):cc.read_sources(m,PROFILE)
        self.write([ROWS[0]]);self.assertEqual(len(cc.read_sources(m,PROFILE)[0]),1)
    def test_pathway_not_forced_to_ligand_receptor(self):
        self.write([['KC','CD4','SIGNAL','2.3']],['source','target','pathway_name','prob'])
        p={**PROFILE,'level':'pathway'};rr,_=cc.read_sources(self.input,p)
        self.assertEqual(rr[0]['level'],'pathway');self.assertIsNone(rr[0]['parsed']['pval'])
        self.assertNotIn('ligand',rr[0]['raw'])
    def test_context_conflicts_separate_rows_and_record_parameters(self):
        p=copy.deepcopy(PROFILE);p['context']['condition']='other'
        rr,_=cc.read_sources(self.input,p);self.assertIn('context_conflict:condition',rr[0]['issues'])
        self.assertEqual(len(cc.make_units(rr,p)),3)
    def test_frozen_plan_reparse_and_input_tamper(self):
        out=self.root/'run';plan=cc.plan(self.input,self.profile,out)
        self.assertEqual(plan['source_rows'],3);cc.load(out)
        with (out/'input'/'edges.csv').open('a') as f:f.write('garbage\n')
        with self.assertRaises(ValueError):cc.load(out)
    def test_mock_receipts_do_not_certify_native_completion(self):
        out=self.root/'run';cc.plan(self.input,self.profile,out)
        result=cc.run(out,backend=Backend())
        self.assertEqual(result['status'],'incomplete_or_invalid')
        self.assertIn('simulated_backend_not_native',result['errors'])
    def test_tokens_question_binding_and_provider_mismatch_fail(self):
        rr,_=cc.read_sources(self.input,PROFILE);u=cc.make_units(rr,PROFILE)[0];b=Backend()
        r={'binding':cc.request_identity(u,b.identity),'native':b.evaluate(u['state'],u['questions'])}
        cc.check_receipt(r,u,b.identity)
        for change in ['tokens','questions','provider']:
            wrong=copy.deepcopy(r)
            if change=='tokens':wrong['native']['payload']['usage']['input_tokens']=1
            if change=='questions':wrong['native']['payload']['answers']={}
            if change=='provider':wrong['native']['provider_identity']={'kind':'bad'}
            with self.assertRaises(ValueError):cc.check_receipt(wrong,u,b.identity)
    def test_jev_explicit_optin_and_body_contract(self):
        from bio_topics.backend import HTTPBackend
        with self.assertRaises(ValueError):HTTPBackend({'kind':'jev','model':'jev-1.13.0'})
    def test_empty_table_has_zero_cards_without_inventing_negative_results(self):
        self.write([]); rr,_=cc.read_sources(self.input,PROFILE);self.assertEqual(cc.make_units(rr,PROFILE),[])

if __name__=='__main__':unittest.main()
