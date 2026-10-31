# Outsource

A simple wizard for RDP, SSH, and virt-viewer launchers in the GNOME application menu.
Nix installs the application and its clients. You can then add and edit connections
without editing Nix or JSON files or rebuilding your system.

[Install](#installation) · [Manage connections](#adding-a-connection) ·
[KeePassXC](#keepassxc) · [RemoteApp](#windows-remoteapp) ·
[Troubleshooting](#troubleshooting) · [Development](DEVELOPMENT.md)

## Supported environment

Outsource is packaged for Linux with Nix and is intended for NixOS with the GNOME
desktop. The graphical wizard uses Zenity; SSH launchers use a private GNOME Console
variant, while RDP and virtual machine consoles use FreeRDP and virt-viewer.
Desktop window grouping is designed for GNOME. Other desktops and installations
without Nix are not currently supported.

Release checks run on `x86_64-linux`. The flake also declares `aarch64-linux`, but
that platform has not been verified on hardware.

## Installation

Install the published 2.2.0 release into your user profile:

```bash
nix profile install github:tomasmark79/outsource/v2.2.0
```

Then open **Remote Connections** in the application menu, or run `outs manage`.
To try the wizard without installing it:

```bash
nix run github:tomasmark79/outsource/v2.2.0 -- manage
```

This standalone project provides a Nix package and an optional NixOS module.
From a checkout:

```bash
nix run . -- manage
nix build
```

To install it in your user profile, run `nix profile install .`.
The connection manager and new connection wizard appear in the application menu.
On NixOS, add `outsource.nixosModules.default` to your modules and set
`programs.outsource.enable = true`. Use `programs.outsource.package` to select
a custom package, for example one with a different KeePassXC variant.
For a release-pinned NixOS input, use
`outsource.url = "github:tomasmark79/outsource/v2.2.0"` in your flake inputs.

The host system manages networking, NetworkManager activation, the OpenVPN plugin,
and libvirt permissions. The module does not change them automatically.
Installation and updates do not move user data.

## Adding a connection

Open **Add Remote Connection** in the application menu, or run:

```bash
outs new
```

Select a connection type, enter a launcher name and connection details, then confirm
the save. The launcher appears in the application menu and can be pinned to the dock.
Canceling the wizard does not create an incomplete connection.

- **RDP:** enter the address, username, port, and optional Windows domain.
  For a single Windows application, fill in **RemoteApp application**, for example
  `||notepad` (a published alias) or `C:\Windows\System32\notepad.exe`.
  Leave it blank for the full remote desktop; see [Windows RemoteApp](#windows-remoteapp)
  for server setup and display settings.
  Supply the UUID of the password entry in KeePassXC. In **RDP audio playback**,
  choose **Play audio on this computer** (`local`, the default), **Play audio on
  the remote computer** (`remote`), or **Do not play audio** (`off`). This choice
  is also available when editing a launcher and applies to full-desktop RDP and
  RemoteApp. Clipboard sharing and multiple monitors are separate options.
  When connecting, enter the database master
  password in a graphical dialog. FreeRDP runs without an extra terminal.
  Closing the window or logging out does not open another dialog; a connection
  error displays a message with the log path.
- **SSH:** enter an alias from `~/.ssh/config` or a server address. Leave the username
  and port blank to use OpenSSH settings. System SSH configuration, `ProxyJump`,
  keys, and the SSH agent also apply. The connection opens in a terminal with the
  SSH launcher icon. The terminal closes when the session ends, including with
  Ctrl+D. This uses a private GNOME Console variant; the regular terminal is
  unaffected. Alternatively, supply an entry UUID and the name of a key attachment
  in KeePassXC.
- **Virt-viewer:** enter a virtual machine name or UUID and a libvirt connection,
  such as `qemu:///system`. A graphical window opens directly without a terminal.

RDP and virt-viewer use a window identity matching their launcher so GNOME can
associate the running window with its icon.

## Editing and removing connections

Open **Remote Connections**, or run:

```bash
outs manage
```

The manager lets you add, edit, or remove a launcher and configure the database.
Changes apply the next time you connect. Removing a connection deletes its launcher
and local settings; it does not change the server or the KeePassXC entry.

## KeePassXC

Enter the UUID of the password entry when configuring a connection. Copy it from
the entry's **Properties** tab in KeePassXC. UUIDs with hyphens and braces or just
32 hexadecimal characters are accepted. The current UUID is prefilled when editing
a connection and is stored as `record.keepass.uuid` in the connection file.

The wizard does not unlock the database or read its entry list when creating a
launcher. If the database location has not been configured, it asks for a `.kdbx`
file and an optional key file. The password is read using the stored UUID only when
connecting. The wizard checks the UUID format; the entry's existence is checked
when connecting. Renaming or moving an entry within the database preserves the link.

Change the database settings in the manager, or run:

```bash
outs keepass
```

The wizard uses `keepassxc-cli`. Even if the database is open in KeePassXC, reading
it requires the master password again. A master password and an optional key file
are supported. Passwords and private keys are never stored in launchers or the Nix
store. This integration does not use Secret Service or change GNOME Keyring.

SSH does not open the database by default. If your keys are in KeePassXC, you can
use its SSH agent integration and keep system authentication selected in the wizard.

### Credentials and temporary files

Database and optional key file paths are local to this machine. The wizard saves
them in `~/.config/outsource/config.local.json`:

```json
{
  "keepass": {
    "database": "/path/to/database.kdbx",
    "key_file": "/path/to/key-file"
  }
}
```

Omit `key_file` or set it to `null` when unused. Each RDP record refers to an entry
with `"keepass": {"uuid": "faa054617a774d8bad6a27cb673d9141"}`. Outsource locates
the entry by UUID, then reads its password. The master password reaches the
short-lived KeePassXC processes through standard input. FreeRDP receives its
arguments through `/args-from:stdin`, keeping passwords out of the process list,
environment, and temporary files.

For an SSH key attachment, Outsource verifies the resolved entry's UUID before
exporting the key to a random temporary file with mode `0600`. It removes the file
when SSH exits and does not modify the SSH configuration or agent. Normal cleanup
also runs on `SIGTERM` and `SIGHUP`; it cannot run after `SIGKILL` or a system crash.

Legacy web records use the entry's `URL` and `UserName` fields. Authentication is
left to KeePassXC-Browser; the password is not put in URLs, browser arguments, or
the clipboard.

### Legacy VPN connections

Company profiles can reference an OpenVPN profile stored as a KeePassXC attachment.
`vpn-up` exports it under `$XDG_RUNTIME_DIR/outsource/vpn`, imports a temporary
NetworkManager profile, and removes the attachment file after activation.
The logged-in session must supply an `XDG_RUNTIME_DIR` with mode `0700`.
`NM_CERT_PATH` keeps extracted certificates and keys in the private runtime
directory for the entire VPN session, including reconnections.

The entry's `UserName` and `Password` supply the VPN credentials. The password is
passed through a `0600` `nmcli passwd-file`, removed after activation. Profile
changes also use `--temporary`; credentials are not saved in a persistent profile.
Runtime `state.json` contains only the imported profile's UUID and name, with mode
`0600`. A name derived from the company and VPN alias and a lock separate sessions.

Exiting `vpn-up` leaves the VPN connected. Run `vpn-down` before another `vpn-up`;
it deletes the exact NetworkManager profile by UUID before removing certificates.
Failed or interrupted startup is cleaned up. If profile deletion fails, runtime
state is retained for a retry so a running VPN keeps its certificates.
Runtime files disappear after reboot. If NetworkManager retains a profile after
its runtime state disappears, Outsource reports its UUID for manual removal
instead of claiming ownership or success. This also applies to profiles with
legacy `outs-company-alias` names.

## Windows RemoteApp

RemoteApp opens an allowed Windows application as a separate window on the Linux
desktop. The application remains installed and runs on Windows. Enabling ordinary
Remote Desktop alone does not publish RemoteApp applications.

On Windows Server, publish the application through the Remote Desktop Services
collection. On supported desktop Windows editions, a publisher such as
[RemoteApp Tool](https://github.com/kimmknight/remoteapptool) can configure it.
See its [Windows compatibility list](https://github.com/kimmknight/remoteapptool/wiki/Windows-Compatibility).
The value `||notepad` requires an application published with the alias `notepad`;
it is not an automatic alias for every installed Notepad. An executable path must
also be permitted by the Windows host.

In `outs new` or `outs edit`, set **RemoteApp application** to that alias or path.
Enter only the program, without arguments, commas, or quotes; paths with spaces
are supported. Clearing the field restores full-desktop RDP while preserving the
connection ID and launcher. External RDP records use the same `remoteapp` string.

RemoteApp defaults are:

| Setting | Value | Purpose |
| --- | --- | --- |
| Client | `sdl-freerdp` or `sdl-freerdp3` | SDL3 client from FreeRDP 3.32 or newer |
| `SDL_VIDEODRIVER` | `wayland` when `WAYLAND_DISPLAY` is available | Native Wayland windows |
| `SDL_VIDEO_WAYLAND_SCALE_TO_DISPLAY` | `1` | Map pixels 1:1 instead of enlarging a low-resolution image |
| `/scale-desktop` | `150` | Let Windows render larger desktop application controls and text |
| `/bpp` | `32` | 32-bit session color depth |
| `/gfx` | `AVC444,frame-ack:off` | AVC444 graphics without waiting for frame acknowledgements |

These defaults apply to RemoteApp, including GUI launchers, manual authentication,
and KeePassXC authentication. Full-desktop RDP retains its existing defaults.
The SDL environment is set for the child client only. X11-only sessions do not
force the Wayland backend. The packaged client supports SDL3 RemoteApp; upstream
introduced it as a beta feature in [FreeRDP 3.32](https://www.freerdp.com/2026/09/23/3_32_0-release).

An explicit `RDP_CLIENT` override is still honored. That client must support
RemoteApp and the configured graphics options; the normal path uses SDL3 rather
than falling back to XWayland.

To change the size for a particular display, add `freerdp_args` to the connection's
`record` or to a company RDP record. For example, this record fragment selects 125%:

```json
{
  "remoteapp": "||notepad",
  "freerdp_args": ["/scale-desktop:125"]
}
```

Record options override built-in defaults. For company-style CLI commands,
FreeRDP arguments after `--` override record options. Replacing `/gfx` replaces
the entire option, so include `frame-ack:off` when retaining that behavior.
Removing `/scale-desktop` alone is not a solution for compositor resampling;
pixel mapping and Windows DPI control different parts of the display path.

Sharpness, multi-monitor behavior, application DPI support, and responsiveness
must be checked in a real session. AVC444 is not a guarantee of lossless output.
Upstream documents [frame-ack:off as a connection-delay diagnostic](https://www.freerdp.com/2024/07/04/3_6_2-release);
it improved responsiveness in the authorized live investigation behind these
defaults. See [verification history](DEVELOPMENT.md#verification-history) for the
evidence and outstanding desktop checks.

## Data locations

- `~/.config/outsource/connections/`: connections created by the wizard, one file each.
- `~/.config/outsource/config.local.json`: database and optional key file paths.
- `~/.local/share/applications/outs-local-*.desktop`: generated launchers.

`XDG_CONFIG_HOME`, `XDG_DATA_HOME`, and `OUTSOURCE_LOCAL_CONFIG` are also supported;
the last overrides the database settings location. Connection files and database
settings use mode `0600`. The application does not read configuration from its
source directory or the Nix store. Back up `~/.config/outsource` to preserve your
connections. Back up the KeePassXC database and key file at their actual locations.

## Activity logs

Each connection or wizard invocation creates a separate file in
`~/.local/share/logs/outsource/`, or `$XDG_DATA_HOME/logs/outsource/` when
`XDG_DATA_HOME` is set. File names include a UTC timestamp and process ID.
Files use mode `0600`; newly created log directories use `0700`.

Logs contain timestamps, action types, connection IDs, KeePassXC operations, and
exit codes. Graphical RDP and virt-viewer sessions also capture recognized client
diagnostics. For terminal RDP, diagnostics are available with `--debug`.
Error dialogs and terminal messages include the relevant log path.

Passwords, database entry UUIDs, private keys, command arguments, remote terminal
contents, and full client output are not logged. Diagnostics record only known
error codes and generic causes. SSH records startup and the exit code; detailed
errors remain in its terminal.

At startup, logs older than 30 days are pruned and at most 100 files are retained.
Open logs are skipped, so concurrent sessions may temporarily exceed this limit.
Each log is limited to approximately 2 MiB. Legacy commands that start a client in
the background record the handoff and PID, rather than the later end of the session.

To list the latest logs:

```bash
ls -lt ~/.local/share/logs/outsource/
```

## Terminal usage

The package includes Bash completion for commands, saved connection IDs, companies
and their aliases, targets, and basic flags. Open a new shell after installation.
Only connection types with saved targets are offered. For `outs connect `, pressing
Tab twice displays connection names alongside IDs; only the ID is inserted.
When working directly from a checkout, run `source completions/outs.bash` and make
sure `outs` is in `PATH`. Completion only reads configuration; it does not open
connections or KeePassXC and does not create activity logs.

Run a connection with `outs connect <id>`; the ID is its file name without `.json`.
Use `outs connect <id> --gui` for graphical password entry and error reporting.
For SSH, use the terminal launcher.

Legacy company commands for web, VPN, and other access remain available.
Their optional profiles are read from
`~/.config/outsource/clients/<company>/config.json` or `OUTSOURCE_CLIENTS_DIR`.
No company profiles are included in this project.

## Troubleshooting

For a failed connection, start with the log path shown in the error message;
see [activity logs](#activity-logs). For legacy company RDP commands,
`outs example rdp workstation --debug` shows client output in the terminal.
Add `--manual` to test manual authentication instead of KeePassXC.

If a RemoteApp application has jumping knobs or erratic mouse dragging, try its
absolute mouse input mode. In Bitwig, enabling **Absolute Mouse Mode** in the
user interface settings resolved the problem in a user-reported RemoteApp session.

If RemoteApp stops working after a Windows update, check the host's update history
as well as the client log. The user reported that removing Windows update
`KB5127936` restored RemoteApp in one session; this is a troubleshooting observation,
not a confirmed general cause or a recommendation to remove security updates.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for the source layout, checks, packaging, and
manual desktop verification, and [CHANGELOG.md](CHANGELOG.md) for release changes.

License: [MIT](LICENSE).
