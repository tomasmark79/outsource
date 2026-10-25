# Project rules

- Write documentation and new comments in English. Keep technical interfaces unchanged.
- Real profiles, databases, keys, and activity logs belong in user XDG directories, never in the repository or Nix store.
- Tests use temporary directories and mock remote clients. Do not open real connections or databases during routine verification.
- Preserve existing connection IDs and desktop identifiers for compatibility with existing launchers. Unit tests do not replace live window grouping checks in GNOME.
- The private GNOME Console variant has a specific purpose documented in package.nix. After updates, check whether the exception can be removed.
- Create a local commit after each verified step. Push, release, and activate the system only when explicitly requested.

## Checks

```bash
python3 -m unittest discover -s tests -v
nix flake check --no-update-lock-file
nix build --no-update-lock-file
```
