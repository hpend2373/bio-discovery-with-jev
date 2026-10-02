"""Wire-contract tests with synthetic responses; these are not live model evaluations."""
import json
import os
import unittest
from unittest.mock import patch

from bio_topics.backend import HTTPBackend, slice_receipt, validate_receipt
from bio_topics.plan import batch_questions, questions


def payload(qs, model):
    answers = {}
    for name, q in qs.items():
        choice = next(iter(q['criteria']))
        answers[name] = {'type': 'choice', 'choice': choice,
                         'probabilities': {k: float(k == choice) for k in q['criteria']}}
    return {'model': model, 'answers': answers, 'usage': {'input_tokens': 192, 'output_tokens': 0}}


class BackendContractTests(unittest.TestCase):
    def setUp(self):
        self.qs = batch_questions({'inspection': {}})
        self.state = {'records': [{'id': 'held', 'source_blocked': True},
                                  {'id': 'weak', 'fdr': 0.99}], 'unknown': None}
        self.cfg = {'kind': 'jev', 'model': 'jev-1.13.0'}

    def test_jev_requires_external_flag_and_key(self):
        with self.assertRaises(ValueError):
            HTTPBackend(self.cfg)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            HTTPBackend(self.cfg, allow_external=True)

    @patch.dict(os.environ, {'TYPESAFE_API_KEY': 'synthetic-test-key'})
    def test_jev_full_batch_and_receipt_binding(self):
        with patch.object(HTTPBackend, '_request', return_value=payload(self.qs, self.cfg['model'])) as request:
            backend = HTTPBackend(self.cfg, allow_external=True)
            full = backend.evaluate(self.state, self.qs)
        endpoint, encoded = request.call_args.args
        self.assertEqual(endpoint, 'https://api.typesafe.ai/v1/systemone')
        self.assertEqual(json.loads(encoded), {'state': self.state, 'model': self.cfg['model'], 'questions': self.qs})
        self.assertEqual(len(self.qs), 16)
        self.assertNotIn('synthetic-test-key', json.dumps(full))
        receipt = slice_receipt(full, 'robustness', self.state, self.qs)
        validate_receipt(receipt, self.state, questions('robustness'), backend.identity, self.qs, 'robustness')
        receipt['batch']['request_hash'] = 'modified'
        with self.assertRaises(ValueError):
            validate_receipt(receipt, self.state, questions('robustness'), backend.identity, self.qs, 'robustness')

    @patch.dict(os.environ, {'TYPESAFE_API_KEY': 'synthetic-test-key'})
    def test_jev_wrong_model_and_large_body_are_rejected(self):
        with patch.object(HTTPBackend, '_request', return_value=payload(self.qs, 'jev-1.12.0')):
            with self.assertRaises(ValueError):
                HTTPBackend(self.cfg, allow_external=True).evaluate(self.state, self.qs)
        with patch.object(HTTPBackend, '_request') as request:
            with self.assertRaises(ValueError):
                HTTPBackend({**self.cfg, 'max_body_bytes': 20}, allow_external=True).evaluate(self.state, self.qs)
            request.assert_not_called()

    @patch.dict(os.environ, {'TYPESAFE_API_KEY': 'synthetic-test-key'})
    def test_jev_mutable_alias_and_invalid_version_are_rejected(self):
        for model in ('jev-latest', 'jev-preview', 'jev-unknown'):
            with self.subTest(model=model), self.assertRaises(ValueError):
                HTTPBackend({**self.cfg, 'model': model}, allow_external=True)

    def test_laya_full_context_guard_and_token_binding(self):
        health = {'status': 'ok', 'revisions': {'multilingual': 'test-revision'}}
        guard_receipt = {'ok': True, 'question_lengths': {q: 12 for q in self.qs}, 'expected_input_tokens': 192}
        with patch('bio_topics.backend.TokenGuard') as guard, \
             patch.object(HTTPBackend, '_request', side_effect=[health, payload(self.qs, 'multilingual')]) as request:
            guard.return_value.identity = {'tokenizer_sha256': 'synthetic-tokenizer'}
            guard.return_value.check.return_value = guard_receipt
            backend = HTTPBackend({'kind': 'laya'})
            full = backend.evaluate(self.state, self.qs)
            guard.return_value.check.assert_called_once_with(self.state, self.qs, 4096, 384)
            encoded = json.loads(request.call_args.args[1])
            self.assertEqual(encoded['state'], self.state)
            self.assertEqual(encoded['questions'], self.qs)
            receipt = slice_receipt(full, 'integrity', self.state, self.qs)
            validate_receipt(receipt, self.state, questions('integrity'), backend.identity, self.qs, 'integrity')
            receipt['context_receipt']['expected_input_tokens'] -= 1
            with self.assertRaises(ValueError):
                validate_receipt(receipt, self.state, questions('integrity'), backend.identity, self.qs, 'integrity')
            backend.close()
            guard.return_value.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
