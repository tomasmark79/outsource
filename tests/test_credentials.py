"""Ověření identity položky používá jen umělé výstupy KeePassXC."""

from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from test_rdp import outs


UUID = "1" * 32


class CredentialTests(unittest.TestCase):
    def invoke(self, identity=UUID, *, status=0):
        calls = []

        def cli(arguments, password):
            calls.append(arguments)
            self.assertEqual(password, "fake-master")
            command = arguments[1]
            if command == "search":
                return subprocess.CompletedProcess(arguments, 0, b"/Servers/duplicate\n")
            if command == "show":
                return subprocess.CompletedProcess(arguments, status, identity.encode() + b"\n")
            self.assertEqual(command, "attachment-export")
            return subprocess.CompletedProcess(arguments, 0, b"FAKE-PRIVATE-KEY")

        with patch.object(outs, "keepass_paths", return_value=(Path("/fake.kdbx"), Path("/fake.key"))), \
             patch.object(outs, "ask_password", return_value="fake-master"), \
             patch.object(outs, "require_program", side_effect=lambda value: value), \
             patch.object(outs, "run_keepass_cli", side_effect=cli):
            try:
                return outs.lookup_keepass_attachment({"uuid": UUID, "attachment": "id_ed25519"}), calls
            finally:
                self.calls = calls

    def test_matching_uuid_exports_attachment(self):
        key, calls = self.invoke()
        self.assertEqual(key, bytearray(b"FAKE-PRIVATE-KEY"))
        self.assertEqual([call[1] for call in calls], ["search", "show", "attachment-export"])
        self.assertTrue(all("/fake.key" in call for call in calls))

    def test_duplicate_path_cannot_export_a_different_entry(self):
        with self.assertRaisesRegex(outs.OutsError, "jinou SSH položku"):
            self.invoke("2" * 32)
        self.assertNotIn("attachment-export", [call[1] for call in self.calls])

    def test_invalid_uuid_is_not_exported(self):
        with self.assertRaisesRegex(outs.OutsError, "neověřil UUID"):
            self.invoke("invalid")
        self.assertEqual(len(self.calls), 2)

    def test_failed_identity_command_is_not_exported(self):
        with self.assertRaises(outs.OutsError):
            self.invoke(status=1)
        self.assertEqual(len(self.calls), 2)
