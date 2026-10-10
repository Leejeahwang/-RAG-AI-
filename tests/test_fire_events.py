import time
import unittest
from dataclasses import asdict, replace
from unittest.mock import Mock, patch

import requests
import main
from alerts.fire_events import FireEvent, FireEventLink
from rag.layout import evacuation_for_zone


class FireEventsTests(unittest.TestCase):
    def setUp(self):
        self.app = main.EdgeSaver()
        self.app.local_zone = 'B'
        self.app.detection_zone = 'B'
        self.app._tts = Mock()
        self.app._tts.is_speaking.return_value = False
        for name in ('trigger_alarm', 'stop_siren', 'send_alert'):
            patch('main.'+name).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(self.app.cleanup)
        self.event = FireEvent('device-A', 100, 1, 'incident-A', 'A', True, 5, 'local smoke')

    def test_origin_and_listener_use_different_routes(self):
        self.app.handle_fire_event(self.event)
        speech = [call.args[0] for call in self.app.tts.speak_async.call_args_list]
        self.assertIn(evacuation_for_zone('B', fire_zone='A'), speech)
        self.assertNotIn(evacuation_for_zone('A', fire_zone='A'), speech)
        self.assertEqual(self.app._event_zone, 'A')
        self.assertEqual(speech[0], main.first_emergency_guidance('A'))
        self.assertNotIn('B구역에서', speech[0])
        self.assertTrue(self.app._cached_evac_guidance.startswith('A구역에서'))

    def test_local_first_guidance_names_each_fire_zone(self):
        for zone in ('A', 'B', 'C'):
            with self.subTest(zone=zone):
                self.app.local_zone = zone
                self.app.detection_zone = zone
                self.app._activate_local_fire('fire', 'smoke')
                speech = self.app.tts.speak_async.call_args_list[-2].args[0]
                self.assertTrue(speech.startswith(f'{zone}구역에서 화재 위험이 감지되었습니다.'))
                self.app._clear_alarm()

    def test_duplicate_stale_and_old_incident_clear(self):
        self.app.handle_fire_event(self.event)
        self.app.handle_fire_event(self.event)
        self.assertEqual(self.app._event_id, 1)
        newer = replace(self.event, sequence=2, incident_id='new-incident')
        self.app.handle_fire_event(newer)
        self.app.handle_fire_event(replace(self.event, sequence=3, active=False))
        self.assertTrue(self.app._alarm_active)
        self.app.handle_fire_event(replace(newer, sequence=4, active=False))
        self.assertFalse(self.app._alarm_active)
        self.app.handle_fire_event(newer)
        self.assertFalse(self.app._alarm_active)

    def test_local_detection_a_announces_b_and_sends_a(self):
        self.app.detection_zone = 'A'
        self.app._alert_link = Mock()
        self.app._activate_local_fire('A fire', 'smoke', 5)
        spoken = [call.args[0] for call in self.app.tts.speak_async.call_args_list]
        self.assertEqual(spoken[0], main.first_emergency_guidance('A'))
        self.assertIn(evacuation_for_zone('B', fire_zone='A'), spoken)
        self.app._clear_alarm()
        emitted = [call.args[0] for call in self.app._alert_link.publish.call_args_list]
        self.assertEqual([event.fire_zone for event in emitted], ['A', 'A'])
        self.assertEqual([event.active for event in emitted], [True, False])

    def test_local_recovery_cannot_clear_remote_and_does_not_relay(self):
        link = self.app._alert_link = Mock()
        self.app.handle_fire_event(self.event)
        link.publish.assert_not_called()
        self.app._activate_local_fire('local fire', 'local smoke')
        self.app._clear_alarm()
        self.assertTrue(self.app._alarm_active)
        self.assertEqual(self.app._event_zone, 'A')
        emitted = [call.args[0] for call in link.publish.call_args_list]
        self.assertEqual([event.active for event in emitted], [True, False])
        self.assertTrue(all(event.fire_zone == 'B' for event in emitted))

    def test_clear_one_origin_keeps_another_active(self):
        self.app.handle_fire_event(self.event)
        other = replace(self.event, source_node='device-C', incident_id='incident-C', fire_zone='C')
        self.app.handle_fire_event(other)
        self.app.handle_fire_event(replace(other, sequence=2, active=False))
        self.assertTrue(self.app._alarm_active)
        self.assertEqual(self.app._event_zone, 'A')
        self.app.handle_fire_event(replace(self.event, sequence=2, active=False))
        self.assertFalse(self.app._alarm_active)

    def test_own_echo_ignored(self):
        self.app.handle_fire_event(replace(self.event, source_node=self.app._node_id))
        self.assertFalse(self.app._alarm_active)

    def test_repeat_audio_also_prints_the_guidance(self):
        self.app._alarm_active = True
        self.app._event_zone = 'A'
        self.app._cached_evac_guidance = 'stored route and precautions'
        with patch.object(self.app._stop, 'wait', side_effect=[False, True]), \
                patch('main.time.monotonic', side_effect=[0, 30, 30]), patch('builtins.print') as output:
            self.app._run_evac_broadcast()
        output.assert_any_call('stored route and precautions')
        self.app.tts.speak_async.assert_called_once()

    def test_http_auth_validation_and_real_sender_receiver(self):
        receiver = FireEventLink('127.0.0.1', 0, 'test-secret', [], self.app.handle_fire_event, .05)
        receiver.start()
        self.addCleanup(receiver.close)
        url = f'http://127.0.0.1:{receiver.port}'
        self.assertEqual(requests.post(url+'/fire-event', json=asdict(self.event), timeout=2).status_code, 401)
        self.assertFalse(self.app._alarm_active)
        invalid = asdict(self.event)
        invalid['fire_zone'] = 'D'
        self.assertEqual(requests.post(url+'/fire-event', json=invalid,
            headers={'X-Alert-Token': 'test-secret'}, timeout=2).status_code, 400)
        sender = FireEventLink('127.0.0.1', 0, 'test-secret', [url], lambda event: None, .05)
        sender.start()
        self.addCleanup(sender.close)
        sender.publish(self.event)
        deadline = time.monotonic()+3
        while not self.app._alarm_active and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(self.app._alarm_active)
        sender.publish(replace(self.event, sequence=2, active=False))
        while self.app._alarm_active and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(self.app._alarm_active)

    def test_invalid_payload_and_missing_auth_configuration(self):
        for event in (replace(self.event, sequence=True), replace(self.event, active=1),
                      replace(self.event, source_epoch=float('nan'))):
            with self.assertRaises(ValueError):
                FireEvent.parse(asdict(event))
        with self.assertRaises(ValueError):
            FireEventLink('127.0.0.1', 0, '', [], lambda event: None)


if __name__ == '__main__':
    unittest.main()
