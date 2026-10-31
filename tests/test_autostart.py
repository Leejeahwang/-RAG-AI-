"""No device/model loading or host service installation is performed here."""
import json
import os
from pathlib import Path
import signal
import threading
import unittest
from unittest.mock import Mock, patch

import main
from tools.install_autostart import build_unit, connect_user_manager, verify_unit
from tools.run_service import prepare_audio, select_sink


class AutostartTests(unittest.TestCase):
    def test_remote_private_bus_is_replaced_without_changing_parent_environment(self):
        with patch.dict(os.environ, {'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/tmp/xrdp-private',
                                     'XDG_RUNTIME_DIR': '/tmp/remote'}), \
                patch('tools.install_autostart.subprocess.run', return_value=Mock(returncode=0)) as run:
            env = connect_user_manager(1000)
            self.assertEqual(env['DBUS_SESSION_BUS_ADDRESS'], 'unix:path=/run/user/1000/bus')
            self.assertEqual(env['XDG_RUNTIME_DIR'], '/run/user/1000')
            self.assertEqual(os.environ['XDG_RUNTIME_DIR'], '/tmp/remote')
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.kwargs['env'], env)

    def test_missing_manager_is_started_then_rechecked(self):
        with patch('tools.install_autostart.subprocess.run',
                   side_effect=[Mock(returncode=1), Mock(returncode=0), Mock(returncode=0)]) as run:
            connect_user_manager(1000)
        self.assertEqual(run.call_args_list[1].args[0], ['sudo', 'systemctl', 'start', 'user@1000.service'])
        self.assertEqual(run.call_args_list[2].kwargs['env']['XDG_RUNTIME_DIR'], '/run/user/1000')

    def test_unavailable_user_bus_reports_actionable_error(self):
        with patch('tools.install_autostart.subprocess.run',
                   side_effect=[Mock(returncode=1), Mock(returncode=0), Mock(returncode=1)]):
            with self.assertRaisesRegex(RuntimeError, 'dbus-user-session'):
                connect_user_manager(1000)

    def test_service_run_survives_no_stdin_and_exits_when_stopped(self):
        app = main.EdgeSaver()
        initialized = threading.Event()
        with patch.object(app, 'initialize', side_effect=initialized.set), \
                patch('main.PromptSession') as prompt, patch('builtins.input') as stdin:
            thread = threading.Thread(target=app.run, kwargs={'service': True})
            thread.start()
            try:
                self.assertTrue(initialized.wait(1))
                self.assertTrue(thread.is_alive())
                prompt.assert_not_called()
                stdin.assert_not_called()
            finally:
                app._stop.set()
                thread.join(timeout=1)
            self.assertFalse(thread.is_alive())

    def test_sigterm_cleans_up_and_restores_handler(self):
        app = Mock()
        handlers = []
        def register(sig, handler):
            handlers.append(handler)
            return signal.SIG_DFL
        app.run.side_effect = lambda **kwargs: handlers[0](signal.SIGTERM, None)
        with patch('main.EdgeSaver', return_value=app), patch('main.signal.signal', side_effect=register):
            main.main(['--service'])
        app.run.assert_called_once_with(service=True)
        app.cleanup.assert_called_once()
        self.assertEqual(handlers[-1], signal.SIG_DFL)

    def test_init_failure_is_not_swallowed_and_still_cleans_up(self):
        app = Mock()
        app.run.side_effect = RuntimeError('initialization failed')
        with patch('main.EdgeSaver', return_value=app), patch('main.signal.signal'):
            with self.assertRaisesRegex(RuntimeError, 'initialization failed'):
                main.main(['--service'])
        app.cleanup.assert_called_once()

    def test_user_unit_uses_venv_and_does_not_embed_secrets(self):
        unit = build_unit('/home/raspi/My Project', '/home/raspi/My Project/.venv-py311/bin/python')
        self.assertIn('WantedBy=default.target', unit)
        self.assertIn('StandardInput=null', unit)
        self.assertIn('Restart=on-failure', unit)
        self.assertIn('"/home/raspi/My Project/.venv-py311/bin/python"', unit)
        self.assertIn('\nWorkingDirectory=/home/raspi/My Project\n', unit)
        self.assertNotIn('WorkingDirectory="', unit)
        self.assertIn('run_service.py" --audio pulse', unit)
        self.assertIn('UnsetEnvironment=PULSE_SINK', unit)
        self.assertNotIn('GEMINI_API_KEY', unit)
        self.assertNotIn('User=root', unit)
        self.assertNotIn('EnvironmentFile=', unit)
        with self.assertRaises(ValueError):
            build_unit('/bad\npath', '/python')
        escaped = build_unit('/home/50% $x', '/home/50% $x/bin/python')
        self.assertIn('50%% $$x/bin/python', escaped)
        self.assertIn('WorkingDirectory=/home/50%% $x\n', escaped)
        self.assertIn('Environment="PULSE_SINK=alsa_output.test"',
                      build_unit('/project', '/python', sink='alsa_output.test'))
        self.assertNotIn('pipewire.service', build_unit('/project', '/python', audio='alsa'))

    def test_verify_checks_temporary_unit_before_install_and_preserves_diagnostics(self):
        unit = build_unit('/project', '/usr/bin/python3', audio='alsa')
        def check(command, **kwargs):
            self.assertEqual(command[:3], ['systemd-analyze', '--user', 'verify'])
            self.assertEqual(Path(command[3]).read_text(encoding='utf-8'), unit)
            self.assertEqual(kwargs['env'], {'XDG_RUNTIME_DIR': '/run/user/1000'})
            return Mock(returncode=0)
        with patch('tools.install_autostart.subprocess.run', side_effect=check):
            verify_unit(unit, {'XDG_RUNTIME_DIR': '/run/user/1000'})
        with patch('tools.install_autostart.subprocess.run',
                   return_value=Mock(returncode=1, stderr='WorkingDirectory path is not absolute')):
            with self.assertRaisesRegex(RuntimeError, 'WorkingDirectory path is not absolute'):
                verify_unit(unit, {})

    def test_sink_selection_uses_default_including_remote_output(self):
        sinks = [{'name': 'auto_null'}, {'name': 'xrdp-sink'}, {'name': 'alsa_output.usb-speaker'}]
        self.assertEqual(select_sink(sinks, default='xrdp-sink'), 'xrdp-sink')
        self.assertEqual(select_sink(sinks[:2]), 'xrdp-sink')
        self.assertIsNone(select_sink(sinks[:1]))
        self.assertEqual(select_sink(sinks, requested='xrdp-sink'), 'xrdp-sink')
        self.assertIsNone(select_sink(sinks, requested='missing-speaker'))

    def test_pulse_wait_sets_only_process_output_without_global_default_change(self):
        sink = 'alsa_output.usb-speaker'
        outputs = [Mock(stdout=json.dumps([{'name': sink}])), Mock(stdout=sink+'\n')]
        with patch.dict(os.environ, {}, clear=True), patch('tools.run_service.shutil.which', return_value='/bin/pactl'), \
                patch('tools.run_service.subprocess.run', side_effect=outputs) as command:
            prepare_audio('pulse', timeout=5)
            self.assertEqual(os.environ['SDL_AUDIODRIVER'], 'pulseaudio')
            self.assertNotIn('PULSE_SINK', os.environ)
            self.assertFalse(any('set-default-sink' in call.args[0] for call in command.call_args_list))

    def test_audio_timeout_does_not_block_monitoring(self):
        with patch.dict(os.environ), patch('tools.run_service.shutil.which', return_value='/bin/pactl'), \
                patch('tools.run_service.time.monotonic', side_effect=[0, 6]):
            self.assertFalse(prepare_audio('pulse'))

    def test_missing_audio_probe_does_not_block_monitoring(self):
        with patch.dict(os.environ), patch('tools.run_service.shutil.which', return_value=None):
            self.assertFalse(prepare_audio('pulse'))

    def test_launcher_runs_monitoring_even_if_no_audio_yet(self):
        from tools.run_service import main as launch
        with patch('tools.run_service.sys.platform', 'linux'), patch('tools.run_service.os.chdir'), \
                patch('dotenv.load_dotenv'), patch('tools.run_service.prepare_audio', return_value=False), \
                patch('tools.run_service.os.execv') as execute:
            launch([])
        self.assertEqual(execute.call_args.args[1][-1], '--service')


if __name__ == '__main__':
    unittest.main()
