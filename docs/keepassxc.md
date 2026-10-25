# KeePassXC

KeePassXC is the single source of truth for passwords, web credentials, API tokens,
private keys, recovery codes, and sensitive notes. Shared configuration contains
only the entry UUID, never its title, group, or password.

SSH uses `~/.ssh/config`, system OpenSSH settings, and the SSH agent by default.
It does not override the username or port unless you supply them. KeePassXC can
pass stored keys directly to the agent; the launcher then does not unlock the database.

Alternatively, select a key stored as an entry attachment. In this mode, the launcher
exports the key to a random temporary file with mode `0600` for each session and
removes it when SSH exits. Before exporting, it also verifies the UUID of the entry
returned at that path: two entries with the same title in the same group must not
cause the wrong key to be loaded. Neither `~/.ssh/config` nor the agent is modified.

On `SIGTERM` and `SIGHUP`, the launcher performs normal cleanup of the SSH key and
any VPN operation in progress. Cleanup cannot be guaranteed after `SIGKILL` or a
system crash.

Web records also contain only a UUID. The launcher reads the entry's `URL` and
`UserName` fields, opens the URL in the default browser, and leaves authentication
to KeePassXC-Browser. The password is never inserted into the URL, browser
arguments, or clipboard.

An OpenVPN profile can be stored as an entry attachment. `vpn-up` exports it by UUID
to a private directory under `$XDG_RUNTIME_DIR/outsource/vpn`, imports it into
NetworkManager with `--temporary`, and removes the original file after activation.
Subsequent profile changes also use `--temporary` to avoid saving it to disk.
The logged-in session must provide its own `XDG_RUNTIME_DIR` with mode `0700`;
VPN startup is refused without it.

During import, the OpenVPN plugin writes embedded certificates and keys to separate
files. Outsource sets `NM_CERT_PATH` to the same private runtime directory.
These files remain available throughout the VPN session, including reconnections.
The `--temporary` flag alone does not manage their lifetime.

`vpn-down` deletes the NetworkManager profile using its saved UUID, then removes
the runtime directory containing its certificates. Exiting `vpn-up` does not
disconnect the VPN. If import or activation fails or is interrupted, the launcher
cleans up the profile and files. If NetworkManager is unreachable or deletion
fails, local state is retained so `vpn-down` can be retried; removing certificates
could disrupt a VPN that is still running. Runtime files disappear after a reboot.

The internal name is a hash of the company and VPN alias pair. The saved UUID
identifies the exact profile even if its name changes, and a lock prevents
concurrent operations on the same pair. Run `vpn-down` before repeating `vpn-up`.

If NetworkManager still has the profile but its runtime state has disappeared,
for example after logout, Outsource refuses to take ownership of it or report a
successful shutdown. The error includes its UUID for manual disconnection and
removal in NetworkManager. Existing profiles using the legacy `outs-company-alias`
naming scheme are handled the same way.

The same entry's standard `UserName` field becomes the OpenVPN username.
Its `Password` field is passed during activation through `nmcli passwd-file`.
This file uses mode `0600` and is removed after activation. The password does not
appear in process arguments or a persistent profile.

The runtime `state.json` also uses mode `0600` and contains only the UUID and import
name needed for recovery after interruption. Passwords and attachment contents
are never stored there.

## Automatic RDP passwords

`outs` unlocks one KDBX database through `keepassxc-cli`. The database and optional
key file locations are machine-specific, so they belong in the local file
`~/.config/outsource/config.local.json`, outside the repository:

```json
{
  "keepass": {
    "database": "/path/to/database.kdbx",
    "key_file": "/path/to/key-file"
  }
}
```

If you do not use a key file, omit `key_file` or set it to `null`.
Run `outs keepass` to configure these paths graphically.

Each RDP record references an entry as follows:

```json
"keepass": { "uuid": "faa054617a774d8bad6a27cb673d9141" }
```

The launcher first searches for `uuid:<UUID>` and passes the resulting path to
another KeePassXC command. You can rename or move the entry without changing the
configuration. Copy its UUID from the **Properties** tab.

A new RDP launcher opens a graphical dialog for the database master password.
The launcher supplies the key file if configured. Enter the UUID manually in the
wizard; it is prefilled when editing. The wizard checks the UUID format without
unlocking the database or reading its entry list. The entry's existence is checked
when connecting. An unlocked KeePassXC window does not authenticate `keepassxc-cli`,
so the master password is required again. This integration does not use Secret
Service and does not modify or disable GNOME Keyring.

For diagnostics, run `outs example rdp workstation --debug`; FreeRDP stays in the
foreground and its output appears live in the terminal. Use `--manual` for fallback
manual authentication; both flags can be combined. Activity logs contain progress
and exit codes, but not full client output. Recognized diagnostics are recorded for
graphical launchers and in `--debug` mode.

All FreeRDP arguments, including the password, are passed through `/args-from:stdin`.
Only this flag appears in the process list. The password is never written to Git,
process arguments, environment variables, or a temporary file. The launcher asks
for the master password once and passes it to two short-lived `keepassxc-cli`
processes only through standard input, never through arguments or the environment.

Legacy terminal commands without `--debug` start FreeRDP in the background after
passing the arguments. New graphical launchers do not open a terminal; the helper
waits for the client to exit so it can display an error dialog if the connection fails.
