import contextlib
import io
import os
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from test_rdp import outs


class VirtViewerTests(unittest.TestCase):
    def setUp(self):
        self.config = {"company": {"id": "test"}, "virt-viewer": [
            {"id": "vm", "domain": "win11-leadball-ableton"}
        ]}

    def test_direct_launch_is_detached(self):
        with patch.object(outs.shutil, "which", return_value="/bin/virt-viewer"), \
             patch.object(outs.subprocess, "Popen", return_value=Mock(pid=123)) as run, \
             patch.dict(os.environ, {"GDK_BACKEND": "x11"}):
            self.assertEqual(outs.dispatch_action("test", self.config, "virt-viewer", ["vm"]), 0)
            self.assertEqual(run.call_args.args[0], ["/bin/virt-viewer",
                             "--name=outs-test-virt-viewer-vm", "--class=outs-test-virt-viewer-vm", "--attach",
                             "--connect=qemu:///system", "--", "win11-leadball-ableton"])
            self.assertEqual(run.call_args.kwargs["env"]["GDK_BACKEND"], "wayland")
            self.assertEqual(os.environ["GDK_BACKEND"], "x11")
            self.assert_detached(run)
            run.return_value.wait.assert_not_called()

    def assert_detached(self, run):
        for stream in ("stdin", "stdout", "stderr"):
            self.assertEqual(run.call_args.kwargs[stream], outs.subprocess.DEVNULL)
        if os.name != "nt":
            self.assertTrue(run.call_args.kwargs["start_new_session"])

    def test_launch_failure(self):
        with patch.object(outs.shutil, "which", return_value="/bin/virt-viewer"), \
             patch.object(outs.subprocess, "Popen", side_effect=OSError("unavailable")):
            with self.assertRaisesRegex(outs.OutsError, "Virt-viewer nelze spustit"):
                outs.handle_virt_viewer("test", self.config, ["vm"])

    def test_nix_fallback_quotes_domain(self):
        domain = "Windows VM $(touch /tmp/should-not-exist) 'test'"
        self.config["virt-viewer"][0].update(domain=domain, connect="qemu:///session")
        with patch.object(outs.shutil, "which", side_effect=[None, "/bin/nix-shell"]), \
             patch.object(outs.subprocess, "Popen", return_value=Mock(pid=123)) as run:
            outs.handle_virt_viewer("test", self.config, ["vm"])
        self.assert_detached(run)
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["/bin/nix-shell", "-p", "virt-viewer", "--run"])
        self.assertEqual(shlex.split(command[4]), ["virt-viewer",
                         "--name=outs-test-virt-viewer-vm", "--class=outs-test-virt-viewer-vm", "--attach",
                         "--connect=qemu:///session", "--", domain])
        self.assertEqual(run.call_args.kwargs["env"]["GDK_BACKEND"], "wayland")

    def test_invalid_input_does_not_launch(self):
        with patch.object(outs.subprocess, "Popen") as run:
            for args in [["missing"], ["vm", "extra"], ["../vm"]]:
                with self.subTest(args=args), self.assertRaises(outs.OutsError):
                    outs.handle_virt_viewer("test", self.config, args)
            for value in [None, "", 1, "bad\nname"]:
                self.config["virt-viewer"][0]["domain"] = value
                with self.subTest(value=value), self.assertRaises(outs.OutsError):
                    outs.handle_virt_viewer("test", self.config, ["vm"])
            run.assert_not_called()

    def test_listing_menu_and_desktop(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(outs.handle_virt_viewer("test", self.config, []), 0)
        self.assertIn("win11-leadball-ableton", output.getvalue())
        self.assertEqual(outs.menu_items(self.config)[0][1:], ("virt-viewer", ["vm"]))
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(outs, "applications_dir", return_value=Path(directory)), \
             patch.object(outs, "resolve_client", return_value=(Path(directory), self.config)), \
             contextlib.redirect_stdout(io.StringIO()):
            outs.handle_desktop(["test", "virt-viewer", "vm"])
            contents = (Path(directory) / "outs-test-virt-viewer-vm.desktop").read_text()
            self.assertIn('"test" "virt-viewer" "vm"', contents)
            self.assertIn("Terminal=false", contents)
            self.assertIn("StartupWMClass=outs-test-virt-viewer-vm\n", contents)
            self.assertIn(f"Icon={outs.ROOT / 'assets' / 'outs-virt-viewer.svg'}", contents)


if __name__ == "__main__":
    unittest.main()
