"""Repeat a frozen timing sample with one model at a time on the GPU.

Explicit --switch-containers authorizes stopping/starting the named local
containers. Laya is restored and the Ollama model is unloaded in finally.
Input evidence and native responses are private; keep --out under runs/.
"""
import argparse
import copy
import json
import random
import statistics
import subprocess
import time
from pathlib import Path

from benchmark_latency import HTTPBackend, http_json, llm_body, validate_llm
from bio_topics.util import digest


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, stderr=subprocess.STDOUT)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True, type=Path)
    p.add_argument('--sample-run', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--laya-container', default='laya-local-laya-serve-1')
    p.add_argument('--ollama-container', default='ollama')
    p.add_argument('--switch-containers', action='store_true', required=True)
    args = p.parse_args()
    inputs = json.loads((args.sample_run/'private-inputs.json').read_text())
    original = json.loads((args.sample_run/'latency-results.json').read_text())
    assert digest(inputs) == original['sample_contract_hash'], 'Changed timing inputs'
    selected, questions = inputs['units'], inputs['questions']
    model = original['llm']['name']
    profile = json.loads((args.run/'profile.json').read_text())
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'private-inputs.json').write_text(json.dumps(inputs, ensure_ascii=False))
    result = copy.deepcopy(original)
    for key in ('summary', 'hardware', 'code', 'projection', 'verification'):
        result.pop(key, None)
    result['measurements'], result['warmups'] = [], []
    result['method']['phase_order'] = ['llm', 'laya']
    result['method']['gpu_isolation'] = True
    result['method']['limits'] = 'Sequential isolated GPU phases, not randomized provider order. Native prompt/KV caches allowed. Timing is not scientific quality.'
    backend = None
    rng = random.Random(20261002)
    def save():
        (args.out/'latency-results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    def unload():
        http_json('http://127.0.0.1:11434/api/generate', {'model':model, 'keep_alive':0})
    try:
        docker('stop', args.laya_container)
        unload()  # Fresh runner: do not reuse the previous CPU/short-probe context.
        for provider in ('llm', 'laya'):
            if provider == 'laya':
                unload()
                docker('start', args.laya_container)
                deadline = time.monotonic()+180
                while True:
                    try:
                        health = http_json('http://127.0.0.1:8000/health', timeout=3)
                        if health.get('status') == 'ok' and health.get('device') == 'cuda':
                            break
                    except Exception:
                        pass
                    if time.monotonic()>deadline:
                        raise RuntimeError('Laya GPU health not ready')
                    time.sleep(2)
                if not health.get('revisions', {}).get('multilingual'):
                    started = time.perf_counter()
                    http_json('http://127.0.0.1:8000/v1/systemone', {
                        'model':'multilingual', 'state':'Synthetic GPU startup readiness probe.',
                        'questions':{'probe':{'type':'choice','instructions':'Is study evidence available?',
                            'criteria':{'yes':'Study evidence available','no':'No study evidence'}}},
                        'max_len':4096, 'head_max_len':384})
                    result['warmups'].append({'provider':'laya_startup',
                        'seconds':time.perf_counter()-started, 'synthetic':True})
                backend = HTTPBackend(profile['backend'])
                result['laya_identity'] = backend.identity
                # Check actual loaded checkpoint after the first evaluation (lazy loading).
            start = time.perf_counter()
            unit = selected[-1]
            if provider == 'llm':
                warm = http_json('http://127.0.0.1:11434/api/chat', llm_body(model, unit['state'], questions))
                validate_llm(warm, questions, model)
            else:
                warm = backend.evaluate(unit['state'], questions)
                health = http_json('http://127.0.0.1:8000/health')
                if health.get('checkpoint_devices', {}).get('multilingual') != 'cuda':
                    raise RuntimeError('Laya checkpoint did not load on GPU')
                result['gpu_verification']['laya_health'] = health
            result['warmups'].append({'provider':provider, 'seconds':time.perf_counter()-start,
                                      'load_seconds':warm.get('load_duration',0)/1e9})
            (args.out/f'private-{provider}-warmup.json').write_text(json.dumps(warm, ensure_ascii=False))
            if provider == 'llm':
                logs = docker('logs', '--since', '3m', args.ollama_container)
                evidence = [line for line in logs.splitlines() if 'offloaded 42/42 layers to GPU' in line or 'CUDA0 model buffer size' in line]
                smi = subprocess.check_output(['nvidia-smi'], text=True)
                if not any('offloaded 42/42' in line for line in evidence) or '/usr/lib/ollama/llama-server' not in smi:
                    raise RuntimeError('Qwen GPU offload not verified; no speed claim permitted')
                (args.out/'private-gpu-processes.txt').write_text(smi)
                result['gpu_verification'] = {'qwen_offload':evidence,
                    'qwen_compute_process_observed':True, 'qwen_layers_on_gpu':42, 'qwen_layers_total':42}
                result['hardware'] = {'gpu':'NVIDIA GB10', 'driver':'580.159.03', 'architecture':'aarch64',
                    'provider_devices':{'laya':'cuda','llm':'cuda'},
                    'isolation':'Laya stopped during Qwen phase; Qwen unloaded during Laya phase'}
            for repeat in range(result['repeats']):
                order = list(selected)
                rng.shuffle(order)
                for index, unit in enumerate(order):
                    started = time.perf_counter()
                    response = None
                    status, error = 'ok', None
                    try:
                        if provider == 'llm':
                            response = http_json('http://127.0.0.1:11434/api/chat', llm_body(model,unit['state'],questions))
                            validate_llm(response,questions,model)
                        else:
                            response = backend.evaluate(unit['state'],questions)
                    except Exception as exc:
                        status, error = 'failed', type(exc).__name__+': '+str(exc)
                    item = {'provider':provider,'kind':unit['kind'],'repeat':repeat,
                            'sample_index':selected.index(unit),'seconds':time.perf_counter()-started,'status':status}
                    if error:
                        item['error']=error
                    if provider=='llm' and response:
                        item.update({k:response.get(k) for k in ('total_duration','load_duration','prompt_eval_count','prompt_eval_duration','eval_count','eval_duration')})
                    result['measurements'].append(item)
                    (args.out/f'private-{provider}-{repeat}-{index}.json').write_text(json.dumps(response,ensure_ascii=False))
                    save()
                    print(json.dumps({'provider':provider,'repeat':repeat+1,'completed':index+1,'seconds':round(item['seconds'],3),'status':status}),flush=True)
        result['summary']={}
        for provider in ('laya','llm'):
            rows=[m for m in result['measurements'] if m['provider']==provider]
            result['summary'][provider]={'requests':len(rows),'valid':sum(m['status']=='ok' for m in rows),
                'seconds':sum(m['seconds'] for m in rows),'median_seconds':statistics.median(m['seconds'] for m in rows)}
        save()
        if any(m['status']!='ok' for m in result['measurements']):
            raise RuntimeError('Invalid/incomplete answers: comparison rejected')
        print(json.dumps(result['summary']),flush=True)
    finally:
        if backend:
            backend.close()
        try:
            unload()
        finally:
            docker('start',args.laya_container)


if __name__=='__main__':
    main()
