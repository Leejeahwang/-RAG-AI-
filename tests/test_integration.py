"""Regression tests for vision -> risk -> RAG -> speech orchestration."""
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import config
import main
from vision import fire_detector
from sensors.fusion import calculate_risk_level


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        patch.object(config, 'ZONE_ID', 'A').start()
        patch.object(config, 'DETECTION_ZONE_ID', 'A').start()
        self.app = main.EdgeSaver()
        self.app._tts = Mock()
        self.app._tts.is_speaking.return_value = False
        self.alarm = patch('main.trigger_alarm').start()
        patch('main.stop_siren').start()
        self.notify = patch('main.send_alert').start()
        self.addCleanup(patch.stopall)
        self.addCleanup(self.app.cleanup)

    def test_emergency_does_not_wait_for_running_general_answer(self):
        started, release = threading.Event(), threading.Event()
        def generate(context, question, **kwargs):
            if not kwargs['emergency']:
                started.set()
                release.wait(2)
                return SimpleNamespace(text='obsolete answer', provider='test')
            return SimpleNamespace(text=main.EMERGENCY_GUIDANCE, provider='fixed')
        with patch('main.rag_manager.search', return_value=[]), patch('main.generate_guidance', side_effect=generate):
            self.app._start_thread(self.app._guidance_worker, 'test-guidance')
            self.app._process_query('normal question')
            self.assertTrue(started.wait(1))
            try:
                self.app._trigger_rag_alert('fire', 'smoke', 'B', level=5)
                self.notify.assert_called_once_with(zone='B', local_zone='A', risk_level=5, sensor_details='smoke')
                spoken = [c.args[0] for c in self.app.tts.speak_async.call_args_list]
                self.assertIn(main.first_emergency_guidance('B'), spoken)
            finally:
                release.set()
            deadline = time.monotonic()+2
            while self.app._jobs.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(self.app._jobs.unfinished_tasks, 0)
            self.assertNotIn('obsolete answer', [c.args[0] for c in self.app.tts.speak_async.call_args_list])

    def test_zone_guidance_precedes_ai_rules_and_survives_recovery(self):
        from rag.layout import evacuation_for_zone
        started, release = threading.Event(), threading.Event()
        zone = evacuation_for_zone('A', fire_zone='A')
        rule = '전기 화재인 경우 메인 전원을 내린 후 전용 소화기를 사용하십시오.'
        def generate(*args, **kwargs):
            started.set()
            release.wait(2)
            return SimpleNamespace(text=zone+'\n'+rule, provider='ollama')
        docs = [{'source': 'zone_B_layout.txt', 'page_content': 'B구역 출구'},
                {'source': 'factory.txt', 'page_content': rule}]
        with patch('main.rag_manager.search', return_value=docs) as search, \
             patch('main.generate_guidance', side_effect=generate) as generator:
            self.app._trigger_rag_alert('A구역 화재 대피', 'smoke', 'A')
            self.assertEqual([c.args[0] for c in self.app.tts.speak_async.call_args_list],
                             [main.first_emergency_guidance('A'), zone])
            self.app._start_thread(self.app._guidance_worker, 'test-guidance')
            self.assertTrue(started.wait(1))
            try:
                self.app._clear_alarm()
                self.assertNotIn('B구역 출구', generator.call_args.args[0])
                self.assertIn(rule, generator.call_args.args[0])
                self.assertIn('추가 안내', generator.call_args.args[1])
            finally:
                release.set()
            deadline = time.monotonic()+2
            while self.app._jobs.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual([c.args[0] for c in self.app.tts.speak_async.call_args_list],
                             [main.first_emergency_guidance('A'), zone, rule])
            self.assertEqual(search.call_count, 2)

    def test_model_failure_keeps_zone_speech_pending_through_recovery(self):
        from rag.layout import evacuation_for_zone
        self.app.tts.is_speaking.return_value = True
        with patch('main.rag_manager.search', return_value=[]), \
             patch('main.generate_guidance', side_effect=RuntimeError('offline')):
            self.app._trigger_rag_alert('fire', 'smoke', 'A')
            self.app._start_thread(self.app._guidance_worker, 'test-guidance')
            self.app._clear_alarm()
            self.app.tts.stop.reset_mock()
            time.sleep(0.1)
            self.assertIsNotNone(self.app._pending_evac_event)
            self.assertIn(evacuation_for_zone('A', fire_zone='A'), [c.args[0] for c in self.app.tts.speak_async.call_args_list])
            self.app.tts.stop.assert_not_called()
            self.app.tts.is_speaking.return_value = False
            deadline = time.monotonic()+2
            while self.app._jobs.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertIsNone(self.app._pending_evac_event)

    def test_recovery_preserves_delayed_emergency_result_once(self):
        started, release = threading.Event(), threading.Event()
        def generate(*args, **kwargs):
            started.set()
            release.wait(2)
            return SimpleNamespace(text='expired guidance', provider='test')
        with patch('main.rag_manager.search', return_value=[]), patch('main.generate_guidance', side_effect=generate):
            self.app._start_thread(self.app._guidance_worker, 'test-guidance')
            self.app._trigger_rag_alert('fire', 'smoke', 'A')
            self.assertTrue(started.wait(1))
            self.app._clear_alarm()
            release.set()
            deadline = time.monotonic()+2
            while self.app._jobs.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(0.01)
            spoken = [c.args[0] for c in self.app.tts.speak_async.call_args_list]
            self.assertEqual(spoken.count('expired guidance'), 1)
            self.assertFalse(self.app._alarm_active)
            self.assertIsNone(self.app._pending_evac_event)
            self.assertEqual(self.app._cached_evac_guidance, '')

    def test_recovery_preserves_queued_guidance_and_blocks_general_query(self):
        with patch('main.rag_manager.search', return_value=[]), \
             patch('main.generate_guidance', return_value=SimpleNamespace(text='route', provider='test')):
            self.app._trigger_rag_alert('fire', 'smoke', 'A')
            self.app._clear_alarm()
            self.app._process_query('normal question')
            self.assertEqual(self.app._jobs.qsize(), 1)
            self.app._start_thread(self.app._guidance_worker, 'test-guidance')
            deadline = time.monotonic()+2
            while self.app._jobs.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertIn('route', [c.args[0] for c in self.app.tts.speak_async.call_args_list])
            self.assertIsNone(self.app._pending_evac_event)

    def test_new_emergency_discards_previous_delayed_result(self):
        started, release = threading.Event(), threading.Event()
        def generate(context, question, **kwargs):
            if question.startswith('old fire'):
                started.set()
                release.wait(2)
                return SimpleNamespace(text='old route', provider='test')
            return SimpleNamespace(text='new route', provider='test')
        with patch('main.rag_manager.search', return_value=[]), patch('main.generate_guidance', side_effect=generate):
            self.app._start_thread(self.app._guidance_worker, 'test-guidance')
            self.app._trigger_rag_alert('old fire', 'smoke', 'A')
            self.assertTrue(started.wait(1))
            try:
                self.app._clear_alarm()
                self.app._trigger_rag_alert('new fire', 'smoke', 'B')
            finally:
                release.set()
            deadline = time.monotonic()+2
            while self.app._jobs.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(0.01)
            spoken = [c.args[0] for c in self.app.tts.speak_async.call_args_list]
            self.assertNotIn('old route', spoken)
            self.assertIn('new route', spoken)

    def test_recovery_does_not_interrupt_one_time_guidance_playback(self):
        spoken = threading.Event()
        def speak(text, **kwargs):
            if text == 'route':
                spoken.set()
        with patch('main.rag_manager.search', return_value=[]), \
             patch('main.generate_guidance', return_value=SimpleNamespace(text='route', provider='test')):
            self.app.tts.speak_async.side_effect = speak
            self.app.tts.is_speaking.return_value = True
            self.app._start_thread(self.app._guidance_worker, 'test-guidance')
            self.app._trigger_rag_alert('fire', 'smoke', 'A')
            self.assertTrue(spoken.wait(1))
            self.app.tts.stop.reset_mock()
            self.app._clear_alarm()
            self.app.tts.stop.assert_not_called()
            event_id = self.app._event_id
            self.app._trigger_rag_alert('fire again', 'smoke', 'A')
            self.assertEqual(self.app._event_id, event_id)
            self.assertIn('route', self.app._cached_evac_guidance)
            self.app.tts.stop.assert_not_called()
            self.app._clear_alarm()
            self.app._process_query('normal question')
            self.assertIsNotNone(self.app._pending_evac_event)
            self.assertEqual(self.app._jobs.qsize(), 0)
            self.app.tts.is_speaking.return_value = False
            deadline = time.monotonic()+2
            while self.app._jobs.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertIsNone(self.app._pending_evac_event)
            self.app._process_query('normal question')
            self.app.tts.stop.assert_called_once()

    def test_no_duplicate_alarm_or_normal_speech_during_emergency(self):
        self.app._trigger_rag_alert('fire', 'smoke', 'A')
        self.app._trigger_rag_alert('fire', 'smoke', 'A')
        self.app._process_query('question')
        self.alarm.assert_called_once()
        self.assertEqual(self.app._jobs.qsize(), 1)

    def test_same_zone_recurrence_keeps_queued_event(self):
        self.app._trigger_rag_alert('fire', 'smoke', 'A')
        event_id = self.app._event_id
        self.app._clear_alarm()
        self.app.tts.stop.reset_mock()
        self.app._trigger_rag_alert('fire again', 'smoke', 'A')
        self.assertTrue(self.app._alarm_active)
        self.assertEqual(self.app._event_id, event_id)
        self.assertEqual(self.app._jobs.qsize(), 1)
        self.app.tts.stop.assert_not_called()
        self.assertEqual(self.app.tts.speak_async.call_count, 2)

    def test_same_zone_recurrence_preserves_inflight_result_once(self):
        started, release = threading.Event(), threading.Event()
        def generate(*args, **kwargs):
            started.set()
            release.wait(2)
            return SimpleNamespace(text='A route', provider='test')
        with patch('main.rag_manager.search', return_value=[]), patch('main.generate_guidance', side_effect=generate) as generator:
            self.app._start_thread(self.app._guidance_worker, 'test-guidance')
            self.app._trigger_rag_alert('fire', 'smoke', 'A')
            self.assertTrue(started.wait(1))
            try:
                for _ in range(3):
                    self.app._clear_alarm()
                    self.app._trigger_rag_alert('fire again', 'smoke', 'A')
            finally:
                release.set()
            deadline = time.monotonic()+2
            while self.app._jobs.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(0.01)
            generator.assert_called_once()
            spoken = [c.args[0] for c in self.app.tts.speak_async.call_args_list]
            self.assertEqual(spoken.count('A route'), 1)
            self.assertEqual(spoken.count(main.first_emergency_guidance('A')), 1)
            self.assertIn('A route', self.app._cached_evac_guidance)

    def test_different_zone_preempts_even_while_alarm_active(self):
        self.app._trigger_rag_alert('fire', 'smoke', 'A')
        previous_id = self.app._event_id
        self.app.tts.stop.reset_mock()
        self.app._trigger_rag_alert('B fire', 'smoke', 'B')
        self.assertGreater(self.app._event_id, previous_id)
        self.assertEqual(self.app._event_zone, 'B')
        self.app.tts.stop.assert_called_once()
        self.assertEqual(self.app._jobs.qsize(), 1)
        self.assertFalse(self.app._job_valid({'emergency': True, 'id': previous_id}))

    def test_same_zone_after_guidance_completion_starts_new_event(self):
        with patch('main.rag_manager.search', return_value=[]), \
             patch('main.generate_guidance', return_value=SimpleNamespace(text='route', provider='test')):
            self.app._start_thread(self.app._guidance_worker, 'test-guidance')
            self.app._trigger_rag_alert('fire', 'smoke', 'A')
            deadline = time.monotonic()+2
            while self.app._jobs.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertIsNone(self.app._pending_evac_event)
            previous_id = self.app._event_id
            self.app._clear_alarm()
            self.app._trigger_rag_alert('fire again', 'smoke', 'A')
            self.assertGreater(self.app._event_id, previous_id)

    def monitor(self, analysis, *, offline=False, sensor_mode='demo', frame_id=1):
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        with patch('main.read_temperature', return_value={'temperature':24.5,'humidity':50}), \
             patch('main.read_gas_level', return_value=120), \
             patch('main.read_smoke_level', return_value=80), \
             patch('main.vision_bridge.frame_snapshot', return_value=(frame,time.monotonic(),frame_id,offline)), \
             patch('main.fire_detector.detect_fire', return_value=analysis) as detect, \
             patch.object(config, 'SENSOR_MODE', sensor_mode):
            self.app._monitor_once()
            return detect.call_count

    def test_original_fusion_smoke_contract_is_preserved(self):
        analysis = {'fire_detected':True,'is_real_smoke':True,'status':'REAL_SMOKE_RISING'}
        risk = calculate_risk_level(80,120,{'temperature':24.5},analysis)
        self.assertEqual(risk['level'], 2)
        self.assertFalse(risk['is_early_detection'])
        self.monitor(analysis)
        self.assertEqual(self.app.current_level, 2)
        self.alarm.assert_not_called()

    def test_hardware_mode_does_not_invent_triggered_sensors(self):
        self.monitor({'fire_detected':True,'status':'REAL_FIRE_FLICKERING'}, sensor_mode='hardware')
        self.assertEqual(self.app.current_level, 2)
        self.alarm.assert_not_called()

    def test_same_acquired_frame_is_not_counted_twice(self):
        self.assertEqual(self.monitor({'fire_detected':False,'status':'SAFE'}), 1)
        self.assertEqual(self.monitor({'fire_detected':False,'status':'SAFE'}), 0)

    def test_camera_failure_does_not_reuse_previous_fire(self):
        self.app._last_analysis = {'fire_detected':True,'status':'REAL_FIRE_FLICKERING'}
        self.monitor({}, offline=True)
        self.assertEqual(self.app.current_level, 0)
        self.assertIn('CAMERA_OFFLINE', self.app.current_risk_stats)
        self.alarm.assert_not_called()

    def test_camera_failure_does_not_clear_active_alarm(self):
        self.app._trigger_rag_alert('fire','smoke','A')
        self.app._safe_since = time.monotonic()-10
        self.monitor({}, offline=True)
        self.assertTrue(self.app._alarm_active)

    def test_pending_motion_is_not_evidence_to_clear_an_alarm(self):
        self.app._trigger_rag_alert('fire','smoke','A')
        self.app._safe_since = time.monotonic()-10
        self.monitor({'status':'EVALUATING_FIRE_MOTION','fire_detected':False})
        self.assertTrue(self.app._alarm_active)

    def test_general_query_uses_context_and_local_layout(self):
        with patch('main.rag_manager.search', return_value=[{'page_content':'manual sentence'}]), \
             patch('main.generate_guidance', return_value=SimpleNamespace(text='answer',provider='test')) as generate, \
             patch.object(config,'GEMINI_SEND_LAYOUT',False):
            self.app._start_thread(self.app._guidance_worker,'test-guidance')
            self.app._process_query('B구역 대피경로')
            deadline = time.monotonic()+2
            while self.app._jobs.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertIn('B구역',generate.call_args.args[0])
            self.assertEqual(generate.call_args.kwargs['cloud_context'],'manual sentence')
            self.app.tts.speak_async.assert_called_with('answer',lang='ko',speed=1.0,provider='test')


if __name__ == '__main__':
    unittest.main()
