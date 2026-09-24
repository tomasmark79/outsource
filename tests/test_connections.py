"""Průvodce ověřujeme v dočasném profilu, bez připojování k serverům."""
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
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
            'version': 1, 'id': 'a' * 32, 'name': 'Server – práce', 'type': 'ssh',
            'record': {'host': 'pracovni-alias'},
        }

    def test_create_edit_delete_and_stale_edit(self):
        connections.save(self.api, self.connection)
        path = connections.connection_path(self.api, self.connection['id'])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        desktop = connections.desktop_path(self.api, self.connection)
        self.assertIn('Terminal=true', desktop.read_text())
        self.assertIn('"connect" "' + 'a' * 32 + '"', desktop.read_text())
        previous = copy.deepcopy(self.connection)
        self.connection['name'] = 'Nový název'
        connections.save(self.api, self.connection, previous)
        with self.assertRaises(outs.OutsError):
            connections.save(self.api, previous, previous)
        self.assertIn('Nový název', desktop.read_text())
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
        for update in [{'id': '../escape'}, {'name': 'název\nExec=bad'},
                       {'record': {'host': '-oProxyCommand=bad'}},
                       {'record': {'host': 'server', 'port': 0}},
                       {'record': {'host': 'server', 'password': 'secret'}}]:
            connection = copy.deepcopy(self.connection)
            connection.update(update)
            with self.subTest(update=update), self.assertRaises(outs.OutsError):
                connections.save(self.api, connection)
        self.assertFalse(connections.data_dir(self.api).exists())

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
        # Vstupní buffer se po skončení příkazu vynuluje.
        self.assertEqual(set(run.call_args.kwargs['input']), {0})

    def test_keepass_without_key_file(self):
        database = self.root / 'vault.kdbx'
        database.touch()
        self.api.LOCAL_CONFIG.write_text(json.dumps({'keepass': {'database': str(database)}}))
        with patch.object(outs, 'LOCAL_CONFIG', self.api.LOCAL_CONFIG):
            self.assertEqual(outs.keepass_paths(), (database, None))

    def test_dialog_uses_only_supported_button_options(self):
        for kind in ['--info', '--error', '--file-selection', '--password']:
            with patch.object(self.api, 'require_program', return_value='zenity'), \
                 patch.object(connections.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run:
                connections.dialog(self.api, kind)
            args = run.call_args.args[0]
            self.assertEqual('--cancel-label=Zrušit' in args, kind == '--password')
            self.assertEqual('--ok-label=Potvrdit' in args, kind != '--file-selection')

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
