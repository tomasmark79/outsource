{
  lib,
  stdenvNoCC,
  makeWrapper,
  installShellFiles,
  bashInteractive,
  python3,
  freerdp,
  keepassxc,
  networkmanager,
  openssh,
  virt-viewer,
  iproute2,
  xdg-utils,
  zenity,
  gnome-console,
  glib,
  desktop-file-utils,
}:
let
  # GNOME Console 50 has no CLI option to close a command session. This variant
  # also closes on Ctrl+D and sets the X11 window identity and SSH launcher icon.
  # Remove once upstream supports these options and a new window is verified in GNOME.
  sshTerminal = gnome-console.overrideAttrs (old: {
    postPatch = (old.postPatch or "") + ''
      substituteInPlace src/kgx-application.c \
        --replace-fail '"close-on-quit", argv == NULL,' '"close-on-quit", TRUE,'
      substituteInPlace src/main.c \
        --replace-fail 'g_set_prgname (KGX_BIN_NAME);' \
          'g_set_prgname (g_getenv ("OUTSOURCE_TERMINAL_ID") ?: KGX_BIN_NAME);' \
        --replace-fail 'gtk_window_set_default_icon_name (KGX_APPLICATION_ID);' \
          'gtk_window_set_default_icon_name ("outs-ssh");'
    '';
  });
in
stdenvNoCC.mkDerivation {
  pname = "outsource";
  version = "2.1.0";
  # Explicit allowlist: local settings and databases must never enter the store.
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      (lib.fileset.fileFilter (file: file.name == "outs" || file.hasExt "py") ./bin)
      ./assets
      ./completions
      ./LICENSE
      ./README.md
      (lib.fileset.fileFilter (file: file.hasExt "md") ./docs)
      (lib.fileset.fileFilter (file: file.hasExt "py") ./tests)
    ];
  };
  nativeBuildInputs = [ makeWrapper installShellFiles ];
  nativeCheckInputs = [
    bashInteractive
    python3
    glib.bin
    desktop-file-utils
  ];
  dontBuild = true;
  env.PYTHONDONTWRITEBYTECODE = "1";
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    python3 -m unittest discover -s tests
    desktop-file-validate assets/*.desktop
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/share/outsource" "$out/bin" "$out/share/icons/hicolor/scalable/apps" "$out/share/applications"
    cp -r bin assets "$out/share/outsource/"
    installShellCompletion --bash --name outs completions/outs.bash
    cp assets/*.svg "$out/share/icons/hicolor/scalable/apps/"
    cp assets/*.desktop "$out/share/applications/"
    mkdir -p "$out/share/doc/outsource"
    cp LICENSE README.md docs/*.md "$out/share/doc/outsource/"
    makeWrapper ${sshTerminal}/bin/kgx "$out/bin/outs-terminal" \
      --run 'if [[ "$1" == --gapplication-app-id=* ]]; then export OUTSOURCE_TERMINAL_ID="''${1#*=}"; fi'
    makeWrapper ${python3}/bin/python3 "$out/bin/outs" \
      --add-flags "$out/share/outsource/bin/outs" \
      --set OUTSOURCE_EXECUTABLE "$out/bin/outs" \
      --prefix PATH : ${
        lib.makeBinPath [
          freerdp
          keepassxc
          networkmanager
          openssh
          virt-viewer
          iproute2
          xdg-utils
          zenity
        ]
      }
    runHook postInstall
  '';
  meta = {
    description = "Remote connection and launcher wizard with KeePassXC integration";
    mainProgram = "outs";
    homepage = "https://github.com/tomasmark79/outsource";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
  };
}
