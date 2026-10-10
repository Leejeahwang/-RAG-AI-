import json
import unittest
from unittest.mock import Mock, patch

from rag.chain import call_ollama_native


class OllamaStreamTests(unittest.TestCase):
    def response(self, chunks):
        response = Mock(status_code=200)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_lines.return_value = [json.dumps(c).encode() for c in chunks]
        return response

    @patch('rag.chain.requests.post')
    def test_complete_structured_response_and_custom_prompt(self, post):
        post.return_value = self.response([
            {'message': {'content': '{"line_ids":[1]}'}},
            {'done': True, 'done_reason': 'stop'},
        ])
        schema = {'type': 'object'}
        answer = ''.join(call_ollama_native('manual', system_prompt='select IDs',
                                          response_format=schema, num_predict=64))
        self.assertEqual(json.loads(answer), {'line_ids': [1]})
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['messages'][0]['content'], 'select IDs')
        self.assertEqual(payload['format'], schema)

    @patch('rag.chain.requests.post')
    def test_incomplete_or_error_stream_is_not_accepted(self, post):
        for chunks in ([{'message': {'content': 'partial'}}],
                       [{'done': True, 'done_reason': 'length'}],
                       [{'error': 'failed'}]):
            with self.subTest(chunks=chunks):
                post.return_value = self.response(chunks)
                with self.assertRaises(RuntimeError):
                    list(call_ollama_native('manual'))
