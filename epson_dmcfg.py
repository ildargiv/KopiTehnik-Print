# -*- coding: utf-8 -*-
"""Управление частными опциями драйвера Epson через DEVMODE.

Снимки devmode:  python epson_dmcfg.py save <имя-снипка>
Сравнение:       python epson_dmcfg.py diff <снипок1> <снипок2>
Применить:       python epson_dmcfg.py apply <снипок>          (SetPrinter PRINTER_INFO_92)
Показать:        python epson_dmcfg.py status
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys

winspool = ctypes.windll.LoadLibrary("winspool.drv")
winspool.OpenPrinterW.argtypes = [wt.LPWSTR, ctypes.POINTER(wt.HANDLE), ctypes.c_void_p]
winspool.OpenPrinterW.restype = wt.BOOL
winspool.ClosePrinter.argtypes = [wt.HANDLE]
winspool.SetPrinterW.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p, wt.DWORD]
winspool.SetPrinterW.restype = wt.BOOL
winspool.DocumentPropertiesW.argtypes = [wt.HWND, wt.HANDLE, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.DWORD]
winspool.DocumentPropertiesW.restype = ctypes.c_long
PRINTER = "EPSON L8050 Series (копия 1)"
SNAPS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dmsnaps")

DM_OUT_BUFFER = 2
PRINTER_INFO_92 = 92


def _open():
    h = wt.HANDLE()
    if not winspool.OpenPrinterW(PRINTER, ctypes.byref(h), None):
        raise ctypes.WinError(ctypes.get_last_error())
    return h


def get_devmode():
    """Текущие настройки по умолчанию как bytearray DEVMODE."""
    h = _open()
    try:
        size = winspool.DocumentPropertiesW(None, h, PRINTER, None, None, 0)
        if size <= 0:
            raise RuntimeError("DocumentProperties size=%r" % size)
        buf = (ctypes.c_ubyte * size)()
        r = winspool.DocumentPropertiesW(None, h, PRINTER, buf, buf, DM_OUT_BUFFER)
        if r <= 0:
            raise RuntimeError("DocumentProperties out=%r" % r)
        return bytearray(buf)
    finally:
        winspool.ClosePrinter(h)


def set_devmode(dm):
    """Сохранить как пользовательские настройки по умолчанию.

    Epson-драйвер отвергает SetPrinter(level 92) ошибкой 124
    (ERROR_INVALID_DEVMODE), поэтому пишем туда же, куда пишет сама
    оснастка Windows «Параметры печати»: HKCU\\Printers\\DevModePerUser.
    DocumentProperties подхватывает значение сразу, перезапуск шпулера не нужен.
    """
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Printers\DevModePerUser",
                         0, winreg.KEY_SET_VALUE)
    try:
        winreg.SetValueEx(key, PRINTER, 0, winreg.REG_BINARY, bytes(dm))
    finally:
        winreg.CloseKey(key)


def header(dm):
    import struct
    # DEVMODEW (wingdi.h): dmDeviceName[32] WCHAR = 64 байт,
    # dmSpecVersion@64, dmDriverVersion@66, dmSize@68, dmDriverExtra@70
    dmSize = struct.unpack_from("<H", dm, 68)[0]
    extra = struct.unpack_from("<H", dm, 70)[0]
    return dmSize, extra, len(dm)


def cmd_save(name):
    dm = get_devmode()
    os.makedirs(SNAPS, exist_ok=True)
    p = os.path.join(SNAPS, name + ".bin")
    with open(p, "wb") as f:
        f.write(dm)
    print("saved", p, header(dm))


def cmd_diff(a, b):
    da = open(os.path.join(SNAPS, a + ".bin"), "rb").read()
    db = open(os.path.join(SNAPS, b + ".bin"), "rb").read()
    s, e, n = header(da)
    print("dmSize=%d private@%d extra=%d total=%d" % (s, s, e, n))
    n = min(len(da), len(db))
    for i in range(n):
        if da[i] != db[i]:
            where = "private+%d" % (i - s) if i >= s else "public+%d" % i
            print("  off %5d (%s): %02X -> %02X" % (i, where, da[i], db[i]))
    if len(da) != len(db):
        print("  length differs: %d vs %d" % (len(da), len(db)))


def cmd_apply(name):
    dm = bytearray(open(os.path.join(SNAPS, name + ".bin"), "rb").read())
    set_devmode(dm)
    print("applied", name)


def cmd_status():
    dm = get_devmode()
    print("current:", header(dm))


def cmd_patch(specs):
    """specs: private+123=1 или public+3=1 — правки текущего devmode и сохранение."""
    dm = get_devmode()
    s, e, n = header(dm)
    edits = []
    for sp in specs:
        where, val = sp.split("=")
        kind, off = where.split("+")
        off = int(off)
        val = int(val, 0)
        pos = off if kind == "public" else s + off
        old = dm[pos]
        dm[pos] = val
        edits.append("%s+%d: %02X -> %02X" % (kind, off, old, val))
    set_devmode(dm)
    print("patched:", "; ".join(edits))


# --- «Без полей» (borderless) в драйвере Epson L8050 -------------------------
# Флаг найден экспериментально (DocumentPropertiesW DM_IN_PROMPT + diff):
#   bit0 байта private+7700 = «Без полей»; private+7768 = код размера бумаги
#   без полей (0x36 = 10x15, 0x39 = A4) — драйвер считает сам при merge.
#   Обязательно dmDefaultSource=262 (иначе драйвер сбрасывает флаг).
BORDER_PRIV = 7700
BORDER_MIRROR = 7768
SRC_BORDERLESS = 262
SRC_NORMAL = 261
# «Цветокоррекция» в драйвере Epson: private+188, 1=«Автоматический», 2=«Настройка».
# В режиме «Настройка» при нейтральных подстройках драйвер НЕ правит цвет
# (аналог «No Color Adjustment») — нужно, т.к. приложение уже само профилит в ICC.
CCOR_PRIV = 188
CCOR_AUTO, CCOR_MANUAL = 1, 2

gdi32 = ctypes.windll.LoadLibrary("gdi32.dll")


def _merge(dm):
    """Прогнать devmode через драйвер (mode 8|2), чтобы он пересобрал приватную зону."""
    h = _open()
    try:
        size = len(dm)
        inb = ctypes.create_string_buffer(bytes(dm), size)
        outb = ctypes.create_string_buffer(size)
        r = winspool.DocumentPropertiesW(None, h, PRINTER, outb, inb, 0x08 | 2)
        if r <= 0:
            raise OSError("DocumentProperties merge failed (%s)" % r)
        return bytearray(outb.raw[:size])
    finally:
        winspool.ClosePrinter(h)


def printable_area(dm=None):
    """Реальная область печати (мм) для devmode (по умолчанию — текущего)."""
    if dm is None:
        dm = get_devmode()
    buf = ctypes.create_string_buffer(bytes(dm), len(dm))
    hdc = gdi32.CreateDCW("WINSPOOL", PRINTER, None, buf)
    if not hdc:
        return None
    try:
        pw, ph = gdi32.GetDeviceCaps(hdc, 110), gdi32.GetDeviceCaps(hdc, 111)
        ox, oy = gdi32.GetDeviceCaps(hdc, 112), gdi32.GetDeviceCaps(hdc, 113)
        dx, dy = gdi32.GetDeviceCaps(hdc, 88), gdi32.GetDeviceCaps(hdc, 90)
    finally:
        gdi32.DeleteDC(hdc)
    if dx <= 0 or dy <= 0:
        return None
    mm = lambda v, d: round(v * 25.4 / d, 1)
    return {"phys": [mm(pw, dx), mm(ph, dy)], "off": [mm(ox, dx), mm(oy, dy)],
            "area": [mm(pw - 2 * ox, dx), mm(ph - 2 * oy, dy)]}


def cmd_border(mode):
    import struct
    if mode == "status":
        dm = get_devmode()
        s, _, _ = header(dm)
        src = struct.unpack_from("<H", dm, 88)[0]
        print("priv+7700=%02X priv+7768=%02X src=%d" % (dm[s + BORDER_PRIV], dm[s + BORDER_MIRROR], src))
        print("area:", printable_area(dm))
        return
    on = mode == "on"
    dm = get_devmode()
    s, _, _ = header(dm)
    struct.pack_into("<H", dm, 88, SRC_BORDERLESS if on else SRC_NORMAL)
    if on:
        dm[s + BORDER_PRIV] |= 1
    else:
        dm[s + BORDER_PRIV] &= ~1
    dm = _merge(dm)
    set_devmode(dm)
    print("border", mode, "| priv+7700=%02X priv+7768=%02X src=%d"
          % (dm[s + BORDER_PRIV], dm[s + BORDER_MIRROR], struct.unpack_from("<H", dm, 88)[0]))
    print("area:", printable_area(dm))


def cmd_ccor(mode):
    """Цветокоррекция драйвера: off = «Автоматический», on = «Настройка» (нейтрально,
    т.е. драйвер цвет НЕ правит — аналог No Color Adjustment), status = показать."""
    if mode == "status":
        dm = get_devmode()
        s, _, _ = header(dm)
        v = dm[s + CCOR_PRIV]
        print("priv+188=%02X (%s)" % (v, {CCOR_AUTO: "Автоматический",
                                          CCOR_MANUAL: "Настройка"}.get(v, "?")))
        return
    val = CCOR_MANUAL if mode == "on" else CCOR_AUTO
    dm = get_devmode()
    s, _, _ = header(dm)
    old = dm[s + CCOR_PRIV]
    dm[s + CCOR_PRIV] = val
    dm = _merge(dm)
    set_devmode(dm)
    print("ccor", mode, "| priv+188: %02X -> %02X, после merge: %02X"
          % (old, val, dm[s + CCOR_PRIV]))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "save":
        cmd_save(sys.argv[2])
    elif cmd == "diff":
        cmd_diff(sys.argv[2], sys.argv[3])
    elif cmd == "apply":
        cmd_apply(sys.argv[2])
    elif cmd == "patch":
        cmd_patch(sys.argv[2:])
    elif cmd == "border":
        cmd_border(sys.argv[2] if len(sys.argv) > 2 else "status")
    elif cmd == "ccor":
        cmd_ccor(sys.argv[2] if len(sys.argv) > 2 else "status")
    else:
        cmd_status()

