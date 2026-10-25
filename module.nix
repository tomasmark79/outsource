# This module only adds the application; the host manages networking, libvirt, and the user's database.
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
    enable = lib.mkEnableOption "Outsource and its remote connection menu";
    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ./package.nix { };
      defaultText = lib.literalExpression "pkgs.callPackage ./package.nix { }";
      description = "Outsource package; allows a custom client or KeePassXC variant.";
    };
  };
  config = lib.mkIf cfg.enable { environment.systemPackages = [ cfg.package ]; };
}
