"""Exercise real detector/motion/fusion logic with controlled YOLO boxes and flow.

No camera, cloud, audio, or downloaded model is required for these regressions.
Actual ONNX/camera smoke checks are separate in tools/check_vision_runtime.py.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import config
from sensors.fusion import calculate_risk_level
from vision import cctv_service, fire_detector as detector


def detections(*items):
    """Items are class id, confidence and coordinates."""
    boxes = [SimpleNamespace(cls=np.array([kind]), conf=np.array([confidence]),
                             xyxy=np.array([bbox])) for kind, confidence, bbox in items]
    return [SimpleNamespace(names={0: 'fire', 1: 'smoke', 2: 'person'}, boxes=boxes)]


def rising(previous, current, *args, **kwargs):
    flow = np.zeros((*current.shape, 2), dtype=np.float32)
    flow[..., 1] = -1
    return flow


def turbulent(previous, current, *args, **kwargs):
    flow = np.zeros((*current.shape, 2), dtype=np.float32)
    flow[:, ::2, 0], flow[:, 1::2, 0] = 1, -1
    return flow


def stationary(previous, current, *args, **kwargs):
    return np.zeros((*current.shape, 2), dtype=np.float32)


class DetectorContractTests(unittest.TestCase):
    def setUp(self):
        self.model = Mock()
        patch.object(detector, 'model', self.model).start()
        patch.object(config, 'BYPASS_MOTION_FILTER', False).start()
        patch.object(config, 'SENSOR_MODE', 'hardware').start()
        self.flow = patch('vision.smoke_motion.cv2.calcOpticalFlowFarneback', side_effect=turbulent).start()
        self.model.predict.return_value = detections((0, .9, [10, 10, 110, 110]))
        self.frame = np.zeros((160, 160, 3), dtype=np.uint8)
        detector.reset_motion()
        self.addCleanup(patch.stopall)
        self.addCleanup(detector.reset_motion)

    def detect(self):
        return detector.detect_fire(self.frame.copy())

    def risk(self, result, smoke=80, gas=120, temperature=24):
        return calculate_risk_level(smoke, gas, {'temperature': temperature}, result)

    def test_fire_waits_for_three_consecutive_motion_pairs(self):
        results = [self.detect() for _ in range(4)]
        self.assertEqual([r['fire_detected'] for r in results], [False, False, False, True])
        self.assertEqual(results[0]['status'], 'WARMING_UP')
        self.assertTrue(results[-1]['is_real_fire'])
        self.assertEqual(self.risk(results[-1])['vision_kind'], 'fire')
        self.assertEqual(self.risk(results[1], smoke=350)['level'], 1)

    def test_smoke_contract_reaches_early_fusion_with_and_without_sensors(self):
        self.model.predict.return_value = detections((1, .85, [10, 10, 110, 110]))
        self.flow.side_effect = rising
        result = [self.detect() for _ in range(4)][-1]
        self.assertTrue(result['is_real_smoke'])
        self.assertFalse(result['fire_detected'])
        for smoke, gas, expected in [(80, 120, 2), (350, 120, 4), (350, 500, 5)]:
            with self.subTest(expected=expected):
                risk = self.risk(result, smoke, gas)
                self.assertEqual(risk['level'], expected)
                self.assertTrue(risk['is_early_detection'])

    def test_motion_interruption_requires_a_new_full_run(self):
        self.detect()  # warmup
        self.detect()
        self.detect()
        self.flow.side_effect = stationary
        self.assertTrue(self.detect()['is_static_photo'])
        self.flow.side_effect = turbulent
        self.assertFalse(self.detect()['fire_detected'])
        self.assertFalse(self.detect()['fire_detected'])
        self.assertTrue(self.detect()['fire_detected'])

    def test_missing_candidate_resets_track(self):
        for _ in range(4):
            self.detect()
        self.model.predict.return_value = detections()
        self.assertEqual(self.detect()['status'], 'SAFE')
        self.model.predict.return_value = detections((0, .9, [10, 10, 110, 110]))
        self.assertEqual(self.detect()['status'], 'WARMING_UP')

    def test_disjoint_candidate_and_resolution_change_restart_verification(self):
        for _ in range(4):
            self.detect()
        self.model.predict.return_value = detections((0, .9, [120, 120, 155, 155]))
        self.assertEqual(self.detect()['status'], 'WARMING_UP')
        self.frame = np.zeros((200, 200, 3), dtype=np.uint8)
        self.assertEqual(self.detect()['status'], 'WARMING_UP')

    def test_smoke_and_fire_keep_separate_histories_and_matching_confidence(self):
        self.model.predict.return_value = detections(
            (1, .99, [10, 10, 60, 60]), (0, .8, [70, 70, 150, 150]))
        self.flow.side_effect = lambda a, b, *args, **kw: stationary(a, b) if b.shape[0] == 50 else turbulent(a, b)
        result = [self.detect() for _ in range(4)][-1]
        self.assertTrue(result['fire_detected'])
        self.assertFalse(result['is_static_photo'])
        self.assertEqual(result['box'], [70, 70, 150, 150])
        self.assertEqual(result['confidence'], .8)

    def test_unknown_and_low_confidence_classes_cannot_confirm_fire(self):
        self.model.predict.return_value = detections((2, .99, [10, 10, 110, 110]), (0, .2, [10, 10, 110, 110]))
        self.assertEqual(self.detect()['status'], 'SAFE')

    def test_every_error_has_complete_contract_and_no_confirmation(self):
        cases = [(None, 'MODEL_NOT_INITIALIZED'), (Mock(), 'ANALYSIS_ERROR')]
        cases[1][0].predict.side_effect = RuntimeError('inference failure')
        for model, status in cases:
            with self.subTest(status=status), patch.object(detector, 'model', model):
                result = self.detect()
                self.assertEqual(result['status'], status)
                self.assertEqual(result['contract_version'], 1)
                self.assertFalse(result['fire_detected'] or result['is_real_smoke'])
                self.assertEqual(self.risk(result, smoke=350)['level'], 1)
        self.assertEqual(detector.detect_fire(np.zeros((0, 0, 3), dtype=np.uint8))['status'], 'INVALID_INPUT')
        self.detect()
        self.flow.side_effect = RuntimeError('flow failure')
        self.assertEqual(self.detect()['status'], 'MOTION_ERROR')

    def test_demo_bypass_is_explicit_and_cannot_apply_in_hardware(self):
        self.flow.side_effect = stationary
        with patch.object(config, 'BYPASS_MOTION_FILTER', True):
            self.assertFalse(self.detect()['fire_detected'])
            with patch.object(config, 'SENSOR_MODE', 'demo'):
                result = self.detect()
                self.assertTrue(result['demo_bypass'])
                self.assertFalse(result['is_real_fire'])
            self.assertEqual(self.risk(result)['level'], 0)

    def test_legacy_smoke_flag_and_bool_still_work(self):
        risk = self.risk({'fire_detected': True, 'is_real_smoke': True})
        self.assertTrue(risk['is_early_detection'])
        self.assertEqual(risk['vision_kind'], 'smoke')
        self.assertEqual(self.risk(True)['level'], 2)


class CaptureSnapshotTests(unittest.TestCase):
    def tearDown(self):
        cctv_service._mark_camera_offline()

    def test_snapshot_preserves_capture_time_and_sequence_without_refreshing_it(self):
        frame = np.zeros((20, 20, 3), dtype=np.uint8)
        with patch('vision.cctv_service.time.monotonic', return_value=123.0):
            cctv_service._publish_frame(frame)
        captured = cctv_service.frame_snapshot()
        self.assertIs(captured[0], frame)
        self.assertEqual(captured[1], 123.0)
        self.assertEqual(cctv_service.frame_snapshot()[1:3], captured[1:3])
        cctv_service._mark_camera_offline()
        self.assertIsNone(cctv_service.frame_snapshot()[0])
        self.assertTrue(cctv_service.frame_snapshot()[3])
