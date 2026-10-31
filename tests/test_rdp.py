import copy
import contextlib
import importlib.machinery
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


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

    def test_remoteapp_program_is_passed_as_one_argument(self):
        for program in ['||notepad', r'C:\Program Files\Example\app.exe']:
            for manual in (True, False):
                with self.subTest(program=program, manual=manual):
                    command = self.launch({'remoteapp': program}, manual=manual)
                    self.assertIn('/app:program:' + program, command)
                    self.assertIn('/wm-class:outs-rdp', command)

    def test_empty_remoteapp_keeps_desktop_mode(self):
        command = self.launch({'remoteapp': ''})
        self.assertFalse(any(arg.startswith('/app:') for arg in command))

    def test_invalid_remoteapp_is_rejected(self):
        for program in [None, True, [], ' ', '||app\n/p:secret', 'a\0b', 'a\rb',
                        '||app,cmd:unexpected', '"||app"']:
            with self.subTest(program=program), self.assertRaises(outs.OutsError):
                self.launch({'remoteapp': program})

    def test_remoteapp_prefers_sdl_client(self):
        available = {'sdl-freerdp': '/bin/sdl-freerdp', 'xfreerdp': '/bin/xfreerdp'}
        with patch.dict(outs.os.environ, {}, clear=True), \
             patch.object(outs.shutil, 'which', side_effect=available.get):
            self.assertEqual(outs.select_rdp_client(remoteapp=True), '/bin/sdl-freerdp')
            self.assertEqual(outs.select_rdp_client(), '/bin/sdl-freerdp')

    def test_remoteapp_requires_sdl_client_without_override(self):
        with patch.dict(outs.os.environ, {}, clear=True), \
             patch.object(outs.shutil, 'which', side_effect=lambda name: '/bin/xfreerdp' if name == 'xfreerdp' else None), \
             self.assertRaisesRegex(outs.OutsError, 'RemoteApp'):
            outs.select_rdp_client(remoteapp=True)

    def test_remoteapp_uses_verified_graphics_and_scale_defaults(self):
        for manual in (True, False):
            with self.subTest(manual=manual):
                command = self.launch({'remoteapp': '||notepad'}, manual=manual)
                for option in ['/scale-desktop:150', '/bpp:32', '/gfx:AVC444,frame-ack:off']:
                    self.assertIn(option, command)
        desktop = self.launch()
        self.assertFalse(any(a.startswith(('/scale-desktop:', '/bpp:', '/gfx:')) for a in desktop))

    def test_remoteapp_defaults_can_be_overridden_per_profile_and_command(self):
        settings = {'remoteapp': '||notepad', 'freerdp_args': [
            '/scale-desktop:125', '/gfx:RFX']}
        profile = self.launch(settings)
        self.assertIn('/scale-desktop:125', profile)
        self.assertIn('/gfx:RFX', profile)
        self.assertNotIn('/scale-desktop:150', profile)
        self.assertNotIn('/gfx:AVC444,frame-ack:off', profile)
        command = self.launch(settings, ['--', '/scale-desktop:200', '/gfx:AVC444'])
        self.assertIn('/scale-desktop:200', command)
        self.assertIn('/gfx:AVC444', command)
        self.assertNotIn('/scale-desktop:125', command)
        self.assertNotIn('/gfx:RFX', command)

    def test_ipv6_address_is_separated_from_port(self):
        for host in ["::1", "2001:db8::1", "::ffff:192.0.2.1", "fe80::1%eth0"]:
            with self.subTest(host=host):
                command = self.launch({"host": host, "port": 3390})
                self.assertIn(f"/v:[{host}]:3390", command)

    def test_ipv4_hostname_and_bracketed_legacy_address_are_preserved(self):
        for host in ["192.0.2.1", "server.example.test", "[2001:db8::1]"]:
            with self.subTest(host=host):
                self.assertIn(f"/v:{host}:3389", self.launch({"host": host}))

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


class RdpProcessTests(unittest.TestCase):
    def setUp(self):
        for name, value in [("SESSION_LOG", None), ("GUI_MODE", False)]:
            state = patch.object(outs, name, value)
            state.start()
            self.addCleanup(state.stop)

    def test_remoteapp_wayland_environment_reaches_all_authentication_modes(self):
        for detached in (True, False):
            for secure in (True, False):
                with self.subTest(detached=detached, secure=secure):
                    process = Mock()
                    process.poll.return_value = 0
                    password = bytearray(b'fixture') if secure else None
                    parent = {'WAYLAND_DISPLAY': 'fixture-wayland', 'SDL_VIDEODRIVER': 'x11',
                              'SDL_VIDEO_WAYLAND_SCALE_TO_DISPLAY': '0'}
                    with patch.dict(outs.os.environ, parent, clear=True), \
                         patch.object(outs.subprocess, 'Popen', return_value=process) as launch, \
                         patch.object(outs, 'wait_for_client', return_value=0), \
                         patch.object(outs, 'report_detached_rdp', return_value=0), \
                         patch.object(outs, 'warn_if_vpn_active', return_value=0):
                        outs.run_rdp(['sdl-freerdp', '/app:program:||notepad'],
                                     detached=detached, password=password)
                        child_env = launch.call_args.kwargs.get('env', {})
                        self.assertEqual(child_env.get('SDL_VIDEODRIVER'), 'wayland')
                        self.assertEqual(child_env.get('SDL_VIDEO_WAYLAND_SCALE_TO_DISPLAY'), '1')
                        self.assertEqual(child_env.get('WAYLAND_DISPLAY'), 'fixture-wayland')
                        self.assertEqual(dict(outs.os.environ), parent)
                        if secure:
                            self.assertEqual(launch.call_args.args[0], ['sdl-freerdp', '/args-from:stdin'])
                            self.assertEqual(set(password), {0})

    def test_desktop_rdp_does_not_override_sdl_environment(self):
        process = Mock()
        process.poll.return_value = 0
        with patch.dict(outs.os.environ, {'WAYLAND_DISPLAY': 'fixture-wayland'}, clear=True), \
             patch.object(outs.subprocess, 'Popen', return_value=process) as launch, \
             patch.object(outs, 'report_detached_rdp', return_value=0):
            outs.run_rdp(['sdl-freerdp', '/v:example.test'], detached=True)
        self.assertNotIn('env', launch.call_args.kwargs)

    def test_remoteapp_on_x11_does_not_force_wayland(self):
        process = Mock()
        process.poll.return_value = 0
        with patch.dict(outs.os.environ, {'DISPLAY': ':fixture'}, clear=True), \
             patch.object(outs.subprocess, 'Popen', return_value=process) as launch, \
             patch.object(outs, 'report_detached_rdp', return_value=0):
            outs.run_rdp(['sdl-freerdp', '/app:program:||notepad'], detached=True)
        self.assertNotIn('SDL_VIDEODRIVER', launch.call_args.kwargs.get('env', {}))

    def test_manual_debug_and_keepass_share_exit_classification(self):
        # A harmless process accepts the same line-based input as FreeRDP.
        # It does not connect to the network or a graphical session.
        with tempfile.TemporaryDirectory() as directory:
            client = Path(directory) / "fake-rdp"
            client.write_text("#!" + sys.executable + "\n" + """import sys
args = (sys.stdin.buffer.read().decode().splitlines()
        if sys.argv[1:] == ['/args-from:stdin'] else sys.argv[1:])
code = next(arg.split(':', 1)[1] for arg in args if arg.startswith('/fixture-exit:'))
diagnostic = next(arg.split(':', 1)[1] for arg in args if arg.startswith('/fixture-diagnostic:'))
sys.stderr.write(diagnostic)
sys.exit(int(code))
""")
            client.chmod(0o700)
            config = {"company": {"id": "test"}, "rdp": [{
                "id": "vm", "host": "example.test", "username": "user",
                "keepass": {"uuid": "f" * 32},
            }]}
            for code, diagnostic, expected in [
                (0, "", 0), (1, "", 0), (2, "", 0), (11, "", 0), (145, "", 0),
                (131, "ERRCONNECT_CONNECT_CANCELLED", 0),
                (131, "", 131), (131, "ERRCONNECT_AUTHENTICATION_FAILED", 131),
                (132, "ERRCONNECT_CONNECT_CANCELLED", 132),
            ]:
                for manual in (True, False):
                    with self.subTest(code=code, diagnostic=diagnostic, manual=manual), \
                         patch.object(outs, "select_rdp_client", return_value=str(client)), \
                         patch.object(outs, "rdp_window_class", return_value="fixture"), \
                         patch.object(outs, "lookup_keepass_password", side_effect=lambda _: bytearray(b"fixture")), \
                         patch.object(outs, "active_vpn_names", return_value=[]) as vpn, \
                         contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        flags = ["--manual"] if manual else []
                        result = outs.handle_rdp("test", config, [
                            "vm", *flags, "--debug", "--", f"/fixture-exit:{code}",
                            f"/fixture-diagnostic:{diagnostic}",
                        ])
                        self.assertEqual(result, expected)
                        if expected == 0:
                            vpn.assert_not_called()

    def test_fast_successful_detached_exit_is_not_an_error(self):
        for code in (0, 1, 2, 11, 145):
            with self.subTest(code=code), patch.object(outs, "active_vpn_names") as vpn:
                process = Mock(pid=123)
                process.poll.return_value = code
                self.assertEqual(outs.report_detached_rdp(process), 0)
                vpn.assert_not_called()

    def test_fast_failed_detached_exit_remains_an_error(self):
        process = Mock(pid=123)
        process.poll.return_value = 131
        with patch.object(outs, "active_vpn_names", return_value=[]), \
             self.assertRaisesRegex(outs.OutsError, "code 131"):
            outs.report_detached_rdp(process)

    def test_line_protocol_rejects_control_characters_in_password_and_wipes_it(self):
        for character in (b"\n", b"\r", b"\0"):
            with self.subTest(character=character), patch.object(outs.subprocess, "Popen") as launch:
                password = bytearray(b"secret" + character + b"/drive:fixture,/tmp")
                with self.assertRaisesRegex(outs.OutsError, "RDP password"):
                    outs.run_rdp_with_password(["fake-rdp", "/v:example.test"], password, False)
                launch.assert_not_called()
                self.assertEqual(set(password), {0})

    def test_command_rejects_control_characters_before_launch_in_both_modes(self):
        for character in ("\n", "\r", "\0"):
            for manual in (True, False):
                with self.subTest(character=character, manual=manual), \
                     patch.object(outs.subprocess, "Popen") as launch:
                    password = None if manual else bytearray(b"secret")
                    with self.assertRaisesRegex(outs.OutsError, "RDP argument"):
                        outs.run_rdp(["fake-rdp", "/t:fixture" + character + "/v:other"],
                                     detached=False, password=password)
                    launch.assert_not_called()
                    if password is not None:
                        self.assertEqual(set(password), {0})


if __name__ == "__main__":
    unittest.main()
