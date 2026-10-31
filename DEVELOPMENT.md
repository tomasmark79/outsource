# Development

User setup and troubleshooting belong in [README.md](README.md). Released changes
belong in [CHANGELOG.md](CHANGELOG.md). Keep durable maintenance information here;
completed implementation plans remain available in Git history.

## Source layout

| Path | Responsibility |
| --- | --- |
| `bin/outs` | CLI, dispatch, remote clients, credentials, and launcher generation |
| `bin/connections.py` | Graphical connection manager and profile editing |
| `bin/activity_log.py` | Per-invocation logs, filtering, and retention |
| `bin/completion.py`, `completions/outs.bash` | Configuration-only Bash completion |
| `bin/vpn_runtime.py` | Private VPN runtime files, locking, and recovery state |
| `assets/` | Desktop entries and icons |
| `tests/` | Isolated regression tests |
| `package.nix` | Package contents, client dependencies, and SSH terminal variant |
| `module.nix` | Optional NixOS module |
| `flake.nix`, `.github/workflows/ci.yml` | Development environment and build checks |

The CLI remains the shared integration point. Keep modules with a clear purpose;
neither merging them into one file nor splitting each command improves the user
workflow by itself. Extract code when a concrete change benefits from a separate,
testable responsibility. Preserve existing connection records and launcher IDs.

## Checks

From the project root, optionally inside `nix develop`:

```bash
python3 -m unittest discover -s tests -v
nix flake check --no-update-lock-file
nix build --no-update-lock-file
```

Tests use temporary directories and mock clients; they do not open real connections
or databases. The desktop `Exec` regression test uses the actual Gio parser and is
skipped outside Nix if `gio` is unavailable. Package checks also validate desktop
files. The flake declares `x86_64-linux` and `aarch64-linux`; a native check does not
verify the other architecture or hardware.

## Packaging

The source allowlist in `package.nix` includes application files, tests, and public
documentation. Real profiles, databases, credentials, and logs stay in user XDG
directories. Installed documentation keeps the same relative layout as the root
Markdown files. Source references in this guide describe the checkout; source
files are not installed alongside the documentation.

The private GNOME Console variant closes the SSH terminal after its command ends
and supplies its window identity and icon. Its patch and removal criteria are
documented beside `sshTerminal` in `package.nix`. Reassess it when updating GNOME
Console, including a live GNOME window check; ordinary documentation changes do
not require updating the dependency or revisiting desktop behavior.

## Manual verification

For wizard changes, use temporary XDG configuration and data directories to check
creation, cancellation, editing, and removal. Editing must preserve connection
and desktop IDs. Do not use a real database or host for this smoke test.

For changes affecting client windows, separately check SSH, full-desktop RDP,
RemoteApp, and virt-viewer in GNOME. Launch from the application menu and confirm
grouping under the launcher's icon without an extra generic client icon. Close
an SSH session with Ctrl+D and confirm that its terminal closes. RemoteApp also
needs checks of movement, multiple monitors, sharpness, input, and responsiveness.
Use a real remote connection only when requested, and preserve unsaved work.

Passing tests and builds proves neither live desktop integration nor activation.
Push, release, and host activation are separate operations. Adding connections
after installation does not require a rebuild.

## Verification history

- **2.2.0, 2026-10-25:** 102 tests, native flake checks, and package build passed on
  `x86_64-linux`. A temporary-data GNOME/Wayland smoke test covered wizard
  cancellation, SSH creation with system authentication, editing with stable IDs,
  removal, English dialogs, and the SSH terminal's identity and title using a
  local command. Visual dock grouping and actual remote/database access were not
  verified. GitHub Actions was disabled during that release verification.
- **RemoteApp implementation, 2026-10-31:** the initial optional-field change passed
  109 tests; subsequent native SDL3/Wayland defaults passed 114 tests, native flake
  checks, and package build. Regression coverage includes validation, editing,
  client selection, authentication, option precedence, child-only environment
  changes, and unchanged desktop RDP behavior.
- **RemoteApp investigation:** authorized live tests using FreeRDP 3.32.0 favored
  native Wayland over XWayland, 1:1 pixels with 150% Windows scaling, and
  `AVC444,frame-ack:off`. Temporary instrumentation measured input queue age below
  about 4 ms and handler time below 0.4 ms during a reported delay; these are not
  end-to-end latency measurements. Windows updates were in progress during the
  comparison. The user subsequently reported RemoteApp working after removing
  `KB5127936`, and Bitwig mouse input working with Absolute Mouse Mode enabled.
  These reports do not establish a general Windows regression or verify grouping
  of the final Outsource launcher. Timing instrumentation is not shipped.

Historical test counts describe those changes; run the current checks before
claiming the present checkout passes. GNOME visual grouping remains a manual
check. No release or activation follows automatically from a successful build.
