"""Test the wizard in a temporary profile without connecting to servers."""
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from test_rdp import outs

connections = outs.connection_tools()


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.api = SimpleNamespace(**vars(outs))
        self.api.CONFIG_HOME = self.root / 'config'
        self.api.applications_dir = lambda: self.root / 'applications'
        self.api.launcher_executable = lambda: Path('/run/current-system/sw/bin/outs')
        self.api.GUI_MODE = True
        self.api.LOCAL_CONFIG = self.root / 'config.local.json'
        self.connection = {
            'version': 1, 'id': 'a' * 32, 'name': 'Server – café', 'type': 'ssh',
            'record': {'host': 'pracovni-alias'},
        }

    def test_create_edit_delete_and_stale_edit(self):
        connections.save(self.api, self.connection)
        path = connections.connection_path(self.api, self.connection['id'])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        desktop = connections.desktop_path(self.api, self.connection)
        self.assertIn('Terminal=false', desktop.read_text())
        self.assertIn('"/run/current-system/sw/bin/outs-terminal"', desktop.read_text())
        self.assertIn('--gapplication-app-id=org.nixon.outsource.ssh.c' + 'a' * 32, desktop.read_text())
        self.assertIn('StartupWMClass=org.nixon.outsource.ssh.c' + 'a' * 32, desktop.read_text())
        self.assertIn('Icon=' + str(self.api.ROOT / 'assets/outs-ssh.svg'), desktop.read_text())
        self.assertIn('"connect" "' + 'a' * 32 + '"', desktop.read_text())
        previous = copy.deepcopy(self.connection)
        self.connection['name'] = 'Updated café server'
        connections.save(self.api, self.connection, previous)
        with self.assertRaises(outs.OutsError):
            connections.save(self.api, previous, previous)
        self.assertIn('Updated café server', desktop.read_text())
        connections.remove_connection(self.api, self.connection)
        self.assertFalse(path.exists())
        self.assertFalse(desktop.exists())

    def test_failed_desktop_write_rolls_back_connection(self):
        original_write = connections.atomic_write
        def fail_desktop(path, data):
            if path.suffix == '.desktop':
                raise OSError('test')
            original_write(path, data)
        with patch.object(connections, 'atomic_write', side_effect=fail_desktop):
            with self.assertRaises(OSError):
                connections.save(self.api, self.connection)
        self.assertFalse(connections.connection_path(self.api, self.connection['id']).exists())

    def test_invalid_values_do_not_write_files(self):
        for update in [{'id': '../escape'}, {'name': 'name\nExec=bad'},
                       {'record': {'host': '-oProxyCommand=bad'}},
                       {'record': {'host': 'server', 'port': 0}},
                       {'record': {'host': 'server', 'password': 'secret'}}]:
            connection = copy.deepcopy(self.connection)
            connection.update(update)
            with self.subTest(update=update), self.assertRaises(outs.OutsError):
                connections.save(self.api, connection)
        self.assertFalse(connections.data_dir(self.api).exists())

    def test_ip_addresses_and_existing_ssh_aliases_are_valid(self):
        for host in ['::1', '::ffff:192.0.2.1', '2001:db8::1', 'fe80::1%eth0',
                     '192.0.2.1', 'server.example.', 'pracovni-alias', '_local', 'alias%user']:
            with self.subTest(host=host):
                connection = copy.deepcopy(self.connection)
                connection['record']['host'] = host
                connections.validate(self.api, connection)
        for host in ['-oProxyCommand=bad', '[::1]', 'invalid:address', 'server/name', '', None,
                     'fe80::1%bad\nname', 'fe80::1%bad\x00name', 'fe80::1%bad;name']:
            with self.subTest(host=host), self.assertRaises(outs.OutsError):
                connections.validate_host(self.api, host)

    def test_launcher_uses_only_stable_paths_to_its_own_package(self):
        package = self.root / 'package/bin/outs'
        other = self.root / 'other-package/bin/outs'
        for path in [package, other]:
            path.parent.mkdir(parents=True)
            path.write_text('fixture')
        system = self.root / 'system/bin/outs'
        profile = self.root / 'home/.nix-profile/bin/outs'
        discovered = self.root / 'path/bin/outs'
        for path in [system, profile, discovered]:
            path.parent.mkdir(parents=True)
        original_path = Path
        def mapped_path(value):
            return system if value == '/run/current-system/sw/bin/outs' else original_path(value)
        scenarios = [
            (package, package, package, system),
            (other, package, package, profile),
            (None, None, package, discovered),
            (other, other, other, package),
        ]
        for system_target, profile_target, path_target, expected in scenarios:
            with self.subTest(expected=expected):
                for path, target in zip([system, profile, discovered], [system_target, profile_target, path_target]):
                    path.unlink(missing_ok=True)
                    if target:
                        path.symlink_to(target)
                with patch.dict(os.environ, {'OUTSOURCE_EXECUTABLE': str(package)}), \
                     patch.object(outs, 'Path', side_effect=mapped_path) as paths, \
                     patch.object(outs.shutil, 'which', return_value=str(discovered)):
                    paths.home.return_value = self.root / 'home'
                    self.assertEqual(outs.launcher_executable(), expected)

    def test_bad_profiles_warn_without_hiding_healthy_connections(self):
        connections.save(self.api, self.connection)
        directory = connections.data_dir(self.api)
        broken = {
            'b' * 32 + '.json': b'{ broken json',
            'c' * 32 + '.json': b'\xff',
            'd' * 32 + '.json': json.dumps({**self.connection, 'id': 'd' * 32, 'type': []}).encode(),
        }
        for name, contents in broken.items():
            (directory / name).write_bytes(contents)
        with patch.object(connections, 'dialog') as warning, \
             patch.object(connections, 'choose', return_value=self.connection['id']) as choose:
            self.assertEqual(connections.select_connection(self.api), self.connection)
        self.assertIn('--warning', warning.call_args.args)
        text = next(arg for arg in warning.call_args.args if isinstance(arg, str) and arg.startswith('--text='))
        for name, contents in broken.items():
            self.assertIn(name, text)
            self.assertEqual((directory / name).read_bytes(), contents)
        self.assertEqual([row[0] for row in choose.call_args.args[2]], [self.connection['id']])

    def test_only_bad_profiles_report_paths_without_an_empty_chooser(self):
        path = connections.connection_path(self.api, 'b' * 32)
        path.parent.mkdir(parents=True)
        path.write_text('{ broken json')
        with patch.object(connections, 'choose') as choose, \
             self.assertRaisesRegex(outs.OutsError, path.name):
            connections.select_connection(self.api)
        choose.assert_not_called()
        self.assertEqual(path.read_text(), '{ broken json')

    @unittest.skipUnless(shutil.which('gio'), 'Gio is unavailable for desktop parser verification.')
    def test_ssh_desktop_arguments_round_trip_through_gio(self):
        # Run only our own fixture recording argv, not a terminal or SSH.
        program_dir = self.root / 'bin "quoted" $value'
        program_dir.mkdir()
        launcher = program_dir / 'outs'
        self.api.launcher_executable = lambda: launcher
        capture_path = self.root / 'captured.json'
        terminal = launcher.with_name('outs-terminal')
        terminal.write_text(
            '#!' + sys.executable + '\n'
            'import json, os, sys\n'
            'from pathlib import Path\n'
            'target = Path(os.environ["OUTSOURCE_TEST_CAPTURE"])\n'
            'temporary = target.with_suffix(".tmp")\n'
            'temporary.write_text(json.dumps(sys.argv[1:]))\n'
            'temporary.replace(target)\n'
        )
        terminal.chmod(0o700)
        env = {**os.environ, 'OUTSOURCE_TEST_CAPTURE': str(capture_path)}
        names = ['Server "café"', 'Server $value', 'Server `literal`',
                 r'Server\café', r'Server\\café', 'Server %U', 'Server\ttab']
        for name in names:
            with self.subTest(name=name):
                capture_path.unlink(missing_ok=True)
                self.connection['name'] = name
                desktop = self.root / 'probe.desktop'
                desktop.write_text(connections.desktop_contents(self.api, self.connection))
                result = subprocess.run([shutil.which('gio'), 'launch', str(desktop)], env=env,
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                deadline = time.monotonic() + 5
                while not capture_path.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(capture_path.exists(), 'Fixture nedostala argumenty.')
                args = json.loads(capture_path.read_text())
                self.assertEqual(args, [
                    '--gapplication-app-id=org.nixon.outsource.ssh.c' + self.connection['id'],
                    '--title=' + name, '--', str(launcher), 'connect', self.connection['id'],
                ])

    def test_rdp_desktop_has_gui_and_matching_window_identity(self):
        self.connection.update(type='rdp', record={
            'host': 'server', 'username': 'tomas', 'keepass': {'uuid': 'b' * 32}})
        connections.save(self.api, self.connection)
        desktop = connections.desktop_path(self.api, self.connection)
        content = desktop.read_text()
        self.assertIn('Terminal=false', content)
        self.assertIn('"--gui"', content)
        self.assertIn('StartupWMClass=' + desktop.stem, content)
        self.assertNotIn('b' * 32, content)
        with patch.object(self.api, 'dispatch_action', return_value=0) as launch:
            connections.connect(self.api, self.connection['id'])
        self.assertEqual(launch.call_args.args[2:], ('rdp', ['a' * 32, '--debug']))

    def test_cancelled_wizard_writes_nothing(self):
        with patch.object(connections, 'dialog', side_effect=outs.Cancelled):
            with self.assertRaises(outs.Cancelled):
                connections.edit_connection(self.api)
        self.assertFalse(connections.data_dir(self.api).exists())

    def test_ssh_wizard_preserves_system_defaults(self):
        with patch.object(connections, 'choose', side_effect=['ssh', 'config']), \
             patch.object(connections, 'details_form', return_value={'name': 'Server', 'host': 'alias', 'username': '', 'port': ''}), \
             patch.object(connections, 'dialog', return_value=''):
            connections.edit_connection(self.api)
        files = list(connections.data_dir(self.api).glob('*.json'))
        record = json.loads(files[0].read_text())['record']
        self.assertEqual(record['host'], 'alias')
        self.assertNotIn('username', record)
        self.assertNotIn('port', record)
        self.assertNotIn('keepass', record)

    def test_host_typo_can_be_corrected_without_losing_the_form(self):
        form = {'name': 'Work server', 'host': 'server/typo', 'username': 'tomas', 'port': '2222'}
        with patch.object(connections, 'choose', side_effect=['ssh', 'config']), \
             patch.object(connections, 'details_form', return_value=form), \
             patch.object(connections, 'entry', return_value='::1') as entry, \
             patch.object(connections, 'dialog', return_value='') as dialog:
            connections.edit_connection(self.api)
        entry.assert_called_once_with(self.api, 'Alias from ~/.ssh/config or server', 'server/typo')
        self.assertIn('--error', dialog.call_args_list[0].args)
        saved = json.loads(next(connections.data_dir(self.api).glob('*.json')).read_text())
        self.assertEqual(saved['name'], 'Work server')
        self.assertEqual(saved['record']['host'], '::1')
        self.assertEqual(saved['record']['username'], 'tomas')
        self.assertEqual(saved['record']['port'], 2222)

    def test_ssh_config_and_agent_are_not_overridden(self):
        config = {'company': {'id': 'test'}, 'ssh': [{'id': 'server', 'host': 'alias'}]}
        with patch.object(outs, 'require_program', return_value='/bin/ssh'), \
             patch.object(outs, 'run', return_value=0) as launch, \
             patch.object(outs, 'lookup_keepass_attachment') as key:
            outs.handle_ssh('test', config, ['server'])
        launch.assert_called_once_with(['/bin/ssh', '--', 'alias'])
        key.assert_not_called()

    def test_ssh_explicit_overrides_are_arguments_not_shell(self):
        config = {'ssh': [{'id': 'server', 'host': 'alias', 'username': 'user', 'port': 2222}]}
        with patch.object(outs, 'require_program', return_value='/bin/ssh'), \
             patch.object(outs, 'run', return_value=0) as launch:
            outs.handle_ssh('test', config, ['server'])
        launch.assert_called_once_with(['/bin/ssh', '-l', 'user', '-p', '2222', '--', 'alias'])

    def test_rdp_wizard_saves_uuid_and_options(self):
        with patch.object(connections, 'choose', return_value='rdp'), \
             patch.object(connections, 'details_form', return_value={'name': 'Windows', 'host': 'server', 'username': 'user', 'port': '', 'domain': ''}), \
             patch.object(connections, 'enter_credential', return_value={'uuid': 'b' * 32}), \
             patch.object(connections, 'dialog', side_effect=['clipboard,audio', '', '']):
            connections.edit_connection(self.api)
        record = json.loads(next(connections.data_dir(self.api).glob('*.json')).read_text())['record']
        self.assertEqual(record['keepass'], {'uuid': 'b' * 32})
        self.assertEqual(record['port'], 3389)
        self.assertTrue(record['clipboard'])
        self.assertEqual(record['audio'], 'local')

    def test_virt_viewer_wizard_does_not_need_keepass(self):
        with patch.object(connections, 'choose', return_value='virt-viewer'), \
             patch.object(connections, 'details_form', return_value={'name': 'Windows', 'domain': 'win11', 'connect': ''}), \
             patch.object(connections, 'enter_credential') as keepass, \
             patch.object(connections, 'dialog', return_value=''):
            connections.edit_connection(self.api)
        keepass.assert_not_called()
        self.assertIn('Terminal=false', next(self.api.applications_dir().glob('*.desktop')).read_text())

    def test_manual_uuid_does_not_read_or_unlock_keepass(self):
        self.api.LOCAL_CONFIG.write_text('{}')
        value = '{AABBCCDD-1122-3344-5566-778899AABBCC}'
        with patch.object(connections, 'entry', return_value=value), \
             patch.object(self.api, 'ask_password') as password, \
             patch.object(self.api, 'run_keepass_cli') as cli:
            result = connections.enter_credential(self.api)
        self.assertEqual(result, {'uuid': 'aabbccdd112233445566778899aabbcc'})
        password.assert_not_called()
        cli.assert_not_called()

    def test_uuid_edit_is_prefilled_and_preserves_ssh_attachment(self):
        self.api.LOCAL_CONFIG.write_text('{}')
        existing = {'uuid': 'a' * 32, 'attachment': 'id_ed25519'}
        with patch.object(connections, 'entry', return_value='b' * 32) as entry:
            result = connections.enter_credential(self.api, existing)
        self.assertEqual(entry.call_args.args[2], 'a' * 32)
        self.assertEqual(result, {'uuid': 'b' * 32, 'attachment': 'id_ed25519'})
        self.assertEqual(existing['uuid'], 'a' * 32)

    def test_invalid_uuid_retries_and_cancel_does_not_configure_vault(self):
        with patch.object(connections, 'entry', side_effect=['invalid', 'b' * 32]), \
             patch.object(connections, 'dialog') as error, \
             patch.object(connections, 'configure_keepass') as setup:
            self.assertEqual(connections.enter_credential(self.api), {'uuid': 'b' * 32})
        error.assert_called_once()
        setup.assert_called_once()
        with patch.object(connections, 'entry', side_effect=outs.Cancelled), \
             patch.object(connections, 'configure_keepass') as setup:
            with self.assertRaises(outs.Cancelled):
                connections.enter_credential(self.api)
        setup.assert_not_called()

    def test_password_uses_stdin_not_arguments_or_environment(self):
        with patch.object(outs.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'')) as run:
            outs.run_keepass_cli(['keepassxc-cli', 'ls', '-q', 'test.kdbx'], 'master-secret')
        self.assertNotIn('master-secret', run.call_args.args[0])
        self.assertNotIn('env', run.call_args.kwargs)
        # The input buffer is zeroed after the command exits.
        self.assertEqual(set(run.call_args.kwargs['input']), {0})

    def test_keepass_without_key_file(self):
        database = self.root / 'vault.kdbx'
        database.touch()
        self.api.LOCAL_CONFIG.write_text(json.dumps({'keepass': {'database': str(database)}}))
        with patch.object(outs, 'LOCAL_CONFIG', self.api.LOCAL_CONFIG):
            self.assertEqual(outs.keepass_paths(), (database, None))

    def test_dialog_uses_only_supported_button_options(self):
        for kind in ['--info', '--error', '--warning', '--file-selection', '--password']:
            with patch.object(self.api, 'require_program', return_value='zenity'), \
                 patch.object(connections.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run:
                connections.dialog(self.api, kind)
            args = run.call_args.args[0]
            self.assertEqual('--cancel-label=Cancel' in args, kind == '--password')
            self.assertEqual('--ok-label=Confirm' in args, kind != '--file-selection')

    def test_dialog_cancel_and_error(self):
        with patch.object(self.api, 'require_program', return_value='zenity'), \
             patch.object(connections.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', '')):
            with self.assertRaises(outs.Cancelled):
                connections.dialog(self.api, '--entry')
        with patch.object(self.api, 'require_program', return_value='zenity'), \
             patch.object(connections.subprocess, 'run', return_value=subprocess.CompletedProcess([], 2, '', '')):
            with self.assertRaises(outs.OutsError):
                connections.dialog(self.api, '--entry')


if __name__ == '__main__':
    unittest.main()
