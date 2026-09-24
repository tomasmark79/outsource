# KeePassXC

KeePassXC je jediný zdroj pravdy pro hesla, webové přístupy, API tokeny,
privátní klíče, recovery kódy a citlivé poznámky. Sdílená konfigurace
obsahuje pouze UUID položky, nikdy její titulek, skupinu ani heslo.

SSH standardně používá `~/.ssh/config`, systémové nastavení OpenSSH a SSH agenta.
Uživatele ani port nepřepisuje, pokud je nezadáš. Klíče uložené v KeePassXC může
agentovi předat přímo KeePassXC; zástupce pak trezor sám neodemyká.

Volitelně lze vybrat klíč uložený jako příloha položky. V tomto režimu launcher
pro každou relaci exportuje klíč do náhodného dočasného souboru s právy `0600`
a po skončení SSH jej odstraní. Nemění `~/.ssh/config` ani obsah agenta.

Webové záznamy obsahují také pouze UUID. Launcher z položky načte pole
`URL` a `UserName`, URL otevře ve výchozím prohlížeči a vlastní přihlášení
ponechá rozšíření KeePassXC-Browser. Heslo se proto nevkládá do URL,
argumentů prohlížeče ani schránky.

OpenVPN profil lze uložit jako přílohu položky. `vpn-up` ho podle UUID
exportuje do náhodného souboru `0600`, importuje do NetworkManageru s
`--temporary` a soubor ihned odstraní. `vpn-down` odstraní také dočasný
profil NetworkManageru. Název obsahuje firmu i alias VPN, takže se profily
různých firem názvem nepřepisují.

Standardní pole `UserName` stejné položky se nastaví jako OpenVPN username
a pole `Password` se při aktivaci předá přes `nmcli passwd-file`. Soubor
má práva `0600`, po dokončení aktivace se odstraní a heslo se neobjeví v
argumentech procesu ani v trvalém profilu.

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

Pro diagnostiku lze použít `outs dotname rdp musicbox --debug`; FreeRDP
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
