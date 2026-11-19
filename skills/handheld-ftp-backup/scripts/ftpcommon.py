"""Shared helpers for the FTP scripts (stdlib only).

Login: anonymous by default; set FTP_USER and FTP_PASS in the environment for servers that need an
account. Plain FTP sends everything unencrypted: use it on a trusted LAN only, and stop the server
app when you are done (it exposes the storage it serves to the whole network).
"""
import ftplib
import os

TRANSIENT = (EOFError, OSError, ftplib.error_temp, ftplib.error_reply)
MAX_PERMANENT_IN_A_ROW = 5


def connect(host, port, timeout=60):
    f = ftplib.FTP()
    f.connect(host, port, timeout=timeout)
    user = os.environ.get("FTP_USER")
    if user:
        f.login(user, os.environ.get("FTP_PASS", ""))
    else:
        f.login()
    f.voidcmd("TYPE I")
    return f


def is_permanent(exc):
    """A 5xx reply (no such file, permission denied, bad name) will fail the same way on retry."""
    return isinstance(exc, ftplib.error_perm)


class PermanentStreak:
    """Abort a run after several permanent errors in a row (e.g. every upload answers 550 because
    the FTP root points at a folder that no longer exists) instead of grinding through every file."""

    def __init__(self, limit=MAX_PERMANENT_IN_A_ROW):
        self.limit, self.count = limit, 0

    def ok(self):
        self.count = 0

    def fail(self, what, exc):
        self.count += 1
        if self.count >= self.limit:
            raise SystemExit("%d permanent FTP errors in a row (last: %s: %s). Check the server's root "
                             "folder and permissions, then re-run." % (self.count, what, exc))
