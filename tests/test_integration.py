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
                self.notify.assert_called_once_with(zone='B', risk_level=5, sensor_details='smoke')
                spoken = [c.args[0] for c in self.app.tts.speak_async.call_args_list]
                self.assertIn(main.EMERGENCY_GUIDANCE, spoken)
            finally:
                release.set()
            deadline = time.monotonic()+2
            while self.app._jobs.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(self.app._jobs.unfinished_tasks, 0)
            self.assertNotIn('obsolete answer', [c.args[0] for c in self.app.tts.speak_async.call_args_list])

    def test_recovery_discards_delayed_emergency_result(self):
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
            self.assertNotIn('expired guidance', [c.args[0] for c in self.app.tts.speak_async.call_args_list])

    def test_no_duplicate_alarm_or_normal_speech_during_emergency(self):
        self.app._trigger_rag_alert('fire', 'smoke', 'A')
        self.app._trigger_rag_alert('fire', 'smoke', 'A')
        self.app._process_query('question')
        self.alarm.assert_called_once()
        self.assertEqual(self.app._jobs.qsize(), 1)

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
