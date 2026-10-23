# Modul přidává pouze aplikaci; síť, libvirt a uživatelský trezor spravuje hostitel.
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.programs.outsource;
in
{
  options.programs.outsource = {
    enable = lib.mkEnableOption "Outsource a jeho nabídku vzdálených připojení";
    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ./package.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ./package.nix { }";
      description = "Balíček Outsource; umožňuje zvolit vlastní variantu klienta nebo KeePassXC.";
    };
  };
  config = lib.mkIf cfg.enable { environment.systemPackages = [ cfg.package ]; };
}
