"""Печать на нескольких принтерах: общая очередь листов, по потоку на принтер.

Модуль без Qt и без доступа к Windows: отправку листа выполняет переданная функция send(printer, sheet),
поэтому всё проверяется тестами с фейковыми принтерами.
Освободившийся принтер берёт следующий лист, поэтому быстрый печатает больше. Лист, не ушедший на принтер,
возвращается в очередь и уходит на другой; принтер с подряд идущими ошибками исключается из прогона.
"""
import threading
import time
from collections import deque

QUEUED, SENDING, SENT, FAILED = "queued", "sending", "sent", "failed"


class MultiRun:
    def __init__(self, sheets, printers, send, cancel=None, max_errors=2, serialize=False, on_event=None):
        """sheets — идентификаторы листов в порядке печати; printers — имена; send(printer, sheet) блокирует
        до отправки и бросает исключение при сбое; cancel — threading.Event; on_event(kind, printer, sheet, info)."""
        if not printers:
            raise ValueError("нет принтеров")
        self.sheets = list(sheets)
        self.printers = list(dict.fromkeys(printers))
        self.send = send
        self.cancel = cancel or threading.Event()
        self.max_errors = max(1, int(max_errors))
        self.on_event = on_event
        self._lock = threading.Lock()
        self._send_lock = threading.Lock() if serialize else None      # драйверы, не терпящие параллельной отправки
        self._queue = deque(self.sheets)
        self.state = {s: QUEUED for s in self.sheets}
        self.tried = {s: set() for s in self.sheets}                   # принтеры, на которых лист уже не удался
        self.done = {p: [] for p in self.printers}
        self.errors = {p: [] for p in self.printers}
        self.excluded = {}                                             # принтер -> причина
        self.seconds = {p: 0.0 for p in self.printers}                 # время отправок: для оценки скорости
        self._alive = set(self.printers)

    def _emit(self, kind, printer, sheet, info=None):
        if self.on_event:
            try:
                self.on_event(kind, printer, sheet, info)
            except Exception:
                pass

    def _take(self, printer):
        """Следующий лист для принтера (не тот, что на нём уже падал) или None."""
        with self._lock:
            for _ in range(len(self._queue)):
                s = self._queue.popleft()
                if printer in self.tried[s]:
                    self._queue.append(s)
                    continue
                self.state[s] = SENDING
                return s
            return None

    def _pending(self, printer):
        with self._lock:
            return any(printer not in self.tried[s] for s in self._queue)

    def _worker(self, printer):
        streak = 0
        while not self.cancel.is_set():
            s = self._take(printer)
            if s is None:
                with self._lock:
                    busy = any(v == SENDING for v in self.state.values())
                    left = any(printer not in self.tried[x] for x in self._queue)
                if left:
                    continue
                if not busy:
                    return
                time.sleep(0.01)                  # другой принтер может вернуть лист в очередь
                continue
            t0 = time.time()
            try:
                if self._send_lock:
                    with self._send_lock:
                        self.send(printer, s)
                else:
                    self.send(printer, s)
            except Exception as ex:
                streak += 1
                with self._lock:
                    self.errors[printer].append((s, "%s: %s" % (ex.__class__.__name__, ex)))
                    self.tried[s].add(printer)
                    if all(p in self.tried[s] or p in self.excluded for p in self.printers):
                        self.state[s] = FAILED
                    else:
                        self.state[s] = QUEUED
                        self._queue.appendleft(s)
                    drop = streak >= self.max_errors
                    if drop:
                        self.excluded[printer] = str(ex)
                        self._alive.discard(printer)
                        for x in self.sheets:                       # у листов, которым больше некуда идти, исход известен
                            if self.state[x] == QUEUED and all(p in self.tried[x] or p in self.excluded for p in self.printers):
                                self.state[x] = FAILED
                                try:
                                    self._queue.remove(x)
                                except ValueError:
                                    pass
                self._emit("error", printer, s, str(ex))
                if drop:
                    self._emit("excluded", printer, None, str(ex))
                    return
                continue
            streak = 0
            with self._lock:
                self.state[s] = SENT
                self.done[printer].append(s)
                self.seconds[printer] += time.time() - t0
            self._emit("sent", printer, s, None)

    def run(self):
        threads = [threading.Thread(target=self._worker, args=(p,), daemon=True) for p in self.printers]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        with self._lock:                                           # все принтеры выбыли, а листы остались
            for s in self.sheets:
                if self.state[s] in (QUEUED, SENDING) and not self.cancel.is_set():
                    self.state[s] = FAILED
        return self.report()

    def report(self):
        with self._lock:
            return {
                "cancelled": self.cancel.is_set(),
                "sent": {p: list(v) for p, v in self.done.items()},
                "failed": [s for s in self.sheets if self.state[s] == FAILED],
                "not_started": [s for s in self.sheets if self.state[s] in (QUEUED, SENDING)],
                "excluded": dict(self.excluded),
                "errors": {p: list(v) for p, v in self.errors.items() if v},
                "seconds_per_sheet": {p: (self.seconds[p] / len(self.done[p]) if self.done[p] else None) for p in self.printers},
            }


def summarize(rep):
    """Строки для итога: сколько листов ушло на какой принтер."""
    lines = ["%s: %d" % (p, len(v)) for p, v in rep["sent"].items()]
    for p, why in rep["excluded"].items():
        lines.append("%s — исключён: %s" % (p, why))
    if rep["failed"]:
        lines.append("не напечатано листов: %d" % len(rep["failed"]))
    return lines
