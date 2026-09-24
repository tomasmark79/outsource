# Outsource je součást systému; uživatelská konfigurace patří do ~/.config/outsource.
{ pkgs, ... }:
{
  home-manager.users.tomas = {
    xdg.desktopEntries = {
      outsource-connections = {
        name = "Vzdálená připojení";
        comment = "Přidat, upravit nebo odstranit zástupce RDP, SSH a virt-viewer";
        exec = "/run/current-system/sw/bin/outs manage";
        icon = "preferences-desktop-remote-desktop";
        terminal = false;
        categories = [
          "Network"
          "RemoteAccess"
        ];
      };
      outsource-new-connection = {
        name = "Přidat vzdálené připojení";
        exec = "/run/current-system/sw/bin/outs new";
        icon = "list-add";
        terminal = false;
        categories = [
          "Network"
          "RemoteAccess"
        ];
      };
    };
  };
  environment.systemPackages = [
    pkgs.nixon.outsource
  ];
}
