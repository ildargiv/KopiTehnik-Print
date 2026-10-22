# -*- coding: utf-8 -*-
"""Мягкий кликер окна свойств Epson: PostMessage/BM_CLICK не используем
(они вешают диалог), только реальные мышиные события."""
import ctypes, ctypes.wintypes as wt, sys, time

u32 = ctypes.windll.user32
u32.GetWindowTextLengthW.argtypes = [wt.HWND]
u32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u32.IsWindowVisible.argtypes = [wt.HWND]
u32.GetDlgItem.argtypes = [wt.HWND, ctypes.c_int]
u32.GetDlgItem.restype = wt.HWND
u32.SendMessageW.restype = ctypes.c_long
u32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
u32.SetForegroundWindow.argtypes = [wt.HWND]
u32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
u32.WindowFromPoint.argtypes = [wt.POINT]
u32.WindowFromPoint.restype = wt.HWND

EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
BM_GETCHECK = 0x00F0


def title(h):
    n = u32.GetWindowTextLengthW(h)
    if not n:
        return ""
    b = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(h, b, n + 1)
    return b.value


def find_dialog():
    found = []

    @EnumProc
    def cb(h, l):
        t = title(h)
        if t.startswith("Свойства:") and "EPSON L8050" in t:
            found.append(h)
        return True

    u32.EnumWindows(cb, 0)
    return found[0] if found else None


def click(hwnd):
    r = wt.RECT()
    if not u32.GetWindowRect(hwnd, ctypes.byref(r)):
        return False
    x, y = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    for _ in range(3):
        u32.SetCursorPos(x, y)
        time.sleep(0.2)
        p = wt.POINT(x, y)
        w = u32.WindowFromPoint(p)
        if w:
            break
        time.sleep(0.3)
    time.sleep(0.1)
    u32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.07)
    u32.mouse_event(0x0004, 0, 0, 0, 0)
    return True


def main():
    dlg = find_dialog()
    if not dlg:
        print("no dialog"); return 2
    chk = u32.GetDlgItem(dlg, 2793)
    st = u32.SendMessageW(chk, BM_GETCHECK, 0, 0)
    print("state before:", st, "under cursor test", flush=True)
    if st == 0:
        u32.SetForegroundWindow(dlg)
        time.sleep(0.3)
        click(chk)
        time.sleep(0.8)
        st = u32.SendMessageW(chk, BM_GETCHECK, 0, 0)
        print("state after mouse click:", st, flush=True)
    if st == 0:
        print("still unchecked"); return 3
    ok = u32.GetDlgItem(dlg, 1)
    click(ok)
    time.sleep(1.5)
    gone = not u32.IsWindowVisible(dlg)
    print("dialog closed after OK click:", gone, flush=True)
    return 0 if gone else 1


if __name__ == "__main__":
    sys.exit(main())
