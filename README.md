# Vzdálená připojení

Jednoduchý průvodce pro zástupce RDP, SSH a virt-viewer v nabídce GNOME.
Nix instaluje program a potřebné klienty. Připojení si pak přidáváš a upravuješ
za běhu, bez úprav Nixu, JSON souborů nebo nového sestavení systému.

## Přidání připojení

V nabídce aplikací otevři **Přidat vzdálené připojení**, případně spusť:

```bash
outs new
```

Vyber typ připojení, zadej název zástupce a jeho parametry. Nakonec potvrď uložení.
Zástupce se objeví v nabídce aplikací a můžeš ho připnout do doku.
Zrušení průvodce nevytvoří rozpracované připojení.

- **RDP:** adresa, uživatel, port a případně doména Windows. Zadáš UUID položky
  s heslem v KeePassXC a zapneš požadované sdílení schránky, zvuk nebo více monitorů.
  Při připojení zadáš hlavní heslo trezoru do grafického dialogu.
  FreeRDP běží bez pomocného terminálu. Zavření okna křížkem nebo odhlášení
  nevyvolá další dialog; skutečná chyba připojení zobrazí zprávu s cestou k logu.
- **SSH:** zadej alias z `~/.ssh/config` nebo adresu serveru. Uživatele a port
  můžeš ponechat prázdné; použije se nastavení OpenSSH. Platí také systémová
  konfigurace SSH, `ProxyJump`, klíče a SSH agent. Připojení se otevře v terminálu.
  Volitelně lze místo toho zadat UUID položky a název přílohy s klíčem v KeePassXC.
- **Virt-viewer:** název nebo UUID stroje a připojení libvirt, například
  `qemu:///system`. Otevře se přímo grafické okno bez terminálu.

RDP a virt-viewer používají vlastní identitu okna odpovídající zástupci,
aby GNOME mohlo přiřadit spuštěné okno k jeho ikoně.

## Úpravy a odstranění

Otevři **Vzdálená připojení** nebo spusť:

```bash
outs manage
```

Správce nabízí přidání, úpravu a odstranění zástupce a nastavení trezoru.
Úpravy platí pro další spuštění připojení. Odstranění smaže zástupce a jeho místní
nastavení; nemění server ani položku v KeePassXC.

## KeePassXC

U připojení zadáš UUID položky s heslem. Zkopíruješ ho v KeePassXC z karty
**Vlastnosti** dané položky. Lze vložit zápis s pomlčkami a složenými závorkami
nebo samotných 32 hexadecimálních znaků. Při úpravě připojení je současné UUID
předvyplněné. Ukládá se do `record.keepass.uuid` v souboru připojení.

Průvodce při vytváření zástupce trezor neodemyká a nečte seznam položek.
Pokud ještě není nastavené umístění databáze, požádá o soubor `.kdbx` a případně
souborový klíč. Heslo načte podle uloženého UUID až při připojení. Při vytváření
kontroluje pouze formát UUID; existenci položky ověří až při připojení.
Přejmenování nebo přesun položky uvnitř trezoru odkaz nezmění.

Nastavení databáze lze změnit ve správci nebo příkazem:

```bash
outs keepass
```

Průvodce používá `keepassxc-cli`: i když máš trezor otevřený v aplikaci KeePassXC,
požádá při čtení znovu o hlavní heslo. Podporuje hlavní heslo a volitelný souborový
klíč. Hesla ani privátní klíče neukládá do zástupců nebo Nix store.
Podrobnosti najdeš v [návodu ke KeePassXC](docs/keepassxc.md).

SSH ve výchozím režimu trezor neotvírá. Pokud máš klíče v KeePassXC, můžeš využít
jeho integraci se SSH agentem a v průvodci ponechat systémové přihlášení.

## Kde jsou data

- `~/.config/outsource/connections/`: připojení vytvořená průvodcem, po jednom souboru.
- `~/.config/outsource/config.local.json`: cesta k databázi a volitelnému klíči.
- `~/.local/share/applications/outs-local-*.desktop`: vygenerované zástupce.

Respektují se také `XDG_CONFIG_HOME`, `XDG_DATA_HOME` a pro nastavení trezoru
`OUTSOURCE_LOCAL_CONFIG`. Soubory připojení a nastavení trezoru mají práva `0600`.
Program nečte konfiguraci z adresáře se zdrojovým kódem ani z Nix store.
Pro zálohu vlastních připojení zahrň adresář `~/.config/outsource`.
Databázi KeePassXC a souborový klíč zálohuj podle jejich skutečného umístění.

## Provozní logy

Každé spuštění připojení nebo průvodce vytvoří vlastní soubor v
`~/.local/share/logs/outsource/`. Při nastaveném `XDG_DATA_HOME` se použije
`$XDG_DATA_HOME/logs/outsource/`. Názvy souborů obsahují čas v UTC a číslo procesu.
Soubory mají práva `0600`, nově vytvořený adresář `0700`.

Log obsahuje čas, druh akce, ID připojení, průběh práce s KeePassXC a návratové
kódy. U grafického RDP a virt-viewer zachytí také rozpoznané diagnostické chyby.
U terminálového RDP je tato diagnostika dostupná s `--debug`.
Chybové okno nebo terminál uvede cestu k příslušnému logu.

Neukládají se hesla, UUID položek trezoru, privátní klíče, argumenty příkazů,
obsah vzdáleného terminálu ani úplný výstup klientů. Z diagnostiky se zapisují
jen známé chybové kódy a obecné příčiny. U SSH se zaznamenává spuštění a návratový
kód; podrobná chyba zůstává v jeho terminálu.

Při spuštění se uklízejí logy starší než 30 dní a ponechává se nejvýše 100 souborů.
Právě otevřené logy se nemažou, takže při mnoha současných relacích může být souborů
více. Jeden log má limit přibližně 2 MiB. Původní příkazy spouštěné na pozadí
zaznamenají předání klienta a jeho PID, nikoli pozdější konec relace.

Nejnovější logy zobrazíš například takto:

```bash
ls -lt ~/.local/share/logs/outsource/
```

## Spuštění z terminálu

Připojení lze spustit i jako `outs connect <id>`; ID je název jeho souboru
bez `.json`. Varianta `outs connect <id> --gui` používá grafické zadání hesla
a oznámení chyb. Pro SSH používej zástupce s terminálem.

Původní firemní příkazy pro web, VPN a další přístupy jsou stále dostupné.
Jejich volitelné profily se načítají z `~/.config/outsource/clients/<firma>/config.json`
(nebo z `OUTSOURCE_CLIENTS_DIR`). Žádné firemní profily nejsou součástí projektu.

## Vývoj a ověření

Z kořene nixonu:

```bash
python3 -m unittest discover -s applications/outsource/tests
nix build path:.#outsource
```

Balíček definuje `applications/outsource/package.nix`; systémové zapojení a položky
průvodce v nabídce GNOME jsou v `applications/outsource/default.nix`.
Nová verze programu se systémově zpřístupní po obvyklém sestavení a aktivaci NixOS.
Další přidávání připojení už aktivaci nepotřebuje.
