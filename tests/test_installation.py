import contextlib
import io
import os
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_rdp import outs


class InstallationTests(unittest.TestCase):
    def test_external_profiles_are_read_live(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"OUTSOURCE_CLIENTS_DIR": directory}
        ):
            profile = Path(directory) / "test" / "config.json"
            profile.parent.mkdir()
            profile.write_text('{"company": {"id": "test"}, "rdp": []}')
            loaded = runpy.run_path(str(Path(outs.__file__)))
            self.assertEqual(loaded["all_configs"]()[0][1]["rdp"], [])
            profile.write_text('{"company": {"id": "test"}, "rdp": [{"id": "new"}]}')
            self.assertEqual(loaded["all_configs"]()[0][1]["rdp"], [{"id": "new"}])

    def test_missing_profiles_directory_reports_path(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"OUTSOURCE_CLIENTS_DIR": str(Path(directory) / "missing")}
        ):
            loaded = runpy.run_path(str(Path(outs.__file__)))
            with self.assertRaisesRegex(loaded["OutsError"], "Chybí adresář profilů"):
                loaded["all_configs"]()

    def test_local_config_uses_xdg_directory(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"XDG_CONFIG_HOME": directory}, clear=True
        ):
            loaded = runpy.run_path(str(Path(outs.__file__)))
            self.assertEqual(
                loaded["LOCAL_CONFIG"], Path(directory) / "outsource/config.local.json"
            )

    def test_explicit_local_config_takes_precedence(self):
        with patch.dict(os.environ, {"OUTSOURCE_LOCAL_CONFIG": "/custom/config.json"}):
            loaded = runpy.run_path(str(Path(outs.__file__)))
            self.assertEqual(loaded["LOCAL_CONFIG"], Path("/custom/config.json"))

    def test_default_profiles_and_connections_share_xdg_config(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"XDG_CONFIG_HOME": directory}, clear=True
        ):
            root = Path(directory) / "outsource"
            profile = root / "clients/test/config.json"
            profile.parent.mkdir(parents=True)
            profile.write_text('{"company": {"id": "test"}, "rdp": []}')
            loaded = runpy.run_path(str(Path(outs.__file__)))
            self.assertEqual(loaded["CLIENTS_DIR"], root / "clients")
            self.assertEqual(loaded["all_configs"]()[0][0], profile)
            from types import SimpleNamespace
            self.assertEqual(
                loaded["connection_tools"]().data_dir(SimpleNamespace(**loaded)),
                root / "connections",
            )

    def test_packaged_desktop_uses_wrapper_and_installed_icon(self):
        config = {"company": {"id": "test"}, "rdp": [{"id": "vm"}]}
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"OUTSOURCE_EXECUTABLE": "/package/bin/outs"}
        ), patch.object(outs, "applications_dir", return_value=Path(directory)), patch.object(
            outs, "resolve_client", return_value=(Path(directory), config)
        ), contextlib.redirect_stdout(io.StringIO()):
            outs.handle_desktop(["test", "rdp", "vm"])
            contents = (Path(directory) / "outs-test-rdp-vm.desktop").read_text()
            self.assertIn(f'Exec="{outs.launcher_executable()}" "test" "rdp" "vm"', contents)
            self.assertIn("Icon=outs-rdp\n", contents)
            self.assertNotIn("/share/outsource/bin/outs", contents)
