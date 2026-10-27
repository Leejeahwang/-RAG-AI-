import os
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools.install_terminal_autostart import build_desktop, desktop_argument, stop_background_service
from tools.run_terminal import terminal_command, main, run_inside


class TerminalAutostartTests(unittest.TestCase):
    def test_entry_launches_gui_wrapper_without_service_flags_or_secrets(self):
        entry = build_desktop('/home/raspi/My Project', '/home/raspi/My Project/.venv-py311/bin/python')
        self.assertIn('run_terminal.py"', entry)
        self.assertIn('Terminal=false', entry)
        self.assertNotIn('--service', entry)
        self.assertNotIn('GEMINI_API_KEY', entry)
        self.assertNotIn('WorkingDirectory=', entry)
        self.assertIn('50%%', desktop_argument('/home/50%'))
        self.assertIn('\\\\$', desktop_argument('/home/$name'))
        with self.assertRaises(ValueError):
            desktop_argument('bad\npath')

    def test_terminal_command_keeps_spaces_and_special_characters_literal(self):
        args = terminal_command('/usr/bin/lxterminal', '/home/a b/.venv/bin/python', '/home/a b')
        self.assertIn('--no-remote', args)
        self.assertIn('--working-directory=/home/a b', args)
        command = args[-1].removeprefix('--command=')
        self.assertEqual(shlex.split(command), ['/home/a b/.venv/bin/python', '-u',
            str(Path('/home/a b')/'tools'/'run_terminal.py'), '--inside'])

    def test_existing_background_service_is_disabled_before_terminal_install(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root/'systemd'/'user'/'edge-saver.service'
            path.parent.mkdir(parents=True)
            path.write_text('[Service]')
            with patch('tools.install_terminal_autostart.connect_user_manager', return_value={}), \
                    patch('tools.install_terminal_autostart.subprocess.run') as run:
                stop_background_service(root, 1000)
            self.assertEqual(run.call_args.args[0], ['systemctl', '--user', 'disable', '--now', 'edge-saver.service'])

    def test_no_service_does_not_require_a_user_manager(self):
        with tempfile.TemporaryDirectory() as folder, patch('tools.install_terminal_autostart.connect_user_manager') as connect:
            stop_background_service(Path(folder), 1000)
        connect.assert_not_called()

    def test_inside_runs_the_original_main_with_terminal_input_inherited(self):
        fake_fcntl = Mock(LOCK_EX=2, LOCK_NB=4)
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, {'fcntl': fake_fcntl}), \
                patch('tools.run_terminal.ROOT', Path(folder)), \
                patch('tools.run_terminal.subprocess.run', return_value=Mock(returncode=0)) as run:
            self.assertEqual(run_inside(), 0)
            args = run.call_args.args[0]
            self.assertTrue(args[-1].endswith('main.py'))
            self.assertNotIn('--service', args)
            self.assertNotIn('stdin', run.call_args.kwargs)

    def test_duplicate_desktop_session_does_not_start_another_main(self):
        fake_fcntl = Mock(LOCK_EX=2, LOCK_NB=4)
        fake_fcntl.flock.side_effect = BlockingIOError
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, {'fcntl': fake_fcntl}), \
                patch('tools.run_terminal.ROOT', Path(folder)), patch('tools.run_terminal.subprocess.run') as run:
            self.assertEqual(run_inside(), 0)
            run.assert_not_called()

    def test_gui_required_for_opening_terminal(self):
        with patch('tools.run_terminal.sys.platform', 'linux'), patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                main([])

    def test_gui_launch_returns_without_waiting_for_main_to_exit(self):
        with patch('tools.run_terminal.sys.platform', 'linux'), patch.dict(os.environ, {'DISPLAY': ':10'}), \
                patch('tools.run_terminal.shutil.which', return_value='/usr/bin/lxterminal'), \
                patch('tools.run_terminal.subprocess.Popen') as spawn:
            self.assertEqual(main([]), 0)
        self.assertTrue(spawn.call_args.kwargs['start_new_session'])
        self.assertNotIn('env', spawn.call_args.kwargs)


if __name__ == '__main__':
    unittest.main()
