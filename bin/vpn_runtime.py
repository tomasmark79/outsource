"""Private VPN files exist only in the user's runtime directory."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile


class VpnError(RuntimeError):
    """Local state error; profiles owned by others are left untouched."""


def private_directory(path, *, create=True):
    if create:
        path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise VpnError("The VPN runtime directory must be owned by the user and have mode 0700.")


class VpnRuntime:
    def __init__(self, client, target):
        value = os.environ.get("XDG_RUNTIME_DIR", "")
        if not value or not Path(value).is_absolute():
            raise VpnError("VPN requires XDG_RUNTIME_DIR from a logged-in user session.")
        root = Path(value)
        private_directory(root, create=False)
        root = root / "outsource"
        private_directory(root)
        self.root = root / "vpn"
        private_directory(self.root)
        # Separators in company names and aliases must not cause key collisions.
        self.key = hashlib.sha256(json.dumps([client, target]).encode()).hexdigest()
        self.name = "outs-" + self.key
        self.path = self.root / self.key
        self.lock = None

    def __enter__(self):
        descriptor = os.open(self.root / (self.key + ".lock"),
                             os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        self.lock = os.fdopen(descriptor, "r+")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.lock.close()
            self.lock = None
            raise VpnError("Another Outsource command is currently working on this VPN profile.") from exc
        return self

    def __exit__(self, *_):
        self.lock.close()

    def read(self):
        if not self.path.exists():
            return None
        private_directory(self.path, create=False)
        state_path = self.path / "state.json"
        info = state_path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise VpnError("The VPN state file does not have private permissions.")
        try:
            state = json.loads(state_path.read_text())
        except (ValueError, UnicodeError) as exc:
            raise VpnError("VPN state is corrupt; the profile has been left unchanged.") from exc
        if (not isinstance(state, dict)
                or not isinstance(state.get("import_name"), str)
                or not re.fullmatch(re.escape(self.name) + r"-[A-Za-z0-9_-]+", state["import_name"])
                or (state.get("uuid") is not None and not re.fullmatch(
                    r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", str(state["uuid"])) )):
            raise VpnError("VPN state is invalid; the profile has been left unchanged.")
        return state

    def begin(self):
        if self.path.exists():
            raise VpnError("VPN has saved runtime state; run vpn-down first.")
        private_directory(self.path)

    def save(self, state):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.path, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(state, stream)
                stream.write("\n")
            temporary.replace(self.path / "state.json")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def cleanup(self):
        if self.path.exists():
            private_directory(self.path, create=False)
            shutil.rmtree(self.path)
