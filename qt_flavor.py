"""Какая сборка: обычная (PySide6, Windows 10+) или LEGACY (PySide2 / Qt 5 для Windows 8). Во второй нет «Документа» и печати на нескольких принтерах."""
import sys

try:
    import PySide6
    LEGACY = bool(getattr(PySide6, "__legacy__", False))
except ImportError:
    LEGACY = False
