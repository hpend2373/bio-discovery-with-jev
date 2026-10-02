"""Runs a tokenizer-only verifier inside the existing Laya container; no model is loaded."""
WORKER = r'''
import hashlib, inspect, json, sys
from pathlib import Path
from transformers import AutoTokenizer
import laya.common as common

def emit(value):
 print(json.dumps(value,ensure_ascii=False),flush=True)

config=json.loads(sys.stdin.readline())
folder=Path(config['model_path'])/'tokenizer'
tok=AutoTokenizer.from_pretrained(str(folder),local_files_only=True)
fingerprint=hashlib.sha256((folder/'tokenizer.json').read_bytes()).hexdigest()
emit({'ready':True,'tokenizer_sha256':fingerprint,
      'serializer_sha256':hashlib.sha256(Path(common.__file__).read_bytes()).hexdigest()})
for line in sys.stdin:
 try:
  request=json.loads(line)
  state=common.serialize_state(request['state'])
  if tok.mask_token in state:
   raise ValueError('State contains the model mask token, which the server would replace.')
  state_ids=common.encode_text(tok,state,add_special_tokens=False)['input_ids']
  lengths={}
  for qid,qdef in request['questions'].items():
   q={'t':qdef['type'],'ins':qdef['instructions'],'crit':qdef['criteria']}
   head=common._encode_question_text(tok,q['t']+' question: '+q['ins'],add_special_tokens=False)
   opts=common.render_options(q)
   option_ids=[common._encode_question_text(tok,' '+o.replace(tok.mask_token,' '),add_special_tokens=False) for o in opts]
   if any(len(ids)>48 for ids in option_ids):
    raise ValueError('Option would be truncated at 48 tokens.')
   if len({tuple(ids) for ids in option_ids})!=len(opts):
    raise ValueError('Indistinguishable option tokens.')
   option_tokens=sum(len(ids)+1 for ids in option_ids)
   room=request['head_max_len']-option_tokens
   if room<16 or len(head)>max(8,room):
    raise ValueError('Question or options would be truncated by head budget.')
   total=4+len(head)+option_tokens+len(state_ids)
   if total>request['max_len']:
    raise ValueError('Full evidence exceeds token budget: '+str(total))
   ids,markers,stats=common.build_sequence(tok,request['state'],q,request['max_len'],request['head_max_len'],state_ids=state_ids,return_stats=True)
   if len(ids)!=total or len(markers)!=len(opts) or stats['options_distinct']!=len(opts):
    raise ValueError('Serializer mismatch or lost options.')
   lengths[qid]=total
  emit({'ok':True,'state_tokens':len(state_ids),'question_lengths':lengths,'expected_input_tokens':sum(lengths.values())})
 except Exception as exc:
  emit({'ok':False,'error':str(exc)})
'''


import json
import selectors
import subprocess
import tempfile


class TokenGuard:
    def __init__(self, container, model_path):
        self.log = tempfile.TemporaryFile(mode="w+")
        self.proc = subprocess.Popen(["docker", "exec", "-i", container, "python", "-u", "-c", WORKER],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True, bufsize=1)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)
        try:
            self._send({"model_path": model_path})
            self.identity = self._read(60)
            if not self.identity.get("ready"):
                raise RuntimeError("토크나이저 검증기 시작 실패")
        except BaseException:
            self.close()
            raise

    def _send(self, value):
        self.proc.stdin.write(json.dumps(value, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _read(self, timeout):
        if not self.selector.select(timeout):
            raise RuntimeError("토크나이저 검증기 응답 시간 초과")
        line = self.proc.stdout.readline()
        if not line:
            self.log.seek(0)
            raise RuntimeError("토크나이저 검증기 종료: " + self.log.read()[-1200:])
        return json.loads(line)

    def check(self, state, questions, max_len, head_max_len):
        self._send({"state": state, "questions": questions, "max_len": max_len, "head_max_len": head_max_len})
        result = self._read(30)
        if not result.get("ok"):
            raise ValueError("근거를 자를 수 없어 검사하지 않음: " + result.get("error", "unknown"))
        return result

    def close(self):
        if self.proc.stdin:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        self.selector.close()
        self.proc.stdout.close()
        self.log.close()
