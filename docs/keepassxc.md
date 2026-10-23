# KeePassXC

KeePassXC je jediný zdroj pravdy pro hesla, webové přístupy, API tokeny,
privátní klíče, recovery kódy a citlivé poznámky. Sdílená konfigurace
obsahuje pouze UUID položky, nikdy její titulek, skupinu ani heslo.

SSH standardně používá `~/.ssh/config`, systémové nastavení OpenSSH a SSH agenta.
Uživatele ani port nepřepisuje, pokud je nezadáš. Klíče uložené v KeePassXC může
agentovi předat přímo KeePassXC; zástupce pak trezor sám neodemyká.

Volitelně lze vybrat klíč uložený jako příloha položky. V tomto režimu launcher
pro každou relaci exportuje klíč do náhodného dočasného souboru s právy `0600`
a po skončení SSH jej odstraní. Před exportem ověří také UUID položky vrácené
pod danou cestou: dvě položky stejného názvu ve stejné skupině nesmějí způsobit
načtení jiného klíče. Nemění `~/.ssh/config` ani obsah agenta.

Při `SIGTERM` a `SIGHUP` launcher provede běžný úklid SSH klíče a rozpracované
VPN; při `SIGKILL` ani pádu systému tento úklid zaručit nelze.

Webové záznamy obsahují také pouze UUID. Launcher z položky načte pole
`URL` a `UserName`, URL otevře ve výchozím prohlížeči a vlastní přihlášení
ponechá rozšíření KeePassXC-Browser. Heslo se proto nevkládá do URL,
argumentů prohlížeče ani schránky.

OpenVPN profil lze uložit jako přílohu položky. `vpn-up` ho podle UUID
exportuje do soukromého adresáře pod `$XDG_RUNTIME_DIR/outsource/vpn`,
importuje do NetworkManageru s `--temporary` a po dokončení aktivace původní
soubor odstraní. Také následné úpravy profilu používají `--temporary`, aby jej
neuložily na disk. Přihlášená relace musí poskytovat vlastní `XDG_RUNTIME_DIR`
s oprávněním `0700`; bez něj se VPN nespustí.

OpenVPN plugin při importu vypisuje vložené certifikáty a klíče do samostatných
souborů. Outsource proto nastaví `NM_CERT_PATH` na tentýž soukromý runtime
adresář. Tyto soubory zůstanou dostupné po dobu VPN relace, včetně případného
opětovného připojení. Samotné `--temporary` jejich životnost neřeší.

`vpn-down` smaže přes uložené UUID profil NetworkManageru a poté jeho runtime
adresář s certifikáty. Ukončení příkazu `vpn-up` spojení neodpojuje. Když import
nebo aktivace selže či je přerušíš, launcher profil a soubory uklidí. Pokud
NetworkManager nelze kontaktovat nebo smazání selže, zachová lokální stav
pro opakování `vpn-down`; odstranění certifikátů by mohlo poškodit stále běžící
VPN. Po restartu se runtime adresář vyprázdní.

Interní název vzniká hashem dvojice firma a alias VPN. Uložené UUID identifikuje
konkrétní profil i při změně názvu a zámek brání souběžným operacím nad stejnou
dvojicí. Při opakovaném `vpn-up` nejprve dokonči `vpn-down`.

Pokud NetworkManager stále zná profil, ale runtime stav už zanikl například
odhlášením, Outsource odmítne profil převzít i oznámit jeho úspěšné vypnutí.
Chyba uvede konkrétní UUID pro ruční odpojení a odstranění v NetworkManageru.
Stejně zachází s existujícím profilem se starším názvem `outs-firma-alias`.

Standardní pole `UserName` stejné položky se nastaví jako OpenVPN username
a pole `Password` se při aktivaci předá přes `nmcli passwd-file`. Soubor
má práva `0600`, po dokončení aktivace se odstraní a heslo se neobjeví v
argumentech procesu ani v trvalém profilu.

Runtime `state.json` má také práva `0600` a obsahuje pouze UUID a název
importu pro zotavení po přerušení. Heslo ani obsah příloh se do něj neukládají.

## Automatické RDP heslo

`outs` odemyká jednu KDBX databázi přes `keepassxc-cli`. Umístění
databáze a volitelného souborového klíče je strojově specifické, proto je v lokálním
souboru `~/.config/outsource/config.local.json` mimo repozitář:

```json
{
  "keepass": {
    "database": "/cesta/k/trezoru.kdbx",
    "key_file": "/cesta/k/souborovemu-klici"
  }
}
```

Pokud souborový klíč nepoužíváš, pole `key_file` vynech nebo nastav na `null`.
Nastavení lze vytvořit graficky příkazem `outs keepass`.

Každý RDP záznam odkazuje na položku takto:

```json
"keepass": { "uuid": "faa054617a774d8bad6a27cb673d9141" }
```

Launcher nejprve použije hledání `uuid:<UUID>` a získanou cestu předá
dalšímu příkazu KeePassXC. Titulek i umístění položky lze proto libovolně
měnit bez úpravy konfigurace. UUID lze zkopírovat z karty **Vlastnosti**.

Nový RDP zástupce otevře grafický dialog pro hlavní heslo trezoru. Souborový klíč
případně doplní launcher. UUID zadáš do průvodce ručně; při úpravě je
předvyplněné. Průvodce kontroluje formát UUID, ale trezor neodemyká ani nečte
seznam položek. Existenci položky ověří až při připojení. Odemčené okno KeePassXC nenahrazuje přihlášení
do `keepassxc-cli`, proto je hlavní heslo při připojení potřeba znovu. Integrace nepoužívá Secret Service
a nijak nemění ani nevypíná GNOME Keyring.

Pro diagnostiku lze použít `outs example rdp workstation --debug`; FreeRDP
pak zůstane v popředí a jeho výstup je živě vidět v terminálu. Pro nouzové
ruční přihlášení slouží `--manual`; oba přepínače lze kombinovat. Provozní log obsahuje průběh a návratové kódy; úplný výstup klienta se
neukládá. Rozpoznané diagnostické chyby se ukládají u grafických zástupců
a v režimu `--debug`.

Celý seznam FreeRDP parametrů včetně hesla se předá přes
`/args-from:stdin`. V procesním seznamu je vidět pouze tento přepínač;
heslo se nezapisuje do Gitu, argumentů procesu, proměnných prostředí ani
dočasného souboru. Hlavní heslo launcher převezme jednou a dvěma krátce
běžícím procesům `keepassxc-cli` ho předá pouze přes standardní vstup.
Neobjeví se v argumentech procesu ani v proměnných prostředí.

Původní terminálové příkazy bez `--debug` po předání parametrů spustí FreeRDP
na pozadí. Nový grafický zástupce terminál neotevírá a pomocník čeká na konec
klienta, aby mohl při neúspěšném připojení zobrazit chybové okno.
