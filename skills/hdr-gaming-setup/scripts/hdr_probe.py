"""Windows HDR pipeline ground-truth probe (stdlib only, read-only).

Collects, as JSON on stdout:
  - every stored EDID with its CTA-861 HDR static metadata (MaxTML/MaxFALL/min)
  - active displays with HDR (advanced color) state, bit depth, SDR white level
  - the ACTIVE default HDR color profile per display (ColorProfileGetDisplayDefault
    - the authoritative check; do not infer from ICM registry slots)
  - per-app Auto HDR overrides from HKCU UserGpuPreferences
  - NVIDIA driver version (if nvidia-smi is on PATH)

Run:  python hdr_probe.py
"""
import ctypes
import json
import subprocess
import winreg
from ctypes import wintypes

user32 = ctypes.windll.user32
mscms = ctypes.windll.mscms

QDC_ONLY_ACTIVE_PATHS = 2


# ---------- EDID ----------
def parse_edid(edid):
    if len(edid) < 128:
        return None
    r = {}
    w = (edid[8] << 8) | edid[9]
    r["pnp"] = "".join(chr(((w >> s) & 0x1F) + 64) for s in (10, 5, 0))
    name = ""
    for off in (54, 72, 90, 108):
        d = edid[off:off + 18]
        if d[0] == 0 and d[1] == 0 and d[3] == 0xFC:
            name = bytes(d[5:18]).decode("ascii", "ignore").strip()
    r["name"] = name
    hdr = None
    for b in range(1, len(edid) // 128):
        blk = edid[128 * b:128 * (b + 1)]
        if len(blk) < 128 or blk[0] != 0x02:  # CTA-861 extension only
            continue
        dtd_off = blk[2]
        i = 4
        while i < dtd_off and i < 127:
            tag = (blk[i] & 0xE0) >> 5
            ln = blk[i] & 0x1F
            if tag == 7 and ln >= 2 and blk[i + 1] == 0x06:  # HDR static metadata
                body = blk[i + 2:i + 1 + ln]
                hdr = {"eotf_bitmask": body[0]}
                if ln >= 4 and body[2]:
                    hdr["max_lum_nits"] = round(50 * 2 ** (body[2] / 32.0), 1)
                if ln >= 5 and body[3]:
                    hdr["max_fall_nits"] = round(50 * 2 ** (body[3] / 32.0), 1)
                if ln >= 6 and hdr.get("max_lum_nits"):
                    hdr["min_lum_nits"] = round(
                        hdr["max_lum_nits"] * ((body[4] / 255.0) ** 2) / 100.0, 4)
            i += 1 + ln
    r["hdr_static_metadata"] = hdr
    return r


def edids():
    out, seen = [], set()
    base = r"SYSTEM\CurrentControlSet\Enum\DISPLAY"
    try:
        k0 = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
    except OSError:
        return out
    i = 0
    while True:
        try:
            model = winreg.EnumKey(k0, i); i += 1
        except OSError:
            break
        j = 0
        k1 = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base + "\\" + model)
        while True:
            try:
                inst = winreg.EnumKey(k1, j); j += 1
            except OSError:
                break
            try:
                kp = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    base + f"\\{model}\\{inst}\\Device Parameters")
                edid, _ = winreg.QueryValueEx(kp, "EDID")
            except OSError:
                continue
            p = parse_edid(bytearray(edid))
            if p:
                key = (model, p.get("name"), len(edid))
                if key in seen:
                    continue
                seen.add(key)
                p["reg_model"] = model
                p["edid_bytes"] = len(edid)
                out.append(p)
    return out


# ---------- DisplayConfig ----------
class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class PATH_SOURCE(ctypes.Structure):
    _fields_ = [("adapterId", LUID), ("id", wintypes.UINT),
                ("modeInfoIdx", wintypes.UINT), ("statusFlags", wintypes.UINT)]


class RATIONAL(ctypes.Structure):
    _fields_ = [("Numerator", wintypes.UINT), ("Denominator", wintypes.UINT)]


class PATH_TARGET(ctypes.Structure):
    _fields_ = [("adapterId", LUID), ("id", wintypes.UINT),
                ("modeInfoIdx", wintypes.UINT), ("outputTechnology", wintypes.UINT),
                ("rotation", wintypes.UINT), ("scaling", wintypes.UINT),
                ("refreshRate", RATIONAL), ("scanLineOrdering", wintypes.UINT),
                ("targetAvailable", wintypes.BOOL), ("statusFlags", wintypes.UINT)]


class PATH_INFO(ctypes.Structure):
    _fields_ = [("sourceInfo", PATH_SOURCE), ("targetInfo", PATH_TARGET),
                ("flags", wintypes.UINT)]


class MODE_INFO(ctypes.Structure):
    _fields_ = [("infoType", wintypes.UINT), ("id", wintypes.UINT),
                ("adapterId", LUID), ("blob", ctypes.c_byte * 48)]


class DEVICE_INFO_HEADER(ctypes.Structure):
    _fields_ = [("type", wintypes.UINT), ("size", wintypes.UINT),
                ("adapterId", LUID), ("id", wintypes.UINT)]


class TARGET_NAME(ctypes.Structure):
    _fields_ = [("header", DEVICE_INFO_HEADER), ("flags", wintypes.UINT),
                ("outputTechnology", wintypes.UINT),
                ("edidManufactureId", wintypes.USHORT),
                ("edidProductCodeId", wintypes.USHORT),
                ("connectorInstance", wintypes.UINT),
                ("monitorFriendlyDeviceName", wintypes.WCHAR * 64),
                ("monitorDevicePath", wintypes.WCHAR * 128)]


class ADV_COLOR_INFO(ctypes.Structure):
    _fields_ = [("header", DEVICE_INFO_HEADER), ("value", wintypes.UINT),
                ("colorEncoding", wintypes.UINT),
                ("bitsPerColorChannel", wintypes.UINT)]


class SDR_WHITE_LEVEL(ctypes.Structure):
    _fields_ = [("header", DEVICE_INFO_HEADER), ("SDRWhiteLevel", wintypes.ULONG)]


def active_displays():
    npaths = wintypes.UINT(); nmodes = wintypes.UINT()
    if user32.GetDisplayConfigBufferSizes(
            QDC_ONLY_ACTIVE_PATHS, ctypes.byref(npaths), ctypes.byref(nmodes)):
        return []
    paths = (PATH_INFO * npaths.value)()
    modes = (MODE_INFO * nmodes.value)()
    if user32.QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS, ctypes.byref(npaths),
                                 paths, ctypes.byref(nmodes), modes, None):
        return []
    out = []
    for i in range(npaths.value):
        p = paths[i]
        tn = TARGET_NAME()
        tn.header.type, tn.header.size = 2, ctypes.sizeof(TARGET_NAME)
        tn.header.adapterId, tn.header.id = p.targetInfo.adapterId, p.targetInfo.id
        user32.DisplayConfigGetDeviceInfo(ctypes.byref(tn))

        ac = ADV_COLOR_INFO()
        ac.header.type, ac.header.size = 9, ctypes.sizeof(ADV_COLOR_INFO)
        ac.header.adapterId, ac.header.id = p.targetInfo.adapterId, p.targetInfo.id
        user32.DisplayConfigGetDeviceInfo(ctypes.byref(ac))

        wl = SDR_WHITE_LEVEL()
        wl.header.type, wl.header.size = 11, ctypes.sizeof(SDR_WHITE_LEVEL)
        wl.header.adapterId, wl.header.id = p.targetInfo.adapterId, p.targetInfo.id
        user32.DisplayConfigGetDeviceInfo(ctypes.byref(wl))

        # active HDR default profile via mscms (subtype 8 = extended color mode)
        prof = None
        name_ptr = ctypes.c_wchar_p()
        for scope in (1, 0):  # current-user first, then system
            if mscms.ColorProfileGetDisplayDefault(
                    scope, p.sourceInfo.adapterId, p.sourceInfo.id, 0, 8,
                    ctypes.byref(name_ptr)) == 0 and name_ptr.value:
                prof = name_ptr.value
                break

        out.append({
            "name": tn.monitorFriendlyDeviceName,
            "devicePath": tn.monitorDevicePath,
            "refresh_hz": round(p.targetInfo.refreshRate.Numerator
                                / max(1, p.targetInfo.refreshRate.Denominator), 1),
            "hdr_supported": bool(ac.value & 1),
            "hdr_enabled": bool(ac.value & 2),
            "bits_per_channel": ac.bitsPerColorChannel,
            "sdr_white_nits": round(wl.SDRWhiteLevel / 1000.0 * 80, 1)
            if wl.SDRWhiteLevel else None,
            "active_hdr_profile": prof,
        })
    return out


# ---------- Auto HDR overrides ----------
def auto_hdr_overrides():
    out = {}
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\DirectX\UserGpuPreferences")
    except OSError:
        return out
    i = 0
    while True:
        try:
            nm, v, _t = winreg.EnumValue(k, i); i += 1
        except OSError:
            break
        if "AutoHDREnable" in str(v):
            out[nm] = v
    return out


def driver_version():
    try:
        return subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10).stdout.strip() or None
    except OSError:
        return None


if __name__ == "__main__":
    print(json.dumps({
        "edids": edids(),
        "active_displays": active_displays(),
        "auto_hdr_overrides": auto_hdr_overrides(),
        "nvidia_driver": driver_version(),
    }, indent=1))
