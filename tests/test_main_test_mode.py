"""Free Q&A must remain available even when test sensors indicate Level 5."""
import unittest
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch
from contextlib import nullcontext

import main_test


class NormalQATestMode(unittest.TestCase):
    def setUp(self):
        with patch('main_test.PromptSession'):
            self.app = main_test.EdgeSaverTest()
        self.app._tts = Mock()
        self.app._tts.wait_until_idle.return_value = True
        self.addCleanup(self.app._stop_query_worker)

    def wait_for_jobs(self):
        deadline = time.monotonic() + 2
        while self.app._query_queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.app._query_queue.unfinished_tasks, 0)

    def test_high_risk_does_not_interrupt_normal_qa(self):
        app = self.app
        app.current_level = 5
        app._tts = Mock()
        app._tts.wait_until_idle.return_value = True
        with patch.object(main_test.rag_manager, "search", return_value=[
            {"page_content": "test manual", "source": "test.txt"}
        ]), patch("rag.provider.generate_guidance", return_value=SimpleNamespace(
            text="test answer", provider="test"
        )) as generate, patch("main_test.trigger_alarm") as alarm:
            app._process_query("화재 대처 방법", "ko")
            self.wait_for_jobs()
            self.assertEqual(generate.call_args.args[1], "화재 대처 방법")
            self.assertFalse(generate.call_args.kwargs.get("emergency", False))
            app._tts.speak_async.assert_called_once()
            self.assertEqual(app._tts.speak_async.call_args.args[0], "test answer")
            alarm.assert_not_called()
            self.assertFalse(app._is_generating)
            self.assertIn("llm_s", app.last_query_timings)

    def test_new_question_returns_while_old_answer_runs_and_discards_old_speech(self):
        started, release = threading.Event(), threading.Event()
        def answer(context, query, **kwargs):
            if query == 'first':
                started.set()
                release.wait(2)
            return SimpleNamespace(text=query + ' answer', provider='test')
        with patch.object(main_test.rag_manager, 'search', return_value=[]), \
             patch('rag.provider.generate_guidance', side_effect=answer):
            self.app._process_query('first', 'ko')
            self.assertTrue(started.wait(1))
            try:
                self.app._process_query('second', 'ko')
                self.app._process_query('third', 'ko')
                self.assertFalse(release.is_set())
                self.assertEqual(self.app._query_queue.qsize(), 1)
            finally:
                release.set()
            self.wait_for_jobs()
            spoken = [call.args[0] for call in self.app.tts.speak_async.call_args_list]
            self.assertEqual(spoken, ['third answer'])

    def test_prompt_does_not_wait_for_tts(self):
        started, release = threading.Event(), threading.Event()
        def wait(**kwargs):
            started.set()
            release.wait(1)
            return True
        self.app.tts.wait_until_idle.side_effect = wait
        with patch.object(main_test.rag_manager, 'search', return_value=[]), \
             patch('rag.provider.generate_guidance', return_value=SimpleNamespace(text='answer', provider='test')):
            self.app._process_query('question', 'ko')
            self.assertTrue(started.wait(1))
            self.assertGreater(self.app._query_queue.unfinished_tasks, 0)
            release.set()
            self.wait_for_jobs()

    def test_run_returns_to_refreshed_prompt_while_answer_is_pending(self):
        started, release = threading.Event(), threading.Event()
        def generate(*args, **kwargs):
            started.set()
            release.wait(2)
            return SimpleNamespace(text='answer', provider='test')
        prompts = []
        def prompt(*args, **kwargs):
            prompts.append(kwargs)
            if len(prompts) == 1:
                return 'question'
            self.assertTrue(started.wait(1))
            self.assertFalse(release.is_set())
            return 'q'
        self.app.session.prompt.side_effect = prompt
        with patch.object(self.app, 'initialize'), \
             patch.object(self.app, '_monitor_sensors'), \
             patch('main_test.patch_stdout', return_value=nullcontext()), \
             patch.object(main_test.rag_manager, 'search', return_value=[]), \
             patch('rag.provider.generate_guidance', side_effect=generate):
            try:
                self.app.run()
                self.assertEqual(len(prompts), 2)
                self.assertTrue(all(p['refresh_interval'] == 0.5 for p in prompts))
            finally:
                release.set()
            self.wait_for_jobs()

    def test_microphone_request_discards_pending_answer(self):
        started, release = threading.Event(), threading.Event()
        def generate(*args, **kwargs):
            started.set()
            release.wait(2)
            return SimpleNamespace(text='stale answer', provider='test')
        with patch.object(main_test.rag_manager, 'search', return_value=[]), \
             patch('rag.provider.generate_guidance', side_effect=generate):
            self.app._process_query('question', 'ko')
            self.assertTrue(started.wait(1))
            self.app._cancel_pending_query()
            release.set()
            self.wait_for_jobs()
            self.app.tts.speak_async.assert_not_called()
