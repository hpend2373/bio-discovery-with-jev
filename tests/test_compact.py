import unittest
from copy import deepcopy
from bio_topics.compact import checked_pack,unpack_state,table,untab
from bio_topics.util import canonical

class CompactTests(unittest.TestCase):
    def state(self):
        return {'records':[{'id':'R1','fields':{'effect':None,'zero':0,'flag':False,'empty':'','text':'[value] 끝 😀'*600},
         'raw':{'effect':'0.8','unmapped_note':'Opposing result; do not pool','null':None},
         'original_fields':{'effect':0.8,'zero':0,'text':'original'},
         'clinical':{'conflicts':['effect'],'links':[{'confirmed':False,'source_reference':'unknown'}],
          'proposals':[{'fields':{'population':'other'}}],'normalization':[{'source_reference':'explicit'}],
          'provenance':{'effect':[{'value':0.8,'source':'input'},{'value':1.2,'source':'ledger','source_reference':'table2'}],
                        'zero':[{'value':0,'source':'input'}], 'flag':[{'value':False,'source':'input'}],
                        'absent':[{'value':None,'source':'ledger'}]}},'parse_issues':[{'issue':'CI conflict'}]},
         {'id':'R2','fields':{'effect':1.2},'raw':{},'clinical':{'provenance':{}}}],
         'observations':{'null':None,'empty':[]}}
    def test_exact_reconstruction_preserves_conflicts_unknowns_notes_and_edges(self):
        s=self.state();original=deepcopy(s);p=checked_pack(s)
        self.assertEqual(canonical(unpack_state(p)),canonical(s));self.assertEqual(s,original)
        self.assertIn('1.2',canonical(p));self.assertIn('Opposing result',canonical(p))
    def test_missing_null_empty_zero_false_remain_distinct(self):
        rows=[{}, {'x':None},{'x':''},{'x':0},{'x':False},{'x':[]},{'x':{}}]
        self.assertEqual(canonical(untab(table(rows))),canonical(rows))
    def test_tampering_changes_reconstructed_evidence(self):
        s=self.state();p=checked_pack(s)
        p['complete_evidence']['sources'][0]['source']='tampered'
        self.assertNotEqual(canonical(unpack_state(p)),canonical(s))
    def test_bad_table_shape_rejected(self):
        t=table([{'x':1}]);t['rows'][0]=[]
        with self.assertRaises(ValueError):untab(t)
    def test_no_records_and_cell_rows(self):
        self.assertEqual(checked_pack({'observations':1}),{'observations':1})
        s=self.state();s['evidence_rows']=s.pop('records')
        self.assertEqual(unpack_state(checked_pack(s)),s)

    def test_split_pages_expand_references_before_partitioning(self):
        from bio_topics.partitioning import make_pages,restore_pages,atoms
        state=self.state();state.update(research_question='Why?',domain='meta')
        parent={'id':'u','kind':'cell','scope':{},'record_ids':['R1','R2'],'state':checked_pack(state)}
        def checker(s):
            if len(canonical(s))>3000:raise ValueError('Full evidence exceeds token budget: limit')
            return {'ok':True}
        pages,spec=make_pages(parent,checker)
        self.assertGreater(len(pages),1)
        self.assertEqual([e for pg in pages for e in pg['state']['evidence_entries']],list(atoms(state)))
        self.assertEqual(restore_pages(parent,spec),pages)
