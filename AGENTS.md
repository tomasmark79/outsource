# Pravidla projektu

- Dokumentaci a nové komentáře piš česky; technická rozhraní nepřekládej.
- Skutečné profily, trezory, klíče a provozní logy patří do uživatelských XDG adresářů, nikdy do repozitáře ani Nix store.
- Testy používají dočasné adresáře a náhrady vzdálených klientů. Neotvírej skutečná připojení nebo trezor při běžné verifikaci.
- Zachovej současné ID připojení a desktopové identifikátory kvůli existujícím zástupcům. Živé párování v GNOME nenahrazují unit testy.
- Vlastní GNOME Console má konkrétní důvod popsaný v package.nix. Po aktualizaci ověř, zda lze výjimku odstranit.
- Po ověřeném dílčím kroku vytvoř lokální commit. Push, release a aktivaci systému prováděj jen na výslovný pokyn.

## Kontroly

```bash
python3 -m unittest discover -s tests -v
nix flake check --no-update-lock-file
nix build --no-update-lock-file
```
