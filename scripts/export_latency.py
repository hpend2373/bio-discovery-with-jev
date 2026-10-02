"""Export anonymous timing and paired choice agreement from a private GPU run.

Never upload the private run directory. This allowlist deliberately excludes
source evidence, study IDs, original dimensions, input hashes, and raw answers.
"""
import argparse
import collections
import json
import statistics
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    args = p.parse_args()
    raw = json.loads((args.run/'latency-results.json').read_text())
    inputs = json.loads((args.run/'private-inputs.json').read_text())
    questions = inputs['questions']
    n, repeats = raw['sample_unique_units'], raw['repeats']
    if len(inputs['units'])!=n or len(questions)!=raw['questions_per_request']:
        raise ValueError('Input contract does not match timing metadata')
    counters, choices = collections.Counter(), {}
    for row in raw['measurements']:
        provider,rep,idx = row['provider'],row['repeat'],row['sample_index']
        if provider not in ('laya','llm') or row['status']!='ok':
            raise ValueError('Failed or unexpected provider in timing run')
        key = (provider,rep,idx)
        if key in choices:
            raise ValueError('Duplicate timing request')
        pos = counters[provider,rep]
        counters[provider,rep] += 1
        response = json.loads((args.run/f'private-{provider}-{rep}-{pos}.json').read_text())
        answer = ({q:v['choice'] for q,v in response['payload']['answers'].items()}
                  if provider=='laya' else json.loads(response['message']['content']))
        if set(answer)!=set(questions) or any(answer[q] not in questions[q]['criteria'] for q in questions):
            raise ValueError('Incomplete or invalid choices in native receipt')
        choices[key] = answer
    expected = {(provider,rep,idx) for provider in ('laya','llm') for rep in range(repeats) for idx in range(n)}
    if set(choices)!=expected:
        raise ValueError('Unmatched or incomplete sample sets')
    agreement = {'measure':'paired categorical agreement; not accuracy or scientific validity','by_repeat':[]}
    for rep in range(repeats):
        same = sum(choices['laya',rep,idx][q]==choices['llm',rep,idx][q] for idx in range(n) for q in questions)
        total = n*len(questions)
        agreement['by_repeat'].append({'repeat':rep,'matching_choices':same,'paired_choices':total,'fraction':same/total})
    agreement['matching_choices'] = sum(r['matching_choices'] for r in agreement['by_repeat'])
    agreement['paired_choices'] = sum(r['paired_choices'] for r in agreement['by_repeat'])
    agreement['fraction'] = agreement['matching_choices']/agreement['paired_choices']
    summary = {}
    for provider in ('laya','llm'):
        rows = [r for r in raw['measurements'] if r['provider']==provider]
        summary[provider] = {'requests':len(rows),'valid':len(rows),'seconds':sum(r['seconds'] for r in rows),
                             'median_seconds':statistics.median(r['seconds'] for r in rows)}
    health = raw['gpu_verification']['laya_health']
    if health['checkpoint_devices']['multilingual']!='cuda' or raw['hardware']['provider_devices']!={'laya':'cuda','llm':'cuda'}:
        raise ValueError('GPU execution not verified for both providers')
    exported = {k:raw[k] for k in ('date','sample_unique_units','repeats','questions_per_request','llm','hardware')}
    exported.update(schema_version=2,scope='Matched categorical-task GPU timing sample',summary=summary,
        laya={'name':'multilingual','revision':health['revisions']['multilingual']},
        method={'concurrency':1,'phase_order':['llm','laya'],'gpu_isolation':True,'warmup_excluded':True,
            'timing':'HTTP request through complete answer validation; Laya tokenizer guard included',
            'answer_cache':False,'native_prompt_kv_cache':'allowed','llm_thinking':False,
            'output':'Qwen generates choice IDs; Laya also returns choice probabilities',
            'sample_warmup':'One sampled payload was used for warmup; first pass is not strictly uncached',
            'ordering':'Provider phases were not randomized; requests were shuffled within each pass'},
        gpu_verification={'qwen_layers_on_gpu':raw['gpu_verification']['qwen_layers_on_gpu'],
            'qwen_layers_total':raw['gpu_verification']['qwen_layers_total'],
            'qwen_compute_process_observed':raw['gpu_verification']['qwen_compute_process_observed'],
            'laya_checkpoint_device':'cuda','laya_cpu_fallbacks':health['cpu_fallbacks']['multilingual']['count']},
        choice_agreement=agreement,
        measurements=[{k:r[k] for k in ('provider','repeat','sample_index','seconds','status')} for r in raw['measurements']])
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(exported,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'summary':summary,'choice_agreement':agreement}))


if __name__=='__main__':
    main()
