# Změny

## 2.1.0

- Samostatný Nix flake, modul NixOS, desktopové soubory, vývojové prostředí a CI.
- Zachovaná historie původního adresáře `applications/outsource` z Nixonu.
- Správné uvozování názvů a cest v desktopových zástupcích, včetně reálné regrese Gio.
- Vadný profil neblokuje správu zdravých připojení; chybný server lze opravit v průvodci.
- Podpora IPv6 a zástupců pro správnou instalaci programu.
- Jednotné vyhodnocení běžného ukončení ručního a automatického RDP.
- Ověření UUID před exportem SSH přílohy z KeePassXC.
- Dočasné VPN certifikáty s životností podle připojení; jednoznačné profily a spolehlivé rozpoznání importovaného UUID.

Uživatelské profily a stávající desktopové identifikátory zůstávají kompatibilní.
