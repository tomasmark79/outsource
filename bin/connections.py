"""Graphical wizard and user launchers independent of system rebuilds."""

import copy
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid


TYPES = {"rdp": "Remote Desktop (RDP)", "ssh": "Terminal (SSH)", "virt-viewer": "Virtual Machine Console"}
ID_RE = re.compile(r"[a-f0-9]{32}")


def dialog(api, *arguments):
    # File selection uses GTK buttons; Zenity rejects custom labels for it.
    labels = [] if "--file-selection" in arguments else ["--ok-label=Confirm"]
    if not any(kind in arguments for kind in ("--info", "--error", "--warning", "--file-selection")):
        labels.append("--cancel-label=Cancel")
    result = subprocess.run(
        [api.require_program("zenity"), "--title=Remote Connections", "--no-markup",
         *labels, *arguments],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if result.returncode == 1:
        raise api.Cancelled()
    if result.returncode != 0:
        raise api.OutsError("Cannot open the dialog. Run this command in a graphical GNOME session.")
    return result.stdout.removesuffix("\n")


def choose(api, text, rows):
    if not rows:
        raise api.OutsError("The list is empty. Add a connection first.")
    result = dialog(api, "--list", "--width=650", "--height=430", "--text=" + text,
                    "--column=ID", "--column=Item", "--hide-column=1", "--print-column=1",
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
        dialog(api, "--error", "--text=Enter a value on a single line.")


def data_dir(api):
    return api.CONFIG_HOME / "outsource" / "connections"


def connection_path(api, connection_id):
    if not isinstance(connection_id, str) or not ID_RE.fullmatch(connection_id):
        raise api.OutsError("Invalid connection ID.")
    return data_dir(api) / (connection_id + ".json")


def validate_host(api, host):
    if isinstance(host, str) and re.fullmatch(r"[A-Za-z0-9_.:%-]+", host):
        try:
            ipaddress.ip_address(host)
            return
        except ValueError:
            # Also allow OpenSSH aliases containing underscores or percent signs.
            if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.%-]*", host):
                return
    raise api.OutsError("The server must be a hostname, IP address, or alias from ~/.ssh/config.")


def validate(api, connection):
    if not isinstance(connection, dict) or connection.get("version") != 1:
        raise api.OutsError("Unsupported connection format.")
    connection_path(api, connection.get("id"))
    kind = connection.get("type")
    if not isinstance(kind, str) or kind not in TYPES:
        raise api.OutsError("The connection type must be RDP, SSH, or virt-viewer.")
    def text(value, label, required=True):
        if not isinstance(value, str) or (required and not value.strip()) or any(c in value for c in "\0\n\r"):
            raise api.OutsError(f"Invalid field: {label}.")
    text(connection.get("name"), "name")
    record = connection.get("record")
    if not isinstance(record, dict):
        raise api.OutsError("The connection has no settings.")
    if any(key.lower() in {"password", "private_key", "master_password"} for key in record):
        raise api.OutsError("Store passwords and private keys in KeePassXC, not in connection files.")
    if kind in {"rdp", "ssh"}:
        validate_host(api, record.get("host", ""))
        text(record.get("username", ""), "username", required=kind == "rdp")
        port = record.get("port")
        if port is not None and (type(port) is not int or not 1 <= port <= 65535):
            raise api.OutsError("The port must be a number from 1 to 65535.")
    if kind == "virt-viewer":
        text(record.get("domain"), "virtual machine name")
        text(record.get("connect"), "libvirt connection")
    if kind == "rdp":
        text(record.get("domain", ""), "domain", required=False)
        api.rdp_remoteapp(record)
        if not isinstance(record.get("keepass"), dict):
            raise api.OutsError("Enter the UUID of the KeePassXC entry containing the RDP password.")
        api.merge_rdp_options(["freerdp"], record.get("freerdp_args", []))
    if kind == "rdp" or record.get("keepass"):
        credential = record["keepass"]
        if not isinstance(credential, dict):
            raise api.OutsError("Invalid KeePassXC reference.")
        api.normalized_uuid(credential.get("uuid", ""))
        if kind == "ssh":
            text(credential.get("attachment"), "SSH key attachment")
    return connection


def load(api, connection_id):
    connection = api.read_json(connection_path(api, connection_id))
    validate(api, connection)
    if connection["id"] != connection_id:
        raise api.OutsError("The file ID does not match the connection ID.")
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
        # A custom identity associates the terminal with its launcher in GNOME.
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
            raise api.OutsError("Another window has changed this connection. Open it again.")
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
    api.log_event("launcher saved", id=connection["id"], protocol=connection["type"])


def select_connection(api):
    rows = []
    invalid = []
    for path in sorted(data_dir(api).glob("*.json")):
        try:
            connection = load(api, path.stem)
        except (api.OutsError, OSError, UnicodeError):
            invalid.append(str(path))
            continue
        rows.append((connection["id"], f"{connection['name']} — {TYPES[connection['type']]}"))
    if invalid:
        message = ("The following connections could not be loaded. Their files were left unchanged; "
                   "correct them or move them out of the connections directory:\n\n" + "\n".join(invalid))
        if not rows:
            raise api.OutsError(message)
        dialog(api, "--warning", "--text=" + message)
    return load(api, choose(api, "Select a connection.", rows))


def configure_keepass(api):
    database = dialog(api, "--file-selection", "--text=Select a KeePassXC database", "--file-filter=Database | *.kdbx")
    if not Path(database).is_file():
        raise api.OutsError("The selected database does not exist.")
    key_file = None
    if choose(api, "Does the database also use a key file?", [("yes", "Yes, select a key file"), ("no", "No, master password only")]) == "yes":
        key_file = dialog(api, "--file-selection", "--text=Select a key file")
        if not Path(key_file).is_file():
            raise api.OutsError("The selected key file does not exist.")
    current = api.read_json(api.LOCAL_CONFIG) if api.LOCAL_CONFIG.exists() else {}
    current["keepass"] = {"database": database, "key_file": key_file}
    atomic_write(api.LOCAL_CONFIG, json.dumps(current, ensure_ascii=False, indent=2) + "\n")


def enter_credential(api, existing=None):
    credential = copy.deepcopy(existing) if existing else {}
    value = credential.get("uuid", "")
    while True:
        value = entry(api, "KeePassXC entry UUID\nCopy it from the entry's Properties tab.", value)
        try:
            credential["uuid"] = api.normalized_uuid(value)
            break
        except api.OutsError as exc:
            dialog(api, "--error", "--text=" + str(exc))
    # Creating a launcher does not unlock the database or read its entries.
    if not api.LOCAL_CONFIG.exists():
        configure_keepass(api)
    return credential


def details_form(api, kind):
    fields = [("name", "Launcher name")]
    if kind in {"rdp", "ssh"}:
        fields += [
            ("host", "Alias from ~/.ssh/config or server" if kind == "ssh" else "Server address"),
            ("username", "Username (blank = SSH configuration)" if kind == "ssh" else "Windows username"),
            ("port", "Port (blank = SSH configuration)" if kind == "ssh" else "Port (blank = 3389)"),
        ]
        if kind == "rdp":
            fields.append(("domain", "Windows domain (optional)"))
            fields.append(("remoteapp", "RemoteApp application (optional, e.g. ||notepad)"))
    else:
        fields += [("domain", "Virtual machine name or UUID"),
                   ("connect", "Libvirt (blank = qemu:///system)")]
    separator = "\x1f"
    values = dialog(api, "--forms", "--width=650", "--text=" + TYPES[kind],
                    "--separator=" + separator,
                    *["--add-entry=" + label for _, label in fields]).split(separator)
    if len(values) != len(fields):
        raise api.OutsError("The form contains an invalid separator.")
    return {key: value.strip() for (key, _), value in zip(fields, values)}


def edit_connection(api, previous=None):
    connection = copy.deepcopy(previous) if previous else {
        "version": 1, "id": uuid.uuid4().hex, "record": {},
        "type": choose(api, "What type of connection would you like to create?", list(TYPES.items())),
    }
    kind = connection["type"]
    initial = details_form(api, kind) if previous is None else {}
    def ask(key, label, default="", required=True):
        if key in initial:
            value = initial.pop(key) or str(default)
            if (value or not required) and not any(c in value for c in "\0\n\r"):
                return value
        return entry(api, label, default, required)
    connection["name"] = ask("name", "Launcher name in the application menu", connection.get("name", ""))
    record = connection["record"]
    if kind in {"rdp", "ssh"}:
        host_label = "Alias from ~/.ssh/config or server" if kind == "ssh" else "RDP server address"
        host = ask("host", host_label, record.get("host", ""))
        while True:
            try:
                validate_host(api, host)
                break
            except api.OutsError as exc:
                dialog(api, "--error", "--text=" + str(exc))
                host = entry(api, host_label, host)
        record["host"] = host
        username = ask("username", "Username (blank = SSH configuration)" if kind == "ssh" else "Windows username", record.get("username", ""), required=kind == "rdp")
        if username:
            record["username"] = username
        else:
            record.pop("username", None)
        while True:
            port = ask("port", "Port (blank = SSH configuration)" if kind == "ssh" else "RDP port", record.get("port", "" if kind == "ssh" else 3389), required=kind == "rdp")
            if not port:
                record.pop("port", None)
                break
            if port.isdecimal() and 1 <= int(port) <= 65535:
                record["port"] = int(port)
                break
            dialog(api, "--error", "--text=The port must be a number from 1 to 65535.")
    if kind == "rdp":
        record["domain"] = ask("domain", "Windows domain (optional)", record.get("domain", ""), required=False)
        remoteapp = ask("remoteapp", "RemoteApp application (blank = full desktop)", record.get("remoteapp", ""), required=False)
        if remoteapp:
            record["remoteapp"] = remoteapp
        else:
            record.pop("remoteapp", None)
        record["keepass"] = enter_credential(api, record.get("keepass"))
        options = dialog(api, "--list", "--checklist", "--text=RDP options", "--column=Enable", "--column=ID", "--column=Option",
                         "--hide-column=2", "--print-column=2", "--separator=,", "--",
                         str(record.get("clipboard", True)).upper(), "clipboard", "Share clipboard",
                         str(record.get("audio", "local") == "local").upper(), "audio", "Play audio on this computer",
                         str(record.get("multimon", False)).upper(), "multimon", "Use multiple monitors")
        flags = options.split(",")
        record.update(clipboard="clipboard" in flags, audio="local" if "audio" in flags else "off", multimon="multimon" in flags)
    elif kind == "ssh":
        mode = choose(api, "SSH authentication", [("config", "Use ~/.ssh/config and the SSH agent"), ("keepass", "Key from a KeePassXC attachment")])
        if mode == "config":
            record.pop("keepass", None)
        else:
            credential = enter_credential(api, record.get("keepass"))
            credential["attachment"] = entry(api, "SSH key attachment name", credential.get("attachment", ""))
            record["keepass"] = credential
    else:
        record["domain"] = ask("domain", "Virtual machine name or UUID", record.get("domain", ""))
        record["connect"] = ask("connect", "Libvirt connection", record.get("connect", "qemu:///system"))
    record["id"] = connection["id"]
    validate(api, connection)
    dialog(api, "--question", "--text=" + f"Save the launcher “{connection['name']}” to the application menu?")
    save(api, connection, previous)
    dialog(api, "--info", "--text=The launcher is available in the application menu. You can pin it to the dock.")


def remove_connection(api, connection):
    path = connection_path(api, connection["id"])
    with (path.parent / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if load(api, connection["id"]) != connection:
            raise api.OutsError("Another window has changed this connection. Open it again.")
        desktop_path(api, connection).unlink(missing_ok=True)
        path.unlink()
    api.log_event("launcher removed", id=connection["id"])


def connect(api, connection_id):
    connection = load(api, connection_id)
    record = copy.deepcopy(connection["record"])
    record["id"] = connection_id
    kind = connection["type"]
    config = {"company": {"id": "local"}, kind: [record]}
    args = [connection_id]
    # Graphical launchers wait for the client so connection errors can be displayed.
    if kind == "rdp" and api.GUI_MODE:
        args.append("--debug")
    result = api.dispatch_action("local", config, kind, args)
    if result and api.GUI_MODE:
        raise api.OutsError(f"Connection “{connection['name']}” exited with error {result}. Check the address, credentials, and network connectivity.")
    return result


def main(api, arguments):
    action = arguments[0]
    if action == "connect":
        if len(arguments) not in (2, 3) or (len(arguments) == 3 and arguments[2] != "--gui"):
            raise api.OutsError("Usage: outs connect <id> [--gui]")
        return connect(api, arguments[1])
    if len(arguments) != 1:
        raise api.OutsError("This command does not accept additional arguments.")
    if action == "manage":
        action = choose(api, "Remote Connections", [
            ("new", "Add connection"), ("edit", "Edit connection"),
            ("remove", "Remove launcher"),
            ("keepass", "Configure KeePassXC database"),
        ])
    if action == "new":
        edit_connection(api)
    elif action == "edit":
        edit_connection(api, select_connection(api))
    elif action == "remove":
        connection = select_connection(api)
        dialog(api, "--question", "--text=" + f"Remove the launcher “{connection['name']}”? The KeePassXC entry will be preserved.")
        remove_connection(api, connection)
    elif action == "keepass":
        configure_keepass(api)
    return 0
