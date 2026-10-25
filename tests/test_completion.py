import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_rdp import outs


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.clients = self.root / "clients"
        profile = self.clients / "example" / "config.json"
        profile.parent.mkdir(parents=True)
        profile.write_text(json.dumps({
            "company": {"id": "example", "aliases": ["demo"]},
            "ssh": [{"id": "bastion"}], "rdp": [{"id": "workstation"}],
            "vpn": [{"id": "office"}],
            "web": [{"id": "portal"}, {"id": "bad\nvalue"}],
        }))
        self.addCleanup(patch.stopall)
        patch.object(outs, "CONFIG_HOME", self.root).start()
        patch.object(outs, "CLIENTS_DIR", self.clients).start()

    def complete(self, *words):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(
            outs, "run_main", side_effect=AssertionError("spuštění příkazu")
        ), patch.object(outs, "connection_tools", side_effect=AssertionError("dialog")):
            self.assertEqual(outs.main(["--complete", *words]), 0)
        return output.getvalue().splitlines()

    def test_commands_clients_and_prefix(self):
        self.assertIn("connect", self.complete(""))
        self.assertIn("example", self.complete(""))
        self.assertEqual(self.complete("de"), ["demo", "desktop"])
        self.assertEqual(self.complete("new", ""), [])

    def test_actions_targets_and_aliases(self):
        self.assertIn("rdp", self.complete("demo", ""))
        self.assertEqual(self.complete("demo", "ssh", "ba"), ["bastion"])
        self.assertEqual(self.complete("example", "vpn-down", ""), ["office"])
        self.assertEqual(self.complete("example", "web", ""), ["portal"])
        self.assertEqual(self.complete("unknown", ""), [])

    def test_desktop_and_rdp_flags(self):
        self.assertEqual(self.complete("desktop", "ex"), ["example"])
        self.assertNotIn("show", self.complete("desktop", "example", ""))
        self.assertEqual(self.complete("desktop", "example", "rdp", ""), ["workstation"])
        self.assertEqual(self.complete("desktop", "example", "rdp", "workstation", ""), ["--name"])
        self.assertEqual(self.complete("desktop", "example", "rdp", "workstation", "--name", ""), [])
        self.assertEqual(self.complete("demo", "rdp", "workstation", "--manual", ""), ["--", "--debug"])
        self.assertEqual(self.complete("demo", "rdp", "workstation", "--", ""), [])

    def test_connection_ids_and_gui_flag(self):
        directory = self.root / "outsource" / "connections"
        directory.mkdir(parents=True)
        connection_id = "a" * 32
        (directory / (connection_id + ".json")).write_text("{}")
        (directory / "invalid.json").write_text("{}")
        self.assertEqual(self.complete("connect", "a"), [connection_id])
        self.assertEqual(self.complete("connect", connection_id, ""), ["--gui"])
        self.assertEqual(self.complete("connect", connection_id, "--gui", ""), [])

    def test_missing_and_broken_profiles(self):
        broken = self.clients / "broken" / "config.json"
        broken.parent.mkdir()
        broken.write_text("{")
        self.assertIn("example", self.complete(""))
        with patch.object(outs, "CLIENTS_DIR", self.root / "missing"):
            self.assertIn("connect", self.complete(""))
            self.assertEqual(self.complete("connect", ""), [])

    def test_ambiguous_alias_is_not_completed(self):
        profile = self.clients / "other" / "config.json"
        profile.parent.mkdir()
        profile.write_text(json.dumps({"company": {"id": "other", "aliases": ["demo"]}}))
        self.assertEqual(self.complete("demo", ""), [])

    def test_bash_adapter_and_cli_have_no_side_effects(self):
        project = Path(outs.__file__).resolve().parents[1]
        environment = dict(os.environ, XDG_CONFIG_HOME=str(self.root),
                           XDG_STATE_HOME=str(self.root / "state"),
                           OUTSOURCE_CLIENTS_DIR=str(self.clients),
                           PATH=str(project / "bin") + os.pathsep + os.environ["PATH"])
        result = subprocess.run([
            "bash", "--noprofile", "--norc", "-c",
            'outs() { "$PYTHON_FOR_TEST" "$OUTS_FOR_TEST" "$@"; }; '
            'source "$1"; COMP_WORDS=(outs demo ssh ba); COMP_CWORD=3; '
            '_outs_complete; printf "%s\\n" "${COMPREPLY[@]}"',
            "bash", str(project / "completions" / "outs.bash"),
        ], env=dict(environment, PYTHON_FOR_TEST=sys.executable,
                    OUTS_FOR_TEST=str(project / "bin" / "outs")),
            capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, "bastion\n")
        self.assertEqual(result.stderr, "")
        self.assertFalse((self.root / "state").exists())
        self.assertFalse((self.root / "outsource").exists())
