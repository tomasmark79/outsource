{
  description = "Outsource: remote RDP, SSH, and libvirt connections with KeePassXC";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      eachSystem = nixpkgs.lib.genAttrs systems;
      packageFor = system: nixpkgs.legacyPackages.${system}.callPackage ./package.nix { };
    in
    {
      packages = eachSystem (system: {
        default = packageFor system;
        outsource = self.packages.${system}.default;
      });
      apps = eachSystem (system: {
        default = {
          type = "app";
          program = nixpkgs.lib.getExe self.packages.${system}.default;
          meta.description = "Manage remote connections";
        };
      });
      checks = eachSystem (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          tests =
            pkgs.runCommand "outsource-tests"
              {
                nativeBuildInputs = [
                  pkgs.bashInteractive
                  pkgs.python3
                  pkgs.glib.bin
                ];
                src = self.packages.${system}.default.src;
                PYTHONDONTWRITEBYTECODE = "1";
              }
              ''
                cp -r "$src" source
                chmod -R u+w source
                cd source
                python3 -m unittest discover -s tests -v
                touch "$out"
              '';
        }
      );
      devShells = eachSystem (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.python3
              pkgs.glib.bin
              pkgs.nixfmt
            ];
          };
        }
      );
      formatter = eachSystem (system: nixpkgs.legacyPackages.${system}.nixfmt);
      nixosModules.default = import ./module.nix;
    };
}
