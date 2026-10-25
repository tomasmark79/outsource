"""Bounded activity logs excluding command arguments and remote session contents."""

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
# Record only known codes, never full client output.
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
    'connection refused': 'The server refused the connection.',
    'connection timed out': 'The connection timed out.',
    'no route to host': 'No route to the server is available.',
    'name or service not known': 'The server name could not be resolved.',
    'permission denied': 'Permission denied.',
    'authentication failed': 'Authentication failed.',
    'certificate verify failed': 'Certificate verification failed.',
    'unable to connect to libvirt': 'Failed to connect to libvirt.',
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
            # Open sessions hold a lock and are skipped during cleanup.
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
        self.stage = 'startup'
        self.codes = set()

    def write(self, event, **fields):
        self.stage = event
        if self.full:
            return
        record = {'timestamp': datetime.now(timezone.utc).isoformat(), 'event': event, **fields}
        line = json.dumps(record, ensure_ascii=False) + '\n'
        if self.size + len(line.encode('utf-8')) > MAX_BYTES:
            line = json.dumps({'event': 'Log size limit reached.'}, ensure_ascii=False) + '\n'
            self.full = True
        try:
            self.stream.write(line)
            self.stream.flush()
            self.size += len(line.encode('utf-8'))
        except OSError:
            # A full disk must not terminate a running remote session.
            self.full = True

    def diagnostic(self, chunk):
        text = chunk.decode('utf-8', errors='replace') if isinstance(chunk, bytes) else chunk
        codes = set(re.findall(r'\b(?:ERRCONNECT|ERRINFO)_[A-Z0-9_]+\b', text)) & ERROR_CODES
        for code in sorted(codes - self.codes):
            self.write('client diagnostic', code=code)
            self.codes.add(code)
        for needle, message in DIAGNOSTICS.items():
            if needle in text.lower() and needle not in self.codes:
                self.write('client diagnostic', message=message)
                self.codes.add(needle)

    def close(self):
        try:
            self.stream.close()
        except OSError:
            pass
