#!/usr/bin/env python3
"""Add (or list) a non-Steam game shortcut by editing Steam's shortcuts.vdf.

Steam stores non-Steam shortcuts in a small binary VDF file per user:
    <steam>/userdata/<account_id>/config/shortcuts.vdf

This tool parses that binary format, appends a new entry (preserving any
existing shortcuts), backs up the original, and round-trip-verifies its own
serializer before writing — so an existing list can't be corrupted.

IMPORTANT: Steam keeps shortcuts.vdf loaded in memory and rewrites it on exit.
Close Steam *before* writing, or your change is wiped on the next shutdown.

Pure standard library. Cross-platform (Windows / Linux / macOS).

Examples
--------
List detected Steam user(s) and existing shortcuts:
    python add_shortcut.py --list

Add a shortcut (auto-detects Steam + the single user account):
    python add_shortcut.py \
        --name "EA SPORTS FC 26" \
        --exe  "C:\\Program Files\\Electronic Arts\\EA SPORTS FC 26\\FC26.exe"

If multiple accounts exist, pass --user <account_id> (shown by --list).
"""
from __future__ import annotations

import argparse
import binascii
import os
import platform
import shutil
import sys

# ---------------------------------------------------------------------------
# Binary VDF (Valve Data Format) reader / writer
#
# Token types inside a map:
#   0x00  nested map     -> key (cstring), then children, terminated by 0x08
#   0x01  string         -> key (cstring), value (cstring)
#   0x02  int32          -> key (cstring), 4 bytes little-endian (unsigned)
#   0x08  end of map
# Strings are UTF-8, NUL-terminated. The whole file is one root map whose only
# key is "shortcuts" -> { "0": {entry}, "1": {entry}, ... }.
# ---------------------------------------------------------------------------


class _Reader:
    def __init__(self, data: bytes):
        self.d = data
        self.i = 0

    def cstring(self) -> str:
        end = self.d.index(b"\x00", self.i)
        s = self.d[self.i:end].decode("utf-8")
        self.i = end + 1
        return s

    def byte(self) -> int:
        b = self.d[self.i]
        self.i += 1
        return b

    def int32(self) -> int:
        v = int.from_bytes(self.d[self.i:self.i + 4], "little", signed=False)
        self.i += 4
        return v

    def read_map(self) -> dict:
        out: dict = {}
        while True:
            t = self.byte()
            if t == 0x08:          # end of map
                return out
            key = self.cstring()
            if t == 0x00:
                out[key] = self.read_map()
            elif t == 0x01:
                out[key] = self.cstring()
            elif t == 0x02:
                out[key] = self.int32()
            else:
                raise ValueError(f"Unknown VDF token 0x{t:02x} at offset {self.i}")


def parse(data: bytes) -> dict:
    return _Reader(data).read_map()


def _cstr(s: str) -> bytes:
    return s.encode("utf-8") + b"\x00"


def serialize_map(m: dict) -> bytes:
    out = bytearray()
    for key, val in m.items():
        if isinstance(val, dict):
            out += b"\x00" + _cstr(key) + serialize_map(val)
        elif isinstance(val, bool):                     # guard: bool before int
            out += b"\x02" + _cstr(key) + int(val).to_bytes(4, "little")
        elif isinstance(val, int):
            out += b"\x02" + _cstr(key) + (val & 0xFFFFFFFF).to_bytes(4, "little")
        elif isinstance(val, str):
            out += b"\x01" + _cstr(key) + _cstr(val)
        else:
            raise TypeError(f"Unsupported VDF value type for {key!r}: {type(val)}")
    out += b"\x08"                                       # end of this map
    return bytes(out)


# ---------------------------------------------------------------------------
# Shortcut construction
# ---------------------------------------------------------------------------

def gen_appid(exe_quoted: str, name: str) -> int:
    """Legacy non-Steam appid: crc32(exe+name) with the high bit set."""
    crc = binascii.crc32((exe_quoted + name).encode("utf-8")) & 0xFFFFFFFF
    return crc | 0x80000000


def make_entry(name: str, exe: str, start_dir: str | None,
               launch_options: str, icon: str) -> dict:
    exe_q = f'"{exe}"'
    if not start_dir:
        start_dir = os.path.dirname(exe)
    start_q = f'"{start_dir}"'
    # Field order mirrors what the Steam client itself writes.
    return {
        "appid": gen_appid(exe_q, name),
        "AppName": name,
        "Exe": exe_q,
        "StartDir": start_q,
        "icon": icon,
        "ShortcutPath": "",
        "LaunchOptions": launch_options,
        "IsHidden": 0,
        "AllowDesktopConfig": 1,
        "AllowOverlay": 1,
        "OpenVR": 0,
        "Devkit": 0,
        "DevkitGameID": "",
        "DevkitOverrideAppID": 0,
        "LastPlayTime": 0,
        "FlatpakAppID": "",
        "tags": {},
    }


# ---------------------------------------------------------------------------
# Steam discovery
# ---------------------------------------------------------------------------

def steam_root() -> str | None:
    sysname = platform.system()
    candidates: list[str] = []
    if sysname == "Windows":
        # Prefer the registry, fall back to common install dirs.
        try:
            import winreg
            for hive, sub in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
                try:
                    with winreg.OpenKey(hive, sub) as k:
                        val = winreg.QueryValueEx(k, "SteamPath" if hive == winreg.HKEY_CURRENT_USER else "InstallPath")[0]
                        candidates.append(val.replace("/", "\\"))
                except OSError:
                    pass
        except Exception:
            pass
        candidates += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    elif sysname == "Darwin":
        candidates.append(os.path.expanduser("~/Library/Application Support/Steam"))
    else:  # Linux
        home = os.path.expanduser("~")
        candidates += [
            os.path.join(home, ".steam", "steam"),
            os.path.join(home, ".local", "share", "Steam"),
            os.path.join(home, ".var", "app", "com.valvesoftware.Steam", "data", "Steam"),
        ]
    for c in candidates:
        if c and os.path.isdir(os.path.join(c, "userdata")):
            return c
    return None


def find_users(root: str) -> list[str]:
    ud = os.path.join(root, "userdata")
    users = []
    for name in os.listdir(ud):
        if name.isdigit() and os.path.isdir(os.path.join(ud, name, "config")):
            users.append(name)
    return users


def vdf_path(root: str, user: str) -> str:
    return os.path.join(root, "userdata", user, "config", "shortcuts.vdf")


# ---------------------------------------------------------------------------
# Self-check: prove the serializer is correct on this file before writing.
# ---------------------------------------------------------------------------

def roundtrip_ok(original: bytes) -> bool:
    try:
        return serialize_map(parse(original)) == original
    except Exception:
        return False


def steam_running() -> bool:
    try:
        if platform.system() == "Windows":
            out = os.popen('tasklist /FI "IMAGENAME eq steam.exe" /NH').read().lower()
            return "steam.exe" in out
        out = os.popen("pgrep -x steam 2>/dev/null").read().strip()
        return bool(out)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Add a non-Steam shortcut to Steam.")
    ap.add_argument("--name", help="Display name in the Steam library")
    ap.add_argument("--exe", help="Full path to the executable")
    ap.add_argument("--start-dir", help="Working directory (default: the exe's folder)")
    ap.add_argument("--launch-options", default="", help="Launch options string")
    ap.add_argument("--icon", default="", help="Path to an icon file (optional)")
    ap.add_argument("--user", help="Steam account id (under userdata/). Required if multiple exist.")
    ap.add_argument("--steam-root", help="Override Steam install dir auto-detection")
    ap.add_argument("--list", action="store_true", help="List Steam users + existing shortcuts, then exit")
    ap.add_argument("--force", action="store_true", help="Write even if Steam appears to be running")
    args = ap.parse_args(argv)

    root = args.steam_root or steam_root()
    if not root:
        print("ERROR: could not locate a Steam installation. Pass --steam-root.", file=sys.stderr)
        return 2
    users = find_users(root)
    if not users:
        print(f"ERROR: no user accounts under {root}\\userdata", file=sys.stderr)
        return 2

    if args.list:
        print(f"Steam root: {root}")
        for u in users:
            p = vdf_path(root, u)
            n = 0
            if os.path.exists(p):
                try:
                    sc = parse(open(p, "rb").read()).get("shortcuts", {})
                    n = len(sc)
                    names = [e.get("AppName", "?") for e in sc.values()]
                except Exception as e:
                    names = [f"<parse error: {e}>"]
            else:
                names = []
            print(f"  user {u}: {n} shortcut(s)" + ("" if not names else " -> " + ", ".join(names)))
        return 0

    if not args.name or not args.exe:
        print("ERROR: --name and --exe are required (or use --list).", file=sys.stderr)
        return 2

    if len(users) > 1 and not args.user:
        print("ERROR: multiple Steam users found; pass --user <id>. Options: " + ", ".join(users), file=sys.stderr)
        return 2
    user = args.user or users[0]
    if user not in users:
        print(f"ERROR: user {user} not found. Options: {', '.join(users)}", file=sys.stderr)
        return 2

    if steam_running() and not args.force:
        print("ERROR: Steam appears to be running. Close it first (it rewrites "
              "shortcuts.vdf on exit and would wipe this change), or pass --force.",
              file=sys.stderr)
        return 3

    path = vdf_path(root, user)
    if os.path.exists(path):
        original = open(path, "rb").read()
    else:
        original = serialize_map({"shortcuts": {}})  # synthesize an empty file

    if not roundtrip_ok(original):
        print("ERROR: round-trip self-check failed on the existing shortcuts.vdf — "
              "refusing to write so nothing gets corrupted.", file=sys.stderr)
        return 4

    root_map = parse(original)
    shortcuts = root_map.setdefault("shortcuts", {})

    # Don't duplicate an identical existing shortcut.
    exe_q = f'"{args.exe}"'
    for e in shortcuts.values():
        if e.get("Exe") == exe_q and e.get("AppName") == args.name:
            print(f"Already present: {args.name} -> {args.exe} (no change).")
            return 0

    next_index = str(max((int(k) for k in shortcuts), default=-1) + 1)
    shortcuts[next_index] = make_entry(
        args.name, args.exe, args.start_dir, args.launch_options, args.icon)

    new_bytes = serialize_map(root_map)

    # Back up, then write.
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")
        print(f"Backup -> {path}.bak")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(new_bytes)

    # Verify readback.
    readback = open(path, "rb").read()
    ok = readback == new_bytes and parse(readback)["shortcuts"][next_index]["AppName"] == args.name
    print(f"Wrote {len(new_bytes)} bytes to {path}")
    print(f"Added '{args.name}' as shortcut index {next_index}. Readback OK: {ok}")
    print("Reopen Steam — it'll appear under your library (Non-Steam category).")
    return 0 if ok else 5


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
