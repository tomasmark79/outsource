# Minimal RemoteApp Implementation Plan

**Goal:** Open a Windows RemoteApp window on Linux from an existing RDP profile.
**Architecture:** Optional `record.remoteapp` string; empty means desktop RDP.
Reuse the credential and launcher paths, preferring xfreerdp for RemoteApp.
**Tech Stack:** Python, Zenity, FreeRDP, Nix.
**Spec:** ../specs/2026-10-31-remoteapp-design.md

## Constraints and review focus

Preserve profile and desktop IDs and normal desktop RDP behavior. Reject invalid
RemoteApp values before credentials are accessed. Test aliases and Windows paths
with spaces, clearing the field, and missing compatible clients. Use temporary
profiles and mock clients; no remote sessions or real databases.

## Implementation

- [x] Add failing tests in `tests/test_rdp.py` and `tests/test_connections.py`
  covering command construction, validation, client selection, and wizard edits.
- [x] Add `rdp_remoteapp(record)` validation in `bin/outs`, build the application
  argument, and select xfreerdp for these profiles. Existing raw arguments retain
  their normal override precedence.
- [x] Add the optional field to creation and editing in `bin/connections.py`.
  Empty input removes the setting; saving reuses the same connection ID.
- [x] Document usage and the Windows server prerequisite in `README.md`.
- [x] Run the Python suite, flake check, and package build; inspect the diff and
  create a local commit. Record that live GNOME grouping remains unverified.

## Verification record

All 109 Python tests passed. Native `x86_64-linux` flake checks and the package
build passed. The new tests failed before implementation and passed afterward.
No real remote session or database was opened. Live RemoteApp window behavior
and GNOME grouping remain unverified. No dependency update was needed; the private
GNOME Console exception serves SSH and is unaffected by this RDP change.
