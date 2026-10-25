"""Argument completion without launching clients, dialogs, or activity logging."""

import re


COMMANDS = ("manage", "new", "connect", "keepass", "ls", "desktop", "help", "--help")
ACTIONS = ("show", "ssh", "rdp", "virt-viewer", "web", "vpn", "vpn-up", "vpn-down")
DESKTOP_ACTIONS = ("ssh", "rdp", "virt-viewer", "web", "vpn-up", "vpn-down")


def connection_descriptions(api, prefix):
    """Names are only displayed; the original ID is inserted into the command line."""
    directory = api.CONFIG_HOME / "outsource" / "connections"
    result = []
    for path in sorted(directory.glob("*.json")):
        if not api.UUID_RE.fullmatch(path.stem) or not path.stem.startswith(prefix):
            continue
        try:
            name = api.read_json(path).get("name", "")
            if not isinstance(name, str):
                name = ""
            # Control characters from configuration must not affect the terminal or output format.
            name = " ".join("".join(c for c in name if c.isprintable() or c.isspace()).split())
            result.append((path.stem, name))
        except (api.OutsError, OSError, UnicodeError):
            continue
    return result


def candidates(api, words):
    # The last word is the prefix being completed, including an empty string.
    words = words or [""]
    previous, prefix = words[:-1], words[-1]

    def matching(values):
        return sorted({value for value in values
                       if isinstance(value, str)
                       and re.fullmatch(r"[A-Za-z0-9._-]+", value)
                       and value.startswith(prefix)})

    if previous and previous[0] == "connect":
        if len(previous) == 1:
            directory = api.CONFIG_HOME / "outsource" / "connections"
            return matching(path.stem for path in directory.glob("*.json")
                            if api.UUID_RE.fullmatch(path.stem) and path.is_file())
        if len(previous) == 2:
            return matching(["--gui"])
        return []
    if previous and previous[0] in COMMANDS and previous[0] != "desktop":
        return []

    profiles = []
    for path in sorted(api.CLIENTS_DIR.glob("*/config.json")):
        try:
            config = api.read_json(path)
            company = api.company_data(config)
            aliases = company.get("aliases", [])
            names = [company["id"], *(aliases if isinstance(aliases, list) else [])]
            profiles.append((config, [name for name in names
                                      if isinstance(name, str) and api.CLIENT_RE.fullmatch(name)]))
        except (api.OutsError, OSError, UnicodeError):
            # A broken profile or one being rewritten must not block other suggestions.
            continue

    desktop = bool(previous and previous[0] == "desktop")
    args = previous[1:] if desktop else previous
    if not args:
        names = [name for _, names in profiles for name in names]
        return matching(names if desktop else [*COMMANDS, *names])
    matches = [config for config, names in profiles if args[0] in names]
    if len(matches) != 1:
        return []
    def available(action):
        if action == "show":
            return True
        section = "vpn" if action in {"vpn-up", "vpn-down"} else action
        records = matches[0].get(section, [])
        return isinstance(records, list) and any(
            isinstance(record, dict) and isinstance(record.get("id"), str)
            and api.TARGET_RE.fullmatch(record["id"]) for record in records
        )
    if len(args) == 1:
        return matching(action for action in (DESKTOP_ACTIONS if desktop else ACTIONS)
                        if available(action))
    action = args[1]
    if action not in (DESKTOP_ACTIONS if desktop else ACTIONS):
        return []
    if len(args) == 2 and action not in {"show", "vpn"}:
        section = "vpn" if action in {"vpn-up", "vpn-down"} else action
        records = matches[0].get(section, [])
        if not isinstance(records, list):
            return []
        return matching(record.get("id") for record in records if isinstance(record, dict))
    if desktop:
        return matching(["--name"]) if len(args) == 3 else []
    if action == "rdp" and len(args) >= 3 and "--" not in args[3:]:
        return matching(flag for flag in ("--manual", "--debug", "--") if flag not in args[3:])
    return []
