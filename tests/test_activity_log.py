"""Test logging with a fake client and a temporary data directory."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from test_rdp import outs

spec = importlib.util.spec_from_file_location('activity_log', Path(outs.__file__).parent / 'activity_log.py')
logs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logs)


class LogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, value in [('GUI_MODE', False), ('SESSION_LOG', None), ('LAST_LOG_PATH', None)]:
            state = patch.object(outs, name, value)
            state.start()
            self.addCleanup(state.stop)
        environment = patch.dict(os.environ, {'XDG_DATA_HOME': str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)

    def test_private_files_and_xdg_location(self):
        session = logs.SessionLog()
        self.addCleanup(session.close)
        self.assertEqual(session.path.parent, self.root / 'logs/outsource')
        self.assertEqual(session.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(session.path.parent.stat().st_mode & 0o777, 0o700)
        session.write('test', exit_code=0)
        self.assertEqual(json.loads(session.path.read_text())['exit_code'], 0)

    def test_main_records_result_and_no_command_arguments(self):
        with patch.object(outs, 'run_main', return_value=0):
            self.assertEqual(outs.main(['connect', 'a' * 32, '--gui', 'secret-argument']), 0)
        text = outs.LAST_LOG_PATH.read_text()
        self.assertIn('a' * 32, text)
        self.assertIn('finished', text)
        self.assertNotIn('secret-argument', text)
        self.assertIsNone(outs.SESSION_LOG)

    def test_exception_message_is_not_logged(self):
        with patch.object(outs, 'run_main', side_effect=outs.OutsError('secret-path-and-password')):
            with self.assertRaises(outs.OutsError):
                outs.main(['connect', 'a' * 32])
        text = outs.LAST_LOG_PATH.read_text()
        self.assertIn('OutsError', text)
        self.assertIn('error', text)
        self.assertNotIn('secret-path-and-password', text)

    def test_cancel_has_a_separate_event(self):
        with patch.object(outs, 'run_main', side_effect=outs.Cancelled):
            with self.assertRaises(outs.Cancelled):
                outs.main(['new'])
        self.assertIn('canceled by user', outs.LAST_LOG_PATH.read_text())

    def test_diagnostics_discard_raw_text_and_unknown_codes(self):
        session = logs.SessionLog()
        self.addCleanup(session.close)
        session.diagnostic(b'/p:secret-credential ERRCONNECT_LOGON_FAILURE ERRCONNECT_PRIVATE_TOKEN\n')
        session.diagnostic(b'password=secret connection refused for secret-host\n')
        session.diagnostic(b'ERRCONNECT_LOGON_FAILURE\n')
        text = session.path.read_text()
        self.assertIn('ERRCONNECT_LOGON_FAILURE', text)
        self.assertIn('The server refused the connection.', text)
        self.assertNotIn('secret', text)
        self.assertNotIn('PRIVATE_TOKEN', text)
        self.assertEqual(text.count('ERRCONNECT_LOGON_FAILURE'), 1)

    def test_real_rdp_stderr_is_filtered_and_password_buffer_wiped(self):
        client = self.root / 'fake-rdp'
        client.write_text('#!' + sys.executable + '\n' + '''import sys
payload = sys.stdin.buffer.read()
assert b'/p:test-secret' in payload
sys.stderr.write('password=test-secret ERRCONNECT_LOGON_FAILURE\\n')
sys.exit(5)
''')
        client.chmod(0o700)
        session = logs.SessionLog()
        self.addCleanup(session.close)
        password = bytearray(b'test-secret')
        with patch.object(outs, 'SESSION_LOG', session), patch.object(outs, 'GUI_MODE', True), \
             patch.object(outs, 'active_vpn_names', return_value=[]):
            result = outs.run_rdp_with_password([str(client), '/v:test-host'], password, False)
        self.assertEqual(result, 5)
        self.assertEqual(set(password), {0})
        text = session.path.read_text()
        self.assertIn('ERRCONNECT_LOGON_FAILURE', text)
        self.assertIn('"exit_code": 5', text)
        self.assertNotIn('test-secret', text)
        self.assertNotIn('test-host', text)

    def test_retention_skips_open_sessions(self):
        session = logs.SessionLog()
        self.addCleanup(session.close)
        directory = session.path.parent
        old = directory / 'outs-old.log'
        old.write_text('old')
        timestamp = time.time() - logs.MAX_AGE - 10
        os.utime(old, (timestamp, timestamp))
        os.utime(session.path, (timestamp, timestamp))
        logs.prune(directory)
        self.assertFalse(old.exists())
        self.assertTrue(session.path.exists())
        session.close()
        logs.prune(directory)
        self.assertFalse(session.path.exists())

    def test_rdp_close_does_not_raise_gui_error_but_failures_do(self):
        connections = outs.connection_tools()
        connection = {'id': 'a' * 32, 'name': 'Test', 'type': 'rdp', 'record': {}}
        for code, diagnostic, expected in [
            (131, 'ERRCONNECT_CONNECT_CANCELLED', 0),
            (145, '', 0), (1, '', 0), (2, '', 0), (11, '', 0),
            (131, '', 131),
            (131, 'ERRCONNECT_AUTHENTICATION_FAILED', 131),
            (132, 'ERRCONNECT_CONNECT_CANCELLED', 132),
        ]:
            with self.subTest(code=code, diagnostic=diagnostic):
                client = self.root / 'fake-rdp'
                client.write_text('#!' + sys.executable + '\nimport sys\n'
                                  'sys.stdin.buffer.read()\n'
                                  f'sys.stderr.write({diagnostic!r})\n'
                                  f'sys.exit({code})\n')
                client.chmod(0o700)
                session = logs.SessionLog()
                self.addCleanup(session.close)
                def launch(*args):
                    return outs.run_rdp_with_password([str(client)], bytearray(b'test'), False)
                with patch.object(outs, 'SESSION_LOG', session), \
                     patch.object(outs, 'GUI_MODE', True), \
                     patch.object(outs, 'active_vpn_names', return_value=[]), \
                     patch.object(outs, 'dispatch_action', side_effect=launch), \
                     patch.object(connections, 'load', return_value=connection):
                    if expected:
                        with self.assertRaises(outs.OutsError):
                            connections.connect(outs, connection['id'])
                    else:
                        self.assertEqual(connections.connect(outs, connection['id']), 0)
                self.assertIn(f'"exit_code": {code}', session.path.read_text())

    def test_viewer_exit_is_not_interpreted_as_rdp_cancellation(self):
        import io
        from unittest.mock import Mock
        process = Mock(stderr=io.BytesIO(b'ERRCONNECT_CONNECT_CANCELLED'))
        process.wait.return_value = 131
        with patch.object(outs, 'GUI_MODE', True):
            self.assertEqual(outs.wait_for_client(process), 131)

    def test_number_and_size_limits(self):
        directory = logs.log_directory()
        directory.mkdir(parents=True)
        for i in range(8):
            (directory / f'outs-{i}.log').write_text('old')
        with patch.object(logs, 'MAX_FILES', 3), patch.object(logs, 'MAX_BYTES', 250):
            session = logs.SessionLog()
            self.addCleanup(session.close)
            self.assertLessEqual(len(list(directory.glob('outs-*.log'))), 3)
            for _ in range(20):
                session.write('test', data='x' * 200)
            self.assertIn('Log size limit reached', session.path.read_text())
            self.assertLess(session.path.stat().st_size, 350)


if __name__ == '__main__':
    unittest.main()
