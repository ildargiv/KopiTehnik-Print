# -*- coding: utf-8 -*-
"""Автопилот окна свойств драйвера Epson (открытого DocumentPropertiesW):
ставит галку «Без полей» (id 2793) и пытается продавить «ОК» всеми способами,
проверяя, закрылось ли окно (= ОК обработан драйвером)."""
import ctypes, ctypes.wintypes as wt, sys, time

u32 = ctypes.windll.user32
u32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM), wt.LPARAM]
u32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u32.GetWindowTextLengthW.argtypes = [wt.HWND]
u32.GetDlgCtrlID.argtypes = [wt.HWND]
u32.GetDlgItem.argtypes = [wt.HWND, ctypes.c_int]
u32.SendMessageW.restype = ctypes.c_long
u32.PostMessageW.restype = wt.BOOL
u32.IsWindow.argtypes = [wt.HWND]
u32.SetForegroundWindow.argtypes = [wt.HWND]
u32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
u32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
u32.EnumChildWindows.argtypes = [wt.HWND, ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM), wt.LPARAM]
u32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

BM_GETCHECK, BM_CLICK = 0x00F0, 0x00F5
BM_SETCHECK_UNCHECKED, BM_SETCHECK_CHECKED = 0, 1
WM_COMMAND = 0x0111

PRN = "EPSON L8050 Series"
CHK_ID, OK_ID = 2793, 1


def find_dialog():
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, l):
        n = u32.GetWindowTextLengthW(h)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(h, buf, n + 1)
            t = buf.value
            if t.startswith("Свойства:") and PRN in t:
                found.append((h, t))
        return True

    u32.EnumWindows(cb, 0)
    return found[0][0] if found else None


def click_at(hwnd):
    r = wt.RECT()
    if not u32.GetWindowRect(hwnd, ctypes.byref(r)):
        return False
    u32.SetCursorPos((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    time.sleep(0.15)
    ct = wt.POINT((r.right - r.left) // 2, (r.bottom - r.top) // 2)
    u32.ClientToScreen(hwnd, ctypes.byref(ct))
    u32.mouse_event(0x0002, 0, 0, 0, 0)  # left down
    time.sleep(0.08)
    u32.mouse_event(0x0004, 0, 0, 0, 0)  # left up
    return True


def find_child_by_text(dlg, title):
    res = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, l):
        n = u32.GetWindowTextLengthW(h)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(h, buf, n + 1)
            if buf.value.strip() == title:
                res.append(h)
                return False
        return True

    u32.EnumChildWindows(dlg, cb, 0)
    return res[0] if res else 0


def main():
    dlg = None
    for _ in range(60):
        dlg = find_dialog()
        if dlg:
            break
        time.sleep(0.5)
    if not dlg:
        print("dialog not found"); return 2
    print("dialog hwnd", dlg, flush=True)

    chk = u32.GetDlgItem(dlg, CHK_ID)
    if not chk:
        chk = find_child_by_text(dlg, "Без полей")
    print("checkbox hwnd", chk, flush=True)
    st = u32.SendMessageW(chk, BM_GETCHECK, 0, 0)
    print("check state before:", st, flush=True)
    if st == 0:
        u32.SendMessageW(chk, BM_CLICK, 0, 0)
        st = u32.SendMessageW(chk, BM_GETCHECK, 0, 0)
        if st == 0:
            click_at(chk)
            st = u32.SendMessageW(chk, BM_GETCHECK, 0, 0)
        print("check state after:", st, flush=True)
    if st == 0:
        print("cannot set checkbox"); return 3

    time.sleep(0.5)
    attempts = []

    def alive():
        return bool(u32.IsWindow(dlg))

    ok = u32.GetDlgItem(dlg, OK_ID)
    if not ok:
        ok = find_child_by_text(dlg, "ОК")
    # 1. реальный клик мышью по кнопке ОК
    if ok:
        attempts.append(("mouse-click ОК", lambda: click_at(ok)))
    # 2. BM_CLICK
    if ok:
        attempts.append(("BM_CLICK ОК", lambda: u32.SendMessageW(ok, BM_CLICK, 0, 0)))
    # 3. WM_COMMAND BN_CLICKED от кнопки диалогу
    attempts.append(("WM_COMMAND(1,BN_CLICKED)", lambda: u32.PostMessageW(dlg, WM_COMMAND, (0 << 16) | 1, 0)))
    # 4. WM_COMMAND BN_CLICKED с lparam=кнопка
    if ok:
        attempts.append(("WM_COMMAND(1,BN_CLICKED,hbtn)", lambda: u32.PostMessageW(dlg, WM_COMMAND, (0 << 16) | 1, wt.LPARAM(ok))))
    # 5. Enter в фокусе диалога
    def enter():
        u32.SetForegroundWindow(dlg)
        time.sleep(0.2)
        u32.keybd_event(0x0D, 0x1C, 0, 0)
        time.sleep(0.06)
        u32.keybd_event(0x0D, 0x1C, 0x02, 0)
    attempts.append(("Enter key", enter))

    for name, fn in attempts:
        fn()
        time.sleep(1.2)
        if not alive():
            print("OK worked via:", name, flush=True)
            return 0
        print("attempt failed:", name, flush=True)
    print("dialog still alive — leaving it open for morning")
    return 1


if __name__ == "__main__":
    sys.exit(main())
