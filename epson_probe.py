# -*- coding: utf-8 -*-
"""Зонд байтов приватной зоны DEVMODE Epson: для каждой правки замераем
реальную область печати (CreateDC + GetDeviceCaps). Если какой-то байт —
«без полей», область вырастет до всего листа.

Запуск: epson_probe.py value step start stop
  value — чем заполнять dword (например 1 или 0x10), step — шаг (4),
  start/stop — диапазон смещений в байте.
Результат: dmsnaps/probe_<value>.jsonl (только отличающиеся от эталона).
"""
import ctypes, ctypes.wintypes as wt, json, os, struct, sys

wp = ctypes.WinDLL("winspool.drv")
gdi = ctypes.windll.gdi32

PRINTER = "EPSON L8050 Series (копия 1)"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dmsnaps")

wp.OpenPrinterW.argtypes = [wt.LPWSTR, ctypes.POINTER(wt.HANDLE), ctypes.c_void_p]
wp.OpenPrinterW.restype = wt.BOOL
wp.ClosePrinter.argtypes = [wt.HANDLE]
wp.DocumentPropertiesW.argtypes = [wt.HWND, wt.HANDLE, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.DWORD]
wp.DocumentPropertiesW.restype = ctypes.c_long
gdi.CreateDCW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p]
gdi.CreateDCW.restype = wt.HDC
gdi.DeleteDC.argtypes = [wt.HDC]
gdi.GetDeviceCaps.argtypes = [wt.HDC, ctypes.c_int]
gdi.GetDeviceCaps.restype = ctypes.c_int

PHYSICALWIDTH, PHYSICALHEIGHT, PHYSICALOFFSETX, PHYSICALOFFSETY = 110, 111, 112, 113
LOGPIXELSX, LOGPIXELSY = 88, 90
DM_OUT_BUFFER = 2   # у Epson-драйвера работает DM_COPY-режим (как в самой программе)

def base_blob():
    """DEVMODE по умолчанию, пригнанный драйвером к 10x15 глянцу (как при реальной печати)."""
    h = _open()
    try:
        size = wp.DocumentPropertiesW(None, h, PRINTER, None, None, 0)
        buf = (ctypes.c_ubyte * size)()
        if wp.DocumentPropertiesW(None, h, PRINTER, buf, buf, DM_OUT_BUFFER) <= 0:
            raise OSError("DocumentProperties default")
        nb = bytearray(buf)
        struct.pack_into("<H", nb, 78, 285)              # dmPaperSize 10x15
        struct.pack_into("<H", nb, 80, 1524)             # dmPaperLength
        struct.pack_into("<H", nb, 82, 1016)             # dmPaperWidth
        struct.pack_into("<H", nb, 88, 261)              # dmDefaultSource задний лоток
        struct.pack_into("<H", nb, 196, 396)             # dmMediaType глянец
        fields = int.from_bytes(bytes(nb[72:76]), "little") | 0x2 | 0x4 | 0x8
        nb[72:76] = struct.pack("<I", fields)
        inb = ctypes.create_string_buffer(bytes(nb), size)
        outb = ctypes.create_string_buffer(size)
        if wp.DocumentPropertiesW(None, h, PRINTER, outb, inb, 0x08 | 2) <= 0:
            raise OSError("DocumentProperties merge")
        return outb.raw[:size]
    finally:
        wp.ClosePrinter(h)

def _open():
    h = wt.HANDLE()
    if not wp.OpenPrinterW(PRINTER, ctypes.byref(h), None):
        raise OSError("OpenPrinter")
    return h

def geom(blob):
    buf = ctypes.create_string_buffer(blob, len(blob))
    hdc = gdi.CreateDCW("WINSPOOL", PRINTER, None, ctypes.cast(buf, ctypes.c_void_p))
    if not hdc:
        return None
    try:
        pw, ph = gdi.GetDeviceCaps(hdc, PHYSICALWIDTH), gdi.GetDeviceCaps(hdc, PHYSICALHEIGHT)
        ox, oy = gdi.GetDeviceCaps(hdc, PHYSICALOFFSETX), gdi.GetDeviceCaps(hdc, PHYSICALOFFSETY)
        dx, dy = gdi.GetDeviceCaps(hdc, LOGPIXELSX), gdi.GetDeviceCaps(hdc, LOGPIXELSY)
        if dx <= 0 or dy <= 0:
            return None
        mm = lambda v, d: round(v * 25.4 / d, 1)
        return {"phys_mm": [mm(pw, dx), mm(ph, dy)], "off_mm": [mm(ox, dx), mm(oy, dy)],
                "area_mm": [mm(pw - 2 * ox, dx), mm(ph - 2 * oy, dy)]}
    finally:
        gdi.DeleteDC(hdc)

def main():
    val = int(sys.argv[1], 0)
    step = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    lo = int(sys.argv[3]) if len(sys.argv) > 3 else 220
    hi = int(sys.argv[4]) if len(sys.argv) > 4 else 8192
    blob = base_blob()
    dm_size, extra = struct.unpack_from("<HH", blob, 68)
    base = geom(blob)
    print("base:", base, flush=True)
    logp = os.path.join(OUT, f"probe_{val}_{lo}_{hi}.jsonl")
    hits = 0
    with open(logp, "w", encoding="utf-8") as lg:
        lg.write(json.dumps({"base": base, "value": val, "dmSize": dm_size, "extra": extra}) + "\n")
        for off in range(lo, hi - 3, step):
            nb = bytearray(blob)
            struct.pack_into("<I", nb, off, val)
            g = geom(bytes(nb))
            if g is None:
                rec = {"off": off, "priv": off - 220, "geom": None}
                ok = False
            else:
                ok = g["area_mm"] != base["area_mm"]
                rec = {"off": off, "priv": off - 220, "geom": g} if ok else None
            if rec:
                lg.write(json.dumps(rec) + "\n")
                lg.flush()
                hits += 1
            if (off - lo) % 400 == 0:
                print(f"...{off} hits={hits}", flush=True)
    print("done, records:", hits, "->", logp, flush=True)

if __name__ == "__main__":
    main()
