import copy
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


loader = importlib.machinery.SourceFileLoader(
    "outs", str(Path(__file__).resolve().parents[1] / "bin" / "outs")
)
spec = importlib.util.spec_from_loader(loader.name, loader)
outs = importlib.util.module_from_spec(spec)
loader.exec_module(outs)


class RdpTests(unittest.TestCase):
    def launch(self, settings=None, args=None, manual=True):
        record = {"id": "test", "host": "example.test", "username": "user",
                  "keepass": {"uuid": "test"}}
        record.update(settings or {})
        config = {"company": {"id": "test"}, "rdp": [record]}
        original = copy.deepcopy(config)
        with patch.object(outs, "select_rdp_client", return_value="freerdp"), \
             patch.object(outs, "rdp_window_class", return_value="outs-rdp"), \
             patch.object(outs, "run_detached", return_value=0) as detached, \
             patch.object(outs, "lookup_keepass_password", return_value=bytearray(b"secret")), \
             patch.object(outs, "run_rdp_with_password", return_value=0) as secure:
            outs.handle_rdp("test", config, ["test", *(["--manual"] if manual else []), *(args or [])])
        self.assertEqual(config, original)
        return (detached if manual else secure).call_args.args[0]

    def test_existing_defaults(self):
        command = self.launch()
        self.assertIn("/sec:nla", command)
        self.assertIn("-clipboard", command)
        self.assertFalse(any(arg.startswith(("/sound", "/audio-mode", "/microphone")) for arg in command))

    def test_audio_modes(self):
        for mode, value in [("local", "0"), ("remote", "1"), ("off", "2")]:
            with self.subTest(mode=mode):
                command = self.launch({"audio": mode, "microphone": True})
                self.assertIn(f"/audio-mode:{value}", command)
                self.assertEqual("/sound" in command, mode == "local")
                self.assertIn("/microphone", command)

    def test_override_precedence_and_repeated_drives(self):
        command = self.launch({"audio": "local", "freerdp_args": [
            "/sound:sys:pulse", "/sec:tls", "+clipboard", "/drive:a,/tmp/a", "/drive:b,/tmp/b b"
        ]}, ["--", "/sec:rdp", "-clipboard", "-dynamic-resolution"])
        for arg in ["/sound", "/sec:nla", "/sec:tls", "+clipboard", "+dynamic-resolution"]:
            self.assertNotIn(arg, command)
        for arg in ["/sound:sys:pulse", "/sec:rdp", "-clipboard", "-dynamic-resolution",
                    "/drive:a,/tmp/a", "/drive:b,/tmp/b b"]:
            self.assertIn(arg, command)

    def test_secure_path_receives_options(self):
        command = self.launch({"audio": "local"}, ["--", "/microphone"], manual=False)
        self.assertIn("/sound", command)
        self.assertIn("/microphone", command)
        self.assertFalse(any(arg.startswith("/p:") for arg in command))

    def test_cli_disables_configured_sound(self):
        for mode in ["1", "2", "server", "none"]:
            with self.subTest(mode=mode):
                command = self.launch({"audio": "local", "freerdp_args": ["/sound:sys:pulse"]},
                                      ["--", f"/audio-mode:{mode}"])
                self.assertIn(f"/audio-mode:{mode}", command)
                self.assertNotIn("/audio-mode:0", command)
                self.assertFalse(any(arg.startswith("/sound") for arg in command))

    def test_invalid_settings(self):
        for settings in [{"audio": "bad"}, {"audio": []}, {"microphone": "true"},
                         {"freerdp_args": "/f"}, {"freerdp_args": [1]},
                         {"freerdp_args": ["/f\n/p:secret"]}]:
            with self.subTest(settings=settings), self.assertRaises(outs.OutsError):
                self.launch(settings)

    def test_reserved_arguments(self):
        for arg in ["/p:secret", "/password:secret", "/args-from:stdin"]:
            with self.subTest(arg=arg), self.assertRaises(outs.OutsError):
                self.launch(args=["--", arg])

    def test_launcher_flags_still_validated(self):
        with self.assertRaises(outs.OutsError):
            self.launch(args=["/f"])


if __name__ == "__main__":
    unittest.main()
