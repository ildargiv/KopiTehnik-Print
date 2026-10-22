# -*- coding: utf-8 -*-
"""Открывает диалог свойств драйвера Epson (DocumentPropertiesW + PROMPT),
забирает DEVMODE, который вернул ОК, и сравнивает с эталоном."""
import ctypes, ctypes.wintypes as wt, os, struct, sys

wp = ctypes.WinDLL("winspool.drv")
u32 = ctypes.windll.user32

wp.OpenPrinterW.argtypes = [wt.LPWSTR, ctypes.POINTER(wt.HANDLE), ctypes.c_void_p]
wp.OpenPrinterW.restype = wt.BOOL
wp.ClosePrinter.argtypes = [wt.HANDLE]
wp.DocumentPropertiesW.argtypes = [wt.HWND, wt.HANDLE, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.DWORD]
wp.DocumentPropertiesW.restype = ctypes.c_long
u32.GetDesktopWindow.restype = wt.HWND

NAME = "EPSON L8050 Series (копия 1)"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dmsnaps")
DM_IN_PROMPT, DM_IN_BUFFER, DM_OUT_BUFFER = 0x04, 0x08, 0x02  # как в photo_crop.py (Epson понимает DM_OUT_BUFFER=2)

def main():
    h = wt.HANDLE()
    if not wp.OpenPrinterW(NAME, ctypes.byref(h), None):
        sys.exit("OpenPrinter failed")
    try:
        size = wp.DocumentPropertiesW(None, h, NAME, None, None, 0)
        print("devmode size:", size)
        cur = ctypes.create_string_buffer(size)
        if wp.DocumentPropertiesW(None, h, NAME, cur, cur, DM_OUT_BUFFER) != 1:
            sys.exit("default devmode failed")
        open(os.path.join(OUT, "prompt_in.bin"), "wb").write(cur.raw[:size])
        hwnd = u32.GetDesktopWindow()
        out = ctypes.create_string_buffer(size)
        res = wp.DocumentPropertiesW(hwnd, h, NAME, out, cur, DM_IN_BUFFER | DM_OUT_BUFFER | DM_IN_PROMPT)
        print("DocumentPropertiesW result:", res)
        if res == 1:
            blob = out.raw[:size]
            p = os.path.join(OUT, "prompt_out.bin")
            open(p, "wb").write(blob)
            print("saved", p)
            base = open(os.path.join(OUT, "prompt_in.bin"), "rb").read()
            dp = [i for i in range(size) if blob[i] != base[i]]
            print("changed bytes:", len(dp))
            for i in dp[:60]:
                print(f"  off {i} (priv {i-220}): {base[i]:02x} -> {blob[i]:02x}")
        else:
            print("cancelled / error, nothing saved")
    finally:
        wp.ClosePrinter(h)

if __name__ == "__main__":
    main()
