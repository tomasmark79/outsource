# Working on Outsource

Keep the connection wizard and launchers simple and reliable.

- Write documentation and new comments in English.
- Keep existing profiles, CLI options, connection IDs, and desktop IDs compatible.
- Use temporary data and mock clients for routine checks. Keep real user data and
  credentials outside the repository and Nix store.
- Run the checks in [DEVELOPMENT.md](DEVELOPMENT.md#checks), then commit each
  verified change locally. Push, release, and system activation require a request.

Use [README.md](README.md) for user instructions and [DEVELOPMENT.md](DEVELOPMENT.md)
for architecture, packaging, and manual verification. Update those files rather
than adding separate implementation plans or duplicate guides.
