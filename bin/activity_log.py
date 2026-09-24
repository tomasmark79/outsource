"""Omezené provozní záznamy bez argumentů příkazů a obsahu vzdálené relace."""

from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import time


MAX_FILES = 100
MAX_AGE = 30 * 24 * 60 * 60
MAX_BYTES = 2 * 1024 * 1024
# Ukládáme pouze známé kódy, nikdy celý výstup klienta.
ERROR_CODES = {
    'ERRCONNECT_CONNECT_FAILED', 'ERRCONNECT_DNS_NAME_NOT_FOUND',
    'ERRCONNECT_DNS_ERROR', 'ERRCONNECT_CONNECT_TRANSPORT_FAILED',
    'ERRCONNECT_TLS_CONNECT_FAILED', 'ERRCONNECT_AUTHENTICATION_FAILED',
    'ERRCONNECT_LOGON_FAILURE', 'ERRCONNECT_ACCOUNT_DISABLED',
    'ERRCONNECT_ACCOUNT_LOCKED_OUT', 'ERRCONNECT_PASSWORD_EXPIRED',
    'ERRCONNECT_PASSWORD_MUST_CHANGE', 'ERRCONNECT_ACCOUNT_EXPIRED',
    'ERRCONNECT_ACCESS_DENIED', 'ERRCONNECT_SECURITY_NEGO_CONNECT_FAILED',
    'ERRCONNECT_MCS_CONNECT_INITIAL_ERROR', 'ERRCONNECT_CONNECT_CANCELLED',
    'ERRINFO_RPC_INITIATED_DISCONNECT', 'ERRINFO_LOGOFF_BY_USER',
    'ERRINFO_IDLE_TIMEOUT', 'ERRINFO_LOGON_TIMEOUT',
}
DIAGNOSTICS = {
    'connection refused': 'Server odmítl spojení.',
    'connection timed out': 'Vypršel čas pro navázání spojení.',
    'no route to host': 'Síťová cesta k serveru není dostupná.',
    'name or service not known': 'Název serveru se nepodařilo přeložit.',
    'permission denied': 'Přístup byl odmítnut.',
    'authentication failed': 'Přihlášení selhalo.',
    'certificate verify failed': 'Ověření certifikátu selhalo.',
    'unable to connect to libvirt': 'Připojení k libvirt selhalo.',
}


def log_directory():
    root = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share').expanduser()
    return root / 'logs/outsource'


def prune(directory):
    candidates = []
    for path in directory.glob('outs-*.log'):
        try:
            candidates.append((path.stat().st_mtime, path))
        except OSError:
            continue
    files = [path for _, path in sorted(candidates, reverse=True)]
    for index, path in enumerate(files):
        try:
            if index < MAX_FILES - 1 and time.time() - path.stat().st_mtime < MAX_AGE:
                continue
            # Otevřené relace mají zámek a úklid je přeskočí.
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
            with os.fdopen(fd, 'r+') as stream:
                try:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                path.unlink(missing_ok=True)
        except OSError:
            continue


class SessionLog:
    def __init__(self):
        directory = log_directory()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        prune(directory)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        fd, name = tempfile.mkstemp(prefix=f'outs-{stamp}-{os.getpid()}-', suffix='.log', dir=directory)
        self.path = Path(name)
        self.stream = os.fdopen(fd, 'w', encoding='utf-8')
        fcntl.flock(self.stream, fcntl.LOCK_EX)
        self.size = 0
        self.full = False
        self.stage = 'spuštění'
        self.codes = set()

    def write(self, event, **fields):
        self.stage = event
        if self.full:
            return
        record = {'čas': datetime.now(timezone.utc).isoformat(), 'událost': event, **fields}
        line = json.dumps(record, ensure_ascii=False) + '\n'
        if self.size + len(line.encode('utf-8')) > MAX_BYTES:
            line = json.dumps({'událost': 'Dosažen limit velikosti logu.'}, ensure_ascii=False) + '\n'
            self.full = True
        try:
            self.stream.write(line)
            self.stream.flush()
            self.size += len(line.encode('utf-8'))
        except OSError:
            # Zaplněný disk nesmí ukončit již běžící vzdálenou relaci.
            self.full = True

    def diagnostic(self, chunk):
        text = chunk.decode('utf-8', errors='replace') if isinstance(chunk, bytes) else chunk
        codes = set(re.findall(r'\b(?:ERRCONNECT|ERRINFO)_[A-Z0-9_]+\b', text)) & ERROR_CODES
        for code in sorted(codes - self.codes):
            self.write('diagnostika klienta', kód=code)
            self.codes.add(code)
        for needle, message in DIAGNOSTICS.items():
            if needle in text.lower() and needle not in self.codes:
                self.write('diagnostika klienta', zpráva=message)
                self.codes.add(needle)

    def close(self):
        try:
            self.stream.close()
        except OSError:
            pass
