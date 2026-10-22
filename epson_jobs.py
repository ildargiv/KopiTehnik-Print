# -*- coding: utf-8 -*-
"""Снимает DEVMODE заданий из очереди: через EnumJobs (атрибуты) и через .SPL-файлы (сырые байты)."""
import sys, os, glob, struct, win32print

PRINTER = "EPSON L8050 Series (копия 1)"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dmsnaps")

def scan_spl(tag):
    d = os.path.join(os.environ["WINDIR"], "System32", "spool", "PRINTERS")
    for f in glob.glob(os.path.join(d, "*.SPL")):
        raw = open(f, "rb").read()
        pos = 0
        n = 0
        while True:
            i = raw.find(b"\x55\xaa", pos)
            if i < 0:
                break
            if i + 4 <= len(raw):
                dm_size = struct.unpack_from("<H", raw, i + 2)[0]
                if dm_size in (220, 224, 180, 212, 156):
                    extra = struct.unpack_from("<H", raw, i + 4)[0]
                    total = 2 * dm_size if False else dm_size + extra
                    print(f"  {os.path.basename(f)}: devmode @{i} dmSize={dm_size} extra={extra} total={total}")
                    if i + total <= len(raw):
                        p = os.path.join(OUT, f"spl_{tag}_{os.path.basename(f)}_{i}.bin")
                        open(p, "wb").write(raw[i:i + total])
                        n += 1
            pos = i + 2
        print("spl file:", f, len(raw), "bytes; found", n)

def main(tag):
    h = win32print.OpenPrinter(PRINTER)
    try:
        jobs = win32print.EnumJobs(h, 0, -1, 2)
        if not jobs:
            print("no jobs in queue")
        for j in jobs:
            dm = j.get("pDevMode")
            print("job", j.get("JobId"), repr(j.get("Document")), "status", hex(j.get("Status", 0)))
            if dm is not None:
                keys = {}
                for k in ("Size", "SpecVersion", "DriverVersion", "DriverExtra", "Fields", "Orientation",
                          "PaperSize", "PaperLength", "PaperWidth", "Copies", "DefaultSource", "Collate",
                          "Color", "Duplex", "YResolution", "PrintQuality", "MediaType", "DitherType",
                          "ICMMethod", "ICMIntent", "FormName", "LogPixels", "DriverVersion"):
                    try:
                        keys[k] = getattr(dm, k)
                    except Exception:
                        pass
                print("  ", keys)
                dd = getattr(dm, "DriverData", None)
                if dd:
                    b = bytes(dd)
                    p = os.path.join(OUT, f"jobpriv_{tag}_{j.get('JobId')}.bin")
                    open(p, "wb").write(b)
                    print("  private saved:", p, len(b), "bytes")
    finally:
        win32print.ClosePrinter(h)
    scan_spl(tag)

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "x")
