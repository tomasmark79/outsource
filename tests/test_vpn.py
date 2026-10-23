"""VPN zkoušíme s paměťovým NetworkManagerem, bez sítě a uživatelských dat."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_rdp import outs


UUID = "22222222-2222-2222-2222-222222222222"


class VpnTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.profiles = {}
        self.calls = []
        self.fail = None
        self.cancel = None
        self.bad_output = False
        self.delete_failure = False
        self.query_failure = False
        self.profile = bytearray(b"client\n<key>\nFAKE-PRIVATE-KEY\n</key>\n")
        self.password = bytearray(b"fake-secret")
        self.config = {"vpn": [{"id": "office", "type": "openvpn", "keepass": {"uuid": "1" * 32}}]}
        self.enter_context(patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(self.runtime), "XDG_DATA_HOME": str(self.root / "data")}))
        self.enter_context(patch.object(outs, "require_program", side_effect=lambda value: value))
        self.enter_context(patch.object(outs, "lookup_keepass_vpn", side_effect=self.credentials))
        self.enter_context(patch.object(outs.subprocess, "run", side_effect=self.nmcli))
        self.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.enter_context(contextlib.redirect_stderr(io.StringIO()))

    def enter_context(self, manager):
        result = manager.__enter__()
        self.addCleanup(manager.__exit__, None, None, None)
        return result

    def credentials(self, _):
        return self.profile, "demo-user", self.password

    def nmcli(self, command, **options):
        self.calls.append((command, options))
        self.assertEqual(command[0], "nmcli")
        status, output = 0, b""
        if command[1] == "-g":
            self.assertEqual(command[1:5], ["-g", "connection.uuid", "connection", "show"])
            if self.query_failure and self.profiles:
                return subprocess.CompletedProcess(command, 8, b"")
            selector, value = command[5:]
            matches = [uid for uid, name in self.profiles.items()
                       if (uid if selector == "uuid" else name) == value]
            return subprocess.CompletedProcess(command, 0 if matches else 10,
                                               "\n".join(matches).encode())
        operation = command[2]
        if operation == "import":
            profile = Path(command[-1])
            self.assertEqual(profile.stat().st_mode & 0o777, 0o600)
            self.assertIn(b"FAKE-PRIVATE-KEY", profile.read_bytes())
            self.assertEqual(options["env"]["LC_ALL"], "C")
            certificate_root = Path(options["env"]["NM_CERT_PATH"])
            self.assertTrue(certificate_root.is_relative_to(self.runtime))
            self.assertEqual(certificate_root.stat().st_mode & 0o777, 0o700)
            # Stejně jako plugin vypíšeme vložený klíč odděleně od .ovpn.
            certs = certificate_root / "nm-openvpn"
            certs.mkdir()
            (certs / "key.pem").write_bytes(b"FAKE-PRIVATE-KEY")
            self.profiles[UUID] = profile.stem
            if self.bad_output:
                output = b"unknown successful import output"
            else:
                # UUID uvnitř názvu nesmí přebít skutečné UUID v závorkách.
                output = (f"Connection 'name-11111111-1111-1111-1111-111111111111' ({UUID}) successfully added.\n").encode()
        elif operation == "modify":
            self.assertEqual(command[:6], ["nmcli", "connection", "modify", "--temporary", "uuid", UUID])
            if command[6] == "connection.id":
                self.profiles[UUID] = command[7]
        elif operation == "up":
            self.assertEqual(command[4], UUID)
            password = Path(command[-1])
            self.assertEqual(password.stat().st_mode & 0o777, 0o600)
            self.assertEqual(password.read_bytes(), b"vpn.secrets.password:fake-secret\n")
            self.assertNotIn("fake-secret", " ".join(command))
        elif operation == "delete":
            self.assertEqual(command[3], "uuid")
            if self.delete_failure:
                return subprocess.CompletedProcess(command, 8, b"")
            self.profiles.pop(command[4], None)
        else:
            self.failTest(f"Unexpected command: {command}")
        if operation == self.cancel:
            raise KeyboardInterrupt()
        if operation == self.fail:
            status = 8
        return subprocess.CompletedProcess(command, status, output)

    def invoke(self, action="vpn-up"):
        return outs.handle_vpn("example", self.config, action, [self.config["vpn"][0]["id"]])

    def states(self):
        return list(self.runtime.rglob("state.json"))

    def test_up_keeps_only_runtime_certificates_and_uuid(self):
        self.assertEqual(self.invoke(), 0)
        self.assertEqual(len(self.states()), 1)
        state = self.states()[0]
        self.assertEqual(state.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(state.read_text())["uuid"], UUID)
        self.assertNotIn("fake-secret", state.read_text())
        self.assertEqual(len(list(self.runtime.rglob("key.pem"))), 1)
        self.assertFalse(list(self.runtime.rglob("*.ovpn")))
        self.assertFalse(list(self.runtime.rglob("*.passwd")))
        self.assertFalse((self.root / "data").exists())
        self.assertEqual(set(self.profile), {0})
        self.assertEqual(set(self.password), {0})

    def test_down_deletes_by_uuid_and_cleans_certificates(self):
        self.invoke()
        self.assertEqual(self.invoke("vpn-down"), 0)
        self.assertFalse(self.profiles)
        self.assertFalse(self.states())
        self.assertFalse(list(self.runtime.rglob("key.pem")))

    def test_down_without_runtime_state_is_idempotent(self):
        self.assertEqual(self.invoke("vpn-down"), 0)
        self.assertEqual([call[0] for call in self.calls], [
            ["nmcli", "-g", "connection.uuid", "connection", "show", "id",
             outs.vpn_runtime_tools().VpnRuntime("example", "office").name],
            ["nmcli", "-g", "connection.uuid", "connection", "show", "id", "outs-example-office"],
        ])

    def test_lookup_uses_detail_uuid_field_and_exact_selector(self):
        self.profiles[UUID] = "example-profile"
        self.assertEqual(outs.vpn_profile_uuid("nmcli", "id", "example-profile"), UUID)
        self.assertEqual(outs.vpn_profile_uuid("nmcli", "uuid", UUID), UUID)
        self.assertEqual([call[0] for call in self.calls], [
            ["nmcli", "-g", "connection.uuid", "connection", "show", "id", "example-profile"],
            ["nmcli", "-g", "connection.uuid", "connection", "show", "uuid", UUID],
        ])

    def test_legacy_profile_down_is_not_silently_reported_as_success(self):
        self.profiles[UUID] = "outs-example-office"
        with self.assertRaisesRegex(outs.OutsError, "bez spravovaného runtime stavu"):
            self.invoke("vpn-down")
        self.assertIn(UUID, self.profiles)
        self.assertEqual(len(self.calls), 2)

    def test_legacy_profile_up_fails_before_unlock(self):
        self.profiles[UUID] = "outs-example-office"
        with patch.object(outs, "lookup_keepass_vpn") as lookup, self.assertRaises(outs.OutsError):
            self.invoke()
        lookup.assert_not_called()
        self.assertIn(UUID, self.profiles)

    def test_profile_left_after_logout_requires_explicit_cleanup(self):
        runtime = outs.vpn_runtime_tools().VpnRuntime("example", "office")
        self.profiles[UUID] = runtime.name
        with patch.object(outs, "lookup_keepass_vpn") as lookup, self.assertRaisesRegex(outs.OutsError, UUID):
            self.invoke()
        lookup.assert_not_called()
        with self.assertRaisesRegex(outs.OutsError, UUID):
            self.invoke("vpn-down")
        self.assertEqual(self.profiles[UUID], runtime.name)

    def test_modifications_keep_the_import_in_memory(self):
        self.invoke()
        modifications = [call[0] for call in self.calls if call[0][1:3] == ["connection", "modify"]]
        runtime = outs.vpn_runtime_tools().VpnRuntime("example", "office")
        self.assertEqual(modifications, [
            ["nmcli", "connection", "modify", "--temporary", "uuid", UUID, "connection.id", runtime.name],
            ["nmcli", "connection", "modify", "--temporary", "uuid", UUID, "+vpn.data", "username=demo-user"],
        ])

    def test_second_up_does_not_unlock_again(self):
        self.invoke()
        with patch.object(outs, "lookup_keepass_vpn") as lookup, self.assertRaises(outs.OutsError):
            self.invoke()
        lookup.assert_not_called()

    def test_failed_activation_rolls_back_profile_and_certificates(self):
        self.fail = "up"
        with self.assertRaises(outs.OutsError):
            self.invoke()
        self.assertFalse(self.profiles)
        self.assertFalse(self.states())
        self.assertFalse(list(self.runtime.rglob("key.pem")))

    def test_failed_import_recovers_uuid_from_saved_import_name(self):
        self.fail = "import"
        with self.assertRaises(outs.OutsError):
            self.invoke()
        self.assertFalse(self.profiles)
        self.assertFalse(self.states())

    def test_unknown_import_output_rolls_back_by_import_name(self):
        self.bad_output = True
        with self.assertRaises(outs.OutsError):
            self.invoke()
        self.assertFalse(self.profiles)
        self.assertFalse(self.states())

    def test_failed_modify_rolls_back_by_uuid(self):
        self.fail = "modify"
        with self.assertRaises(outs.OutsError):
            self.invoke()
        self.assertFalse(self.profiles)
        self.assertFalse(self.states())

    def test_failed_uuid_recovery_keeps_import_name_for_retry(self):
        self.bad_output = True
        self.query_failure = True
        with self.assertRaises(outs.OutsError):
            self.invoke()
        self.assertTrue(self.states())
        state = json.loads(self.states()[0].read_text())
        self.assertIsNone(state["uuid"])
        self.assertTrue(state["import_name"].startswith("outs-"))
        self.assertTrue(list(self.runtime.rglob("key.pem")))
        self.query_failure = False
        self.invoke("vpn-down")
        self.assertFalse(self.states())

    def test_state_write_failure_before_import_leaves_no_files(self):
        module = outs.vpn_runtime_tools()
        with patch.object(outs, "vpn_runtime_tools", return_value=module), \
             patch.object(module.VpnRuntime, "save", side_effect=OSError("fake disk error")), \
             self.assertRaises(OSError):
            self.invoke()
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(all(call[0][1:5] == ["-g", "connection.uuid", "connection", "show"] for call in self.calls))
        self.assertFalse(list(self.runtime.rglob("*.ovpn")))
        self.assertFalse([path for path in (self.runtime / "outsource" / "vpn").iterdir() if path.is_dir()])

    def test_cancel_after_import_rolls_back_without_uuid_output(self):
        self.cancel = "import"
        with self.assertRaises(KeyboardInterrupt):
            self.invoke()
        self.assertFalse(self.profiles)
        self.assertFalse(self.states())

    def test_cancel_after_activation_rolls_back(self):
        self.cancel = "up"
        with self.assertRaises(KeyboardInterrupt):
            self.invoke()
        self.assertFalse(self.profiles)
        self.assertFalse(self.states())

    def test_delete_failure_keeps_state_for_retry(self):
        self.invoke()
        self.delete_failure = True
        with self.assertRaises(outs.OutsError):
            self.invoke("vpn-down")
        self.assertTrue(self.states())
        self.assertTrue(list(self.runtime.rglob("key.pem")))
        self.delete_failure = False
        self.assertEqual(self.invoke("vpn-down"), 0)
        self.assertFalse(self.states())

    def test_failed_rollback_keeps_uuid_for_later_down(self):
        self.fail = "up"
        self.delete_failure = True
        with self.assertRaises(outs.OutsError):
            self.invoke()
        self.assertEqual(json.loads(self.states()[0].read_text())["uuid"], UUID)
        self.assertFalse(list(self.runtime.rglob("*.passwd")))
        self.assertFalse(list(self.runtime.rglob("*.ovpn")))
        self.delete_failure = False
        self.fail = None
        self.invoke("vpn-down")
        self.assertFalse(self.states())

    def test_lost_nm_profile_allows_local_cleanup(self):
        self.invoke()
        self.profiles.clear()
        self.assertEqual(self.invoke("vpn-down"), 0)
        self.assertFalse(self.states())

    def test_hyphenated_id_pairs_cannot_collide(self):
        module = outs.vpn_runtime_tools()
        left = module.VpnRuntime("a-b", "c")
        right = module.VpnRuntime("a", "b-c")
        self.assertNotEqual(left.name, right.name)
        self.assertNotEqual(left.path, right.path)

    def test_missing_runtime_directory_fails_before_unlock(self):
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": ""}), \
             patch.object(outs, "lookup_keepass_vpn") as lookup, \
             self.assertRaisesRegex(outs.OutsError, "XDG_RUNTIME_DIR"):
            self.invoke()
        lookup.assert_not_called()

    def test_unsafe_runtime_directory_fails_before_unlock(self):
        self.runtime.chmod(0o755)
        with patch.object(outs, "lookup_keepass_vpn") as lookup, self.assertRaises(outs.OutsError):
            self.invoke()
        lookup.assert_not_called()

    def test_same_profile_is_locked(self):
        module = outs.vpn_runtime_tools()
        with module.VpnRuntime("example", "office"), self.assertRaisesRegex(outs.OutsError, "jiný příkaz"):
            self.invoke()

    def test_corrupt_state_does_not_delete_any_profile(self):
        self.invoke()
        self.states()[0].write_text('{"uuid":"invalid"}')
        count = len(self.calls)
        with self.assertRaises(outs.OutsError):
            self.invoke("vpn-down")
        self.assertEqual(len(self.calls), count)
        self.assertTrue(self.profiles)
