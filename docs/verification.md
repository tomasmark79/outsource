# Release verification

## 2.2.0

Verified on 2026-10-25 on `x86_64-linux` with NixOS, GNOME, and Wayland.

### Automated checks

- All 102 Python tests passed using temporary directories and mock clients.
- `nix flake check --no-update-lock-file` passed for the native platform.
- `nix build --no-update-lock-file` passed.
- The built package includes English help, desktop launchers, documentation, and
  Bash completion. Connection and desktop identifiers remain unchanged.

### Live first-run smoke test

The built package was exercised in a running GNOME session with separate temporary
XDG configuration and data directories. No real connection or KeePassXC database
was opened.

- Canceling the new-connection wizard created neither a connection nor a launcher.
- The SSH wizard created a launcher using system authentication with the username
  and port left blank. No KeePassXC reference was created.
- Editing the connection changed its name while preserving its connection and
  desktop identifiers.
- Removing the connection deleted its temporary configuration and desktop file.
- English labels, confirmation dialogs, and success messages were checked through
  the actual dialogs' accessibility interfaces.
- The packaged SSH terminal opened in the Wayland session with its custom identity
  and title while running only a local command. The test launcher was removed afterward.

### Remaining manual checks

Visual dock grouping was not verified: Shell window introspection was denied and
the screenshot service could not capture the desktop. Accessibility confirmed the
test window title in the overview, but that alone does not prove correct grouping
or icon appearance.

Before claiming full desktop integration, launch a new connection from its
application-menu entry and check that it appears under that launcher's icon in
the dash, without an extra generic client icon. Check SSH, RDP, and virt-viewer
separately. Close the test SSH session with Ctrl+D and confirm that its terminal
closes. Do not close windows with unsaved work.

Actual RDP, SSH, libvirt, VPN, and KeePassXC access was deliberately excluded from
this offline smoke test. Successful unit tests and package builds are not evidence
of a successful remote session or live window grouping.
