"""Signály posíláme jen vlastním procesům s falešnými klíči a klienty."""

import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from test_rdp import outs


FIXTURE = r'''
import importlib.machinery, importlib.util, json, os, sys
from pathlib import Path
loader = importlib.machinery.SourceFileLoader('outs_signal_fixture', sys.argv[1])
spec = importlib.util.spec_from_loader(loader.name, loader)
outs = importlib.util.module_from_spec(spec)
loader.exec_module(outs)
outs.install_signal_handlers()
root, mode = Path(sys.argv[2]), sys.argv[3]
client = root / 'fake-client'
'''

CLIENT = r'''
import json, os, sys, time
from pathlib import Path
root = Path(__file__).parent
args = sys.argv[1:]
mode = os.environ['FIXTURE_MODE']
if mode == 'vpn':
    state = root / 'nm-profiles.json'
    profiles = json.loads(state.read_text()) if state.exists() else {}
    if args[0] == '-g':
        selector, value = args[4:]
        matches = [uid for uid, name in profiles.items()
                   if (uid if selector == 'uuid' else name) == value]
        print('\n'.join(matches))
        sys.exit(0 if matches else 10)
    if args[1] == 'delete':
        profiles.pop(args[3], None)
        state.write_text(json.dumps(profiles))
        sys.exit(0)
    assert args[1] == 'import', args
    profiles['22222222-2222-2222-2222-222222222222'] = Path(args[-1]).stem
    state.write_text(json.dumps(profiles))
    certificate = Path(os.environ['NM_CERT_PATH']) / 'nm-openvpn' / 'key.pem'
    certificate.parent.mkdir()
    certificate.write_text('FAKE-KEY')
    ready = {'pid': os.getpid()}
elif mode == 'ssh':
    ready = {'pid': os.getpid(), 'key': args[args.index('-i') + 1]}
else:
    assert mode == 'rdp'
    ready = {'pid': os.getpid()}
ready_path = root / 'ready.tmp'
ready_path.write_text(json.dumps(ready))
ready_path.replace(root / 'ready.json')
time.sleep(60)
'''

FIXTURE_END = r'''
client.chmod(0o700)
outs.require_program = lambda _: str(client)
if mode == 'ssh':
    outs.lookup_keepass_attachment = lambda _: bytearray(b'FAKE-SSH-KEY')
    config = {'ssh': [{'id': 'fixture', 'host': 'example.test',
                      'keepass': {'attachment': 'fake.key'}}]}
    outs.run_main = lambda _: outs.handle_ssh('fixture', config, ['fixture'])
elif mode == 'vpn':
    outs.lookup_keepass_vpn = lambda _: (bytearray(b'FAKE-PROFILE'), 'fixture', bytearray(b'FAKE-SECRET'))
    config = {'vpn': [{'id': 'fixture', 'type': 'openvpn', 'keepass': {'uuid': '1' * 32}}]}
    outs.run_main = lambda _: outs.handle_vpn('fixture', config, 'vpn-up', ['fixture'])
else:
    outs.run_main = lambda _: outs.run_rdp([str(client)], detached=False)
raise SystemExit(outs.main(['fixture', mode, 'fixture']))
'''


class SignalTests(unittest.TestCase):
    def test_import_does_not_replace_signal_handlers(self):
        with patch.object(signal, 'signal') as install:
            runpy.run_path(outs.__file__)
        install.assert_not_called()

    def interrupted_fixture(self, mode, signum):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'runtime'
            runtime.mkdir(mode=0o700)
            # Vložený klient je samostatný skutečný proces, nikoli mock Popen.
            script = (FIXTURE + "client.write_text('#!' + sys.executable + '\\n' + "
                      + repr(CLIENT) + ')\n' + FIXTURE_END)
            process = subprocess.Popen(
                [sys.executable, '-c', script, outs.__file__, directory, mode],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={**os.environ, 'TMPDIR': directory, 'XDG_RUNTIME_DIR': str(runtime),
                     'XDG_DATA_HOME': str(root / 'data'), 'FIXTURE_MODE': mode},
            )
            ready_path = root / 'ready.json'
            ready = None
            try:
                deadline = time.monotonic() + 5
                while not ready_path.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(ready_path.exists(), 'Falešný klient se nespustil.')
                ready = json.loads(ready_path.read_text())
                process.send_signal(signum)
                result = process.wait(timeout=8)
                self.assertEqual(result, 128 + signum)
                with self.assertRaises(ProcessLookupError):
                    os.kill(ready['pid'], 0)
                if mode == 'ssh':
                    self.assertFalse(Path(ready['key']).exists())
                if mode == 'vpn':
                    self.assertEqual(json.loads((root / 'nm-profiles.json').read_text()), {})
                    self.assertFalse(list(runtime.rglob('state.json')))
                    self.assertFalse(list(runtime.rglob('key.pem')))
                    self.assertFalse(list(runtime.rglob('*.ovpn')))
                log = next((root / 'data' / 'logs' / 'outsource').glob('outs-*.log')).read_text()
                self.assertIn('zrušeno signálem', log)
                self.assertIn(f'"signál": {signum}', log)
                self.assertNotIn('FAKE-SECRET', log)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                if ready is not None:
                    try:
                        os.kill(ready['pid'], signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.stdout.close()
                process.stderr.close()

    def test_terminal_signals_remove_ssh_key_and_stop_waited_child(self):
        for signum in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signum=signum):
                self.interrupted_fixture('ssh', signum)

    def test_terminal_signals_roll_back_interrupted_vpn_import(self):
        for signum in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signum=signum):
                self.interrupted_fixture('vpn', signum)

    def test_terminal_signals_stop_foreground_rdp_child(self):
        for signum in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signum=signum):
                self.interrupted_fixture('rdp', signum)


if __name__ == '__main__':
    unittest.main()
