# Windows RemoteApp support

## Intent

Launch a remote Windows application in its own window on a Linux desktop using
RDP RemoteApp. Keep desktop RDP as the default for existing connections.

## Approach

Extend the existing RDP record with an optional `remoteapp` object containing
`program`, optional `cmd`, and optional `workdir`. A program can be a published
alias such as `||notepad` or a Windows executable path permitted by the server.
Reuse the current connection editor, credentials, launchers, and startup handling.
The user confirmed Windows RemoteApp as the target.

A separate connection type would duplicate RDP configuration and credential
handling. Requiring raw FreeRDP arguments alone would omit discoverable editing
and validation. Extending the RDP profile is the proposed implementation.

## Behavior and constraints

- The RDP editor offers desktop or RemoteApp mode and edits the application fields.
  Switching to desktop mode removes the RemoteApp settings.
- Validate the settings before starting a client, including rejecting NUL and
  newline characters. Encode values according to FreeRDP's application syntax.
- Select a FreeRDP client supporting RemoteApp; on GNOME Wayland an X11 client
  can run through XWayland. Check the packaged client capabilities.
- Preserve connection IDs, desktop IDs, existing credential handling, and existing
  RDP behavior. Do not create server configuration or change real profiles.
- The Windows host must support and permit RemoteApp. Client support alone does
  not enable RemoteApp on an unconfigured Windows installation.

## Verification

Use temporary profiles and mocked clients to cover validation, argument
construction, client selection, editing, switching modes, and compatibility.
Run the Python suite, `nix flake check --no-update-lock-file`, and
`nix build --no-update-lock-file`. Commit verified changes locally.

Document manual checks for a real Windows RemoteApp session, window behavior,
and GNOME grouping; these cannot be established by unit tests. Do not connect to
real hosts, unlock databases, activate, push, or release during this work.

## Reference

FreeRDP application options:
https://pub.freerdp.com/api/client_2common_2cmdline_8h_source.html
