# -*- coding: utf-8 -*-
"""Изучение и управление окном свойств драйвера Epson.

tree  — открыть диалог драйвера, выгрузить все элементы в epson_dlg_tree.txt, закрыть «Отмена».
find  — только найти элемент по подстроке (диалог должен быть открыт).
"""
import ctypes
import sys
import time

winspool = ctypes.windll.LoadLibrary("winspool.drv")
PRINTER = "EPSON L8050 Series (копия 1)"
DM_IN_PROMPT = 0x0008
DM_OUT_BUFFER = 0x0002
TREE = "C:\\Users\\User\\Desktop\\Программы\\KopiTehnik-Print\\epson_dlg_tree.txt"


def _open_printer():
    h = ctypes.c_void_p()
    if not winspool.OpenPrinterW(PRINTER, ctypes.byref(h), None):
        raise ctypes.WinError(ctypes.get_last_error())
    return h


def open_props_dialog(threaded=True):
    """Показывает окно настроек драйвера (блокирует, пока не закроют)."""
    def run():
        h = _open_printer()
        try:
            size = winspool.DocumentPropertiesW(None, h, PRINTER, None, None, 0)
            buf = (ctypes.c_ubyte * size)()
            winspool.DocumentPropertiesW(None, h, PRINTER, buf, buf,
                                         DM_IN_PROMPT | DM_OUT_BUFFER)
        finally:
            winspool.ClosePrinter(h)
    if threaded:
        import threading
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return t
    run()


def find_dialog(timeout=15):
    from pywinauto import Desktop
    deadline = time.time() + timeout
    while time.time() < deadline:
        for w in Desktop(backend="uia").windows():
            txt = (w.window_text() or "")
            low = txt.lower()
            if ("свойства" in low and ("докум" in low or "epson" in low or "печ" in low)) \
                    or "print preferences" in low or "epson" in low:
                return w
        time.sleep(0.5)
    return None


def dump_tree(dlg, path=TREE):
    lines = []

    def walk(el, depth=0):
        try:
            ct = el.element_info.control_type
            name = el.window_text()
            rect = el.rectangle()
            lines.append("%s%s '%s' [%d,%d %dx%d]" % (
                "  " * depth, ct, name, rect.left, rect.top,
                rect.width(), rect.height()))
        except Exception as e:
            lines.append("%s<err %s>" % ("  " * depth, e))
            return
        for ch in el.children():
            walk(ch, depth + 1)

    walk(dlg.wrapper_object() if hasattr(dlg, "wrapper_object") else dlg)
    text = "\n".join(lines)
    open(path, "w", encoding="utf-8").write(text)
    return text


def cmd_tree():
    open_props_dialog()
    dlg = find_dialog()
    if not dlg:
        print("dialog not found")
        return
    print("dialog:", dlg.window_text())
    txt = dump_tree(dlg)
    print("elements:", txt.count("\n") + 1, "-> ", TREE)
    for cb in txt.splitlines():
        if "без полей" in cb.lower() or "border" in cb.lower():
            print("BORDER-LIKE:", cb.strip())
    # закрыть отменой
    try:
        dlg.child_window(title_re="Отмена|Cancel", control_type="Button").click_input()
        print("cancelled")
    except Exception as e:
        print("cancel failed:", e)


def cmd_find(sub):
    dlg = find_dialog(timeout=5)
    if not dlg:
        print("dialog not open")
        return
    txt = dump_tree(dlg)
    for line in txt.splitlines():
        if sub.lower() in line.lower():
            print(line.strip())


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tree"
    if cmd == "tree":
        cmd_tree()
    elif cmd == "find":
        cmd_find(sys.argv[2])
