# Windows RemoteApp support

## Intent

Launch a remote Windows application in its own window on a Linux desktop using
RDP RemoteApp. Keep desktop RDP as the default for existing connections.

## Approach

Extend the existing RDP record with an optional `remoteapp` string. A program can be a published
alias such as `||notepad` or a Windows executable path permitted by the server.
Reuse the current connection editor, credentials, launchers, and startup handling.
The user confirmed Windows RemoteApp as the target and requested a minimal extension.

A separate connection type would duplicate RDP configuration and credential
handling. Requiring raw FreeRDP arguments alone would omit discoverable editing
and validation. Extending the RDP profile is the proposed implementation.

## Behavior and constraints

- The RDP editor adds one optional application field. Leaving it blank removes
  RemoteApp settings and uses desktop mode. No extra application options are added.
- Validate the settings before starting a client, including rejecting NUL and
  newline characters. Encode values according to FreeRDP's application syntax.
- Use the SDL3 FreeRDP client (3.32 or newer). On Wayland, use its native backend
  with 1:1 pixel mapping, 150% desktop scaling, 32-bit color, and
  `AVC444,frame-ack:off`. Keep full-desktop defaults unchanged and retain the
  existing record/CLI option override precedence. An explicit client override
  remains available. See the README's Windows RemoteApp section for usage.
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
and GNOME grouping; these cannot be established by unit tests. Routine automated
checks do not connect to real hosts or unlock databases. Authorized live
investigation is recorded separately in docs/verification.md. Activation, push,
and release remain separate actions requiring explicit requests.

## Reference

FreeRDP application options:
https://pub.freerdp.com/api/client_2common_2cmdline_8h_source.html
