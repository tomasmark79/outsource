# Outsource

A simple wizard for RDP, SSH, and virt-viewer launchers in the GNOME application menu.
Nix installs the application and its clients. You can then add and edit connections
without editing Nix or JSON files or rebuilding your system.

## Installation

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
  Supply the UUID of the password entry in KeePassXC and enable clipboard sharing,
  audio, or multiple monitors as needed. When connecting, enter the database master
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
store. See the [KeePassXC guide](docs/keepassxc.md) for details and the lifetime of
temporary VPN keys.

SSH does not open the database by default. If your keys are in KeePassXC, you can
use its SSH agent integration and keep system authentication selected in the wizard.

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

## Development and verification

From the project root:

```bash
python3 -m unittest discover -s tests -v
nix flake check --no-update-lock-file
nix build --no-update-lock-file
```

Tests use temporary directories and mock clients; they do not open real connections
or databases. The `Exec` regression test uses the actual Gio parser. Outside Nix,
this test requires `gio` and is skipped if it is unavailable.

[package.nix](package.nix) packages the application, clients, and desktop files.
[module.nix](module.nix) adds the package to NixOS. The private GNOME Console variant
provides automatic SSH terminal closing and window identity; the package recipe
documents why it is needed and when it can be removed. The regular GNOME Console
remains separate.

CI checks the flake, tests, and build without local checkouts. A successful build
does not replace activation or live verification of window grouping in GNOME.
A new system version becomes available after rebuilding and activating the host;
adding connections afterward does not require activation.

License: [MIT](LICENSE).
