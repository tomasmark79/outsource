{
  lib,
  stdenvNoCC,
  makeWrapper,
  python3,
  freerdp,
  keepassxc,
  networkmanager,
  openssh,
  virt-viewer,
  iproute2,
  xdg-utils,
  zenity,
}:
stdenvNoCC.mkDerivation {
  pname = "outsource";
  version = "2.0.0";
  # Explicitní seznam: lokální nastavení a trezor se nesmějí dostat do store.
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./bin/outs
      ./bin/connections.py
      ./bin/activity_log.py
      ./assets
      (lib.fileset.fileFilter (file: file.hasExt "py") ./tests)
    ];
  };
  nativeBuildInputs = [ makeWrapper ];
  nativeCheckInputs = [ python3 ];
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    python3 -m unittest discover -s tests
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/share/outsource" "$out/bin" "$out/share/icons/hicolor/scalable/apps"
    cp -r bin assets "$out/share/outsource/"
    cp assets/*.svg "$out/share/icons/hicolor/scalable/apps/"
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
    description = "Průvodce vzdálenými připojeními a zástupci s KeePassXC";
    mainProgram = "outs";
    platforms = lib.platforms.linux;
  };
}
