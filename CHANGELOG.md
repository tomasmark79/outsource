# Changelog

## Unreleased

- English interface, help, desktop launchers, documentation, and source comments.
- New activity logs use English field names and events; existing log files are unchanged.
- Bash completion for commands, connection IDs and names, company aliases, targets,
  and basic flags, offering only connection types with configured targets.

## 2.1.0

- Standalone Nix flake, NixOS module, desktop files, development shell, and CI.
- Preserved history of the original `applications/outsource` directory from Nixon.
- Correct quoting of names and paths in desktop launchers, including a regression
  test using the actual Gio parser.
- Invalid profiles no longer block management of healthy connections; invalid
  server settings can be corrected in the wizard.
- IPv6 support and launchers that target the correct application installation.
- Consistent handling of normal exits in manual and automatic RDP sessions.
- UUID verification before exporting an SSH attachment from KeePassXC.
- Temporary VPN certificates tied to connection lifetime, unambiguous profiles,
  and reliable detection of the imported UUID.

User profiles and existing desktop identifiers remain compatible.
