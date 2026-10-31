"""Звуки чата: короткие мелодии генерируются кодом (без внешних файлов), играет QSoundEffect (QtMultimedia).
Если QtMultimedia недоступен или нет звукового устройства, звук молча пропускается."""
import math
import os
import struct
import tempfile
import wave

RATE = 22050
# имя -> [(частота Гц, длительность с)]
MELODIES = {
    "send": [(660, 0.07), (880, 0.10)],                      # короткий взлёт
    "recv": [(988, 0.09), (1319, 0.16)],                     # дзынь: две ноты вверх
    "file": [(784, 0.07), (988, 0.07), (1319, 0.14)],        # арпеджио: пришёл файл
    "error": [(330, 0.12), (247, 0.18)],                     # вниз
}


def synth(notes, volume=0.45):
    out = []
    for freq, dur in notes:
        n = int(RATE * dur)
        for i in range(n):
            t = i / RATE
            env = min(1.0, i / (RATE * 0.005)) * math.exp(-4.5 * i / n)      # быстрая атака, плавное затухание
            v = math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(2 * math.pi * freq * 2 * t)
            out.append(int(max(-1, min(1, v * env * volume)) * 32767))
    return out


def write_wavs(folder):
    os.makedirs(folder, exist_ok=True)
    paths = {}
    for name, notes in MELODIES.items():
        p = os.path.join(folder, "net_%s.wav" % name)
        if not os.path.exists(p):
            with wave.open(p, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(struct.pack("<%dh" % len(synth(notes)), *synth(notes)))
        paths[name] = p
    return paths


class Sounds:
    def __init__(self, folder=None, enabled=lambda: True):
        self.enabled = enabled
        self.paths = write_wavs(folder or os.path.join(tempfile.gettempdir(), "kopitehnik_sounds"))
        self._fx = {}
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect
            for name, p in self.paths.items():
                fx = QSoundEffect()
                fx.setSource(QUrl.fromLocalFile(p))
                fx.setVolume(0.8)
                self._fx[name] = fx
        except Exception:
            self._fx = {}

    def play(self, name):
        if not self.enabled():
            return False
        fx = self._fx.get(name)
        if fx is None:
            return False
        try:
            fx.play()
            return True
        except Exception:
            return False
