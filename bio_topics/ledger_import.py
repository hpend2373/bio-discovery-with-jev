"""Prepare an exact effect-ID ledger join from an explicit local file, never fuzzy text."""
import csv,json
from pathlib import Path
from .clinical import ALLOWED
from .ingest import read_profile,read_table,_xlsx
from .ledger import linkage_audit
from .util import write_json

ALIASES = {
    'publication_id':['rec_id'], 'study_id':['study_id'], 'measure':['effect_measure'], 'value':['effect_point'],
    'ci_lower':['effect_ci_low'], 'ci_upper':['effect_ci_high'], 'outcome_definition':['outcome_name'],
    'outcome_family':['outcome_domain'], 'outcome_time':['outcome_timepoint'], 'model':['effect_model'],
    'adjustment_variables':['adjustment_covariates'], 'human_checked':['human_confirmed'],
    'synthesis_approved':['pool_eligible'], 'source_blocked':['source_or_derivation_blocked'],
    'source_location':['source_page_ref']}


def prepare_effect_ledger(input_path, profile_path, ledger_path, out, sheet=None, require_all=True, ci_level_percent=False):
    source = Path(ledger_path).resolve(); out = Path(out).resolve()
    if out.exists(): raise ValueError('Choose a new ledger-import directory')
    if source.suffix.lower()=='.xlsx': headers,_,_= _xlsx(source,sheet)
    else:
        with source.open(encoding='utf-8-sig',newline='') as f:
            headers=next(csv.reader(f,delimiter='\t' if source.suffix.lower()=='.tsv' else ','))
    ids=[k for k in ['source_effect_id','effect_row_id','effect_id'] if k in headers]
    if len(ids)!=1: raise ValueError('Specify one unambiguous effect ID column: source_effect_id, effect_row_id or effect_id')
    mapping={}
    for field in sorted(ALLOWED['effects']):
        if field in headers: mapping[field]=field;continue
        matches=[k for k in ALIASES.get(field,[]) if k in headers]
        if len(matches)>1: raise ValueError('Ambiguous ledger aliases: '+field)
        if matches:mapping[field]=matches[0]
    profile=read_profile(profile_path)
    clinical=profile.setdefault('clinical',{});clinical['enabled']=True
    clinical.setdefault('ledger_files',[]).append({'entity':'effects','path':str(source),'id_column':ids[0],
        'columns':mapping,'confirmed':True,'source_reference':'Explicit source effect-ID join; not full-text verification',**({'sheet':sheet} if sheet else {})})
    # CI percentages must be declared by the user/profile; never inferred from magnitudes.
    if 'ci_level' in mapping and ci_level_percent:
        clinical['ledger_files'][-1]['transforms']={'ci_level':'percent_to_fraction'}
    if require_all:clinical.setdefault('ledger_requirements',{})['effects']='all_input_rows'
    out.mkdir(parents=True)
    write_json(out/'profile.json',profile)
    parsed=read_profile(out/'profile.json');records,_=read_table(input_path,parsed)
    # Export diagnostics even when the required-all guard will reject planning.
    check_profile=json.loads(json.dumps(parsed));check_profile['clinical'].pop('ledger_requirements',None)
    audit=linkage_audit(records,check_profile);write_json(out/'ledger-linkage.json',audit)
    from .clinical_report import write_csv
    write_csv(out/'ledger-linkage.csv',audit['rows'],['record_id','source_effect_id','entity','lookup_id','status','conflicts','source_references'])
    write_csv(out/'unused-ledger-entries.csv',audit['unused_ledger_entries'],['entity','id','status','source_reference'])
    linkage_audit(records,parsed)
    return {'profile':str(out/'profile.json'),'coverage':audit['coverage'],'unused_entries':len(audit['unused_ledger_entries']),
            'input_rows_preserved':len(records),'source_effect_id_only':True,'source_verification_promoted':False}
