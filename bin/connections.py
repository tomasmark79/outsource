"""Grafický průvodce a uživatelské zástupce nezávislé na sestavení systému."""

import copy
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid


TYPES = {"rdp": "Vzdálená plocha (RDP)", "ssh": "Terminál (SSH)", "virt-viewer": "Konzole virtuálního stroje"}
ID_RE = re.compile(r"[a-f0-9]{32}")


def dialog(api, *arguments):
    # Výběr souborů má vlastní GTK tlačítka; Zenity u něj vlastní popisky odmítá.
    labels = [] if "--file-selection" in arguments else ["--ok-label=Potvrdit"]
    if not any(kind in arguments for kind in ("--info", "--error", "--file-selection")):
        labels.append("--cancel-label=Zrušit")
    result = subprocess.run(
        [api.require_program("zenity"), "--title=Vzdálená připojení", "--no-markup",
         *labels, *arguments],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if result.returncode == 1:
        raise api.Cancelled()
    if result.returncode != 0:
        raise api.OutsError("Dialog nelze otevřít. Spusťte příkaz v grafické relaci GNOME.")
    return result.stdout.removesuffix("\n")


def choose(api, text, rows):
    if not rows:
        raise api.OutsError("Seznam je prázdný. Nejdřív přidejte připojení.")
    result = dialog(api, "--list", "--width=650", "--height=430", "--text=" + text,
                    "--column=ID", "--column=Položka", "--hide-column=1", "--print-column=1",
                    "--", *[value for row in rows for value in row])
    if result not in {row[0] for row in rows}:
        raise api.Cancelled()
    return result


def entry(api, label, default="", required=True):
    while True:
        value = dialog(api, "--entry", "--width=570", "--text=" + label,
                       "--entry-text=" + str(default)).strip()
        if (value or not required) and not any(c in value for c in "\0\r\n"):
            return value
        dialog(api, "--error", "--text=Zadejte hodnotu na jednom řádku.")


def data_dir(api):
    return api.CONFIG_HOME / "outsource" / "connections"


def connection_path(api, connection_id):
    if not isinstance(connection_id, str) or not ID_RE.fullmatch(connection_id):
        raise api.OutsError("Neplatný identifikátor připojení.")
    return data_dir(api) / (connection_id + ".json")


def validate(api, connection):
    if not isinstance(connection, dict) or connection.get("version") != 1:
        raise api.OutsError("Nepodporovaný formát připojení.")
    connection_path(api, connection.get("id"))
    kind = connection.get("type")
    if kind not in TYPES:
        raise api.OutsError("Připojení musí být RDP, SSH nebo virt-viewer.")
    def text(value, label, required=True):
        if not isinstance(value, str) or (required and not value.strip()) or any(c in value for c in "\0\n\r"):
            raise api.OutsError(f"Neplatné pole: {label}.")
    text(connection.get("name"), "název")
    record = connection.get("record")
    if not isinstance(record, dict):
        raise api.OutsError("Připojení nemá nastavení.")
    if any(key.lower() in {"password", "private_key", "master_password"} for key in record):
        raise api.OutsError("Hesla a privátní klíče patří do KeePassXC, ne do připojení.")
    if kind in {"rdp", "ssh"}:
        host = record.get("host", "")
        if not isinstance(host, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.:%-]*", host):
            raise api.OutsError("Server musí být název, IP adresa nebo alias z ~/.ssh/config.")
        text(record.get("username", ""), "uživatel", required=kind == "rdp")
        port = record.get("port")
        if port is not None and (type(port) is not int or not 1 <= port <= 65535):
            raise api.OutsError("Port musí být číslo od 1 do 65535.")
    if kind == "virt-viewer":
        text(record.get("domain"), "název virtuálního stroje")
        text(record.get("connect"), "připojení libvirt")
    if kind == "rdp":
        text(record.get("domain", ""), "doména", required=False)
        if not isinstance(record.get("keepass"), dict):
            raise api.OutsError("Zadejte UUID položky KeePassXC s RDP heslem.")
        api.merge_rdp_options(["freerdp"], record.get("freerdp_args", []))
    if record.get("keepass"):
        credential = record["keepass"]
        if not isinstance(credential, dict):
            raise api.OutsError("Neplatný odkaz na KeePassXC.")
        api.normalized_uuid(credential.get("uuid", ""))
        if kind == "ssh":
            text(credential.get("attachment"), "příloha se SSH klíčem")
    return connection


def load(api, connection_id):
    connection = api.read_json(connection_path(api, connection_id))
    validate(api, connection)
    if connection["id"] != connection_id:
        raise api.OutsError("Identifikátor souboru neodpovídá připojení.")
    return connection


def desktop_path(api, connection):
    return api.applications_dir() / (api.desktop_id("local", connection["type"], connection["id"]) + ".desktop")


def desktop_contents(api, connection):
    kind = connection["type"]
    command = [str(api.launcher_executable()), "connect", connection["id"]]
    if kind != "ssh":
        command.append("--gui")
    icon = str(api.ROOT / "assets" / ("outs-" + kind + ".svg"))
    if os.environ.get("OUTSOURCE_EXECUTABLE"):
        icon = str(api.launcher_executable().parent.parent /
                   "share/icons/hicolor/scalable/apps" / ("outs-" + kind + ".svg"))
    window_class = api.desktop_id("local", kind, connection["id"])
    if kind == "ssh":
        # Vlastní identita přiřadí terminál ke konkrétnímu zástupci v GNOME.
        window_class = "org.nixon.outsource.ssh.c" + connection["id"]
        command = [str(api.launcher_executable().with_name("outs-terminal")),
                   "--gapplication-app-id=" + window_class,
                   "--title=" + connection["name"], "--", *command]
    return (
        "[Desktop Entry]\nType=Application\n"
        f"Name={api.desktop_text(connection['name'])}\n"
        f"Comment={api.desktop_text(TYPES[kind])}\n"
        f"Exec={' '.join(api.desktop_exec_argument(value) for value in command)}\n"
        f"Icon={api.desktop_text(icon)}\n"
        "Terminal=false\n"
        f"StartupWMClass={window_class}\n"
        "StartupNotify=false\nCategories=Network;RemoteAccess;\n"
        f"X-Outsource-Connection={connection['id']}\n"
    )


def atomic_write(path, contents):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".outs-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(contents)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def save(api, connection, previous=None):
    validate(api, connection)
    path = connection_path(api, connection["id"])
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (path.parent / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = api.read_json(path) if path.exists() else None
        if existing != previous:
            raise api.OutsError("Připojení mezitím změnilo jiné okno. Otevřete jej znovu.")
        target = desktop_path(api, connection)
        atomic_write(path, json.dumps(connection, ensure_ascii=False, indent=2) + "\n")
        try:
            atomic_write(target, desktop_contents(api, connection))
        except OSError:
            if previous is None:
                path.unlink()
            else:
                atomic_write(path, json.dumps(previous, ensure_ascii=False, indent=2) + "\n")
            raise
    api.log_event("uložen zástupce", id=connection["id"], protokol=connection["type"])


def select_connection(api):
    rows = []
    for path in sorted(data_dir(api).glob("*.json")):
        connection = load(api, path.stem)
        rows.append((connection["id"], f"{connection['name']} — {TYPES[connection['type']]}"))
    return load(api, choose(api, "Vyberte připojení.", rows))


def configure_keepass(api):
    database = dialog(api, "--file-selection", "--text=Vyberte databázi KeePassXC", "--file-filter=Databáze | *.kdbx")
    if not Path(database).is_file():
        raise api.OutsError("Vybraná databáze neexistuje.")
    key_file = None
    if choose(api, "Používá trezor také souborový klíč?", [("yes", "Ano, vybrat klíč"), ("no", "Ne, pouze hlavní heslo")]) == "yes":
        key_file = dialog(api, "--file-selection", "--text=Vyberte souborový klíč")
        if not Path(key_file).is_file():
            raise api.OutsError("Vybraný klíč neexistuje.")
    current = api.read_json(api.LOCAL_CONFIG) if api.LOCAL_CONFIG.exists() else {}
    current["keepass"] = {"database": database, "key_file": key_file}
    atomic_write(api.LOCAL_CONFIG, json.dumps(current, ensure_ascii=False, indent=2) + "\n")


def enter_credential(api, existing=None):
    credential = copy.deepcopy(existing) if existing else {}
    value = credential.get("uuid", "")
    while True:
        value = entry(api, "UUID položky KeePassXC\nZkopírujte ho z karty Vlastnosti dané položky.", value)
        try:
            credential["uuid"] = api.normalized_uuid(value)
            break
        except api.OutsError as exc:
            dialog(api, "--error", "--text=" + str(exc))
    # Při vytváření zástupce trezor neodemykáme ani nečteme jeho položky.
    if not api.LOCAL_CONFIG.exists():
        configure_keepass(api)
    return credential


def details_form(api, kind):
    fields = [("name", "Název zástupce")]
    if kind in {"rdp", "ssh"}:
        fields += [
            ("host", "Alias z ~/.ssh/config nebo server" if kind == "ssh" else "Adresa serveru"),
            ("username", "Uživatel (prázdné = podle SSH konfigurace)" if kind == "ssh" else "Uživatel Windows"),
            ("port", "Port (prázdné = podle SSH konfigurace)" if kind == "ssh" else "Port (prázdné = 3389)"),
        ]
        if kind == "rdp":
            fields.append(("domain", "Doména Windows (volitelné)"))
    else:
        fields += [("domain", "Název nebo UUID virtuálního stroje"),
                   ("connect", "Libvirt (prázdné = qemu:///system)")]
    separator = "\x1f"
    values = dialog(api, "--forms", "--width=650", "--text=" + TYPES[kind],
                    "--separator=" + separator,
                    *["--add-entry=" + label for _, label in fields]).split(separator)
    if len(values) != len(fields):
        raise api.OutsError("Formulář obsahuje nepovolený oddělovač.")
    return {key: value.strip() for (key, _), value in zip(fields, values)}


def edit_connection(api, previous=None):
    connection = copy.deepcopy(previous) if previous else {
        "version": 1, "id": uuid.uuid4().hex, "record": {},
        "type": choose(api, "Jaké připojení chcete vytvořit?", list(TYPES.items())),
    }
    kind = connection["type"]
    initial = details_form(api, kind) if previous is None else {}
    def ask(key, label, default="", required=True):
        if key in initial:
            value = initial.pop(key) or str(default)
            if (value or not required) and not any(c in value for c in "\0\n\r"):
                return value
        return entry(api, label, default, required)
    connection["name"] = ask("name", "Název zástupce v nabídce aplikací", connection.get("name", ""))
    record = connection["record"]
    if kind in {"rdp", "ssh"}:
        record["host"] = ask("host", "Alias z ~/.ssh/config nebo server" if kind == "ssh" else "Adresa RDP serveru", record.get("host", ""))
        username = ask("username", "Uživatel (prázdné = podle SSH konfigurace)" if kind == "ssh" else "Uživatel Windows", record.get("username", ""), required=kind == "rdp")
        if username:
            record["username"] = username
        else:
            record.pop("username", None)
        while True:
            port = ask("port", "Port (prázdné = podle SSH konfigurace)" if kind == "ssh" else "RDP port", record.get("port", "" if kind == "ssh" else 3389), required=kind == "rdp")
            if not port:
                record.pop("port", None)
                break
            if port.isdecimal() and 1 <= int(port) <= 65535:
                record["port"] = int(port)
                break
            dialog(api, "--error", "--text=Port musí být číslo od 1 do 65535.")
    if kind == "rdp":
        record["domain"] = ask("domain", "Doména Windows (volitelné)", record.get("domain", ""), required=False)
        record["keepass"] = enter_credential(api, record.get("keepass"))
        options = dialog(api, "--list", "--checklist", "--text=Možnosti RDP", "--column=Zapnout", "--column=ID", "--column=Volba",
                         "--hide-column=2", "--print-column=2", "--separator=,", "--",
                         str(record.get("clipboard", True)).upper(), "clipboard", "Sdílet schránku",
                         str(record.get("audio", "local") == "local").upper(), "audio", "Přehrávat zvuk na notebooku",
                         str(record.get("multimon", False)).upper(), "multimon", "Použít více monitorů")
        flags = options.split(",")
        record.update(clipboard="clipboard" in flags, audio="local" if "audio" in flags else "off", multimon="multimon" in flags)
    elif kind == "ssh":
        mode = choose(api, "Přihlášení k SSH", [("config", "Použít ~/.ssh/config a SSH agenta"), ("keepass", "Klíč z přílohy KeePassXC")])
        if mode == "config":
            record.pop("keepass", None)
        else:
            credential = enter_credential(api, record.get("keepass"))
            credential["attachment"] = entry(api, "Název přílohy se SSH klíčem", credential.get("attachment", ""))
            record["keepass"] = credential
    else:
        record["domain"] = ask("domain", "Název nebo UUID virtuálního stroje", record.get("domain", ""))
        record["connect"] = ask("connect", "Připojení libvirt", record.get("connect", "qemu:///system"))
    record["id"] = connection["id"]
    validate(api, connection)
    dialog(api, "--question", "--text=" + f"Uložit zástupce „{connection['name']}“ do nabídky aplikací?")
    save(api, connection, previous)
    dialog(api, "--info", "--text=Zástupce je připravený v nabídce aplikací. Můžete ho připnout do doku.")


def remove_connection(api, connection):
    path = connection_path(api, connection["id"])
    with (path.parent / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if load(api, connection["id"]) != connection:
            raise api.OutsError("Připojení mezitím změnilo jiné okno. Otevřete jej znovu.")
        desktop_path(api, connection).unlink(missing_ok=True)
        path.unlink()
    api.log_event("odstraněn zástupce", id=connection["id"])


def connect(api, connection_id):
    connection = load(api, connection_id)
    record = copy.deepcopy(connection["record"])
    record["id"] = connection_id
    kind = connection["type"]
    config = {"company": {"id": "local"}, kind: [record]}
    args = [connection_id]
    # Grafický zástupce počká na klienta a může tak zobrazit i chybu připojení.
    if kind == "rdp" and api.GUI_MODE:
        args.append("--debug")
    result = api.dispatch_action("local", config, kind, args)
    if result and api.GUI_MODE:
        raise api.OutsError(f"Připojení „{connection['name']}“ skončilo s chybou {result}. Ověřte adresu, přihlášení a dostupnost sítě.")
    return result


def main(api, arguments):
    action = arguments[0]
    if action == "connect":
        if len(arguments) not in (2, 3) or (len(arguments) == 3 and arguments[2] != "--gui"):
            raise api.OutsError("Použití: outs connect <id> [--gui]")
        return connect(api, arguments[1])
    if len(arguments) != 1:
        raise api.OutsError("Tento příkaz nepřijímá další argumenty.")
    if action == "manage":
        action = choose(api, "Vzdálená připojení", [
            ("new", "Přidat připojení"), ("edit", "Upravit připojení"),
            ("remove", "Odstranit zástupce"),
            ("keepass", "Nastavit databázi KeePassXC"),
        ])
    if action == "new":
        edit_connection(api)
    elif action == "edit":
        edit_connection(api, select_connection(api))
    elif action == "remove":
        connection = select_connection(api)
        dialog(api, "--question", "--text=" + f"Odstranit zástupce „{connection['name']}“? Položka v KeePassXC zůstane zachovaná.")
        remove_connection(api, connection)
    elif action == "keepass":
        configure_keepass(api)
    return 0
