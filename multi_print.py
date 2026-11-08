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


class Cancelled(Exception):
    """send() прерван отменой: это не сбой принтера, лист возвращается в очередь."""


class MultiRun:
    def __init__(self, sheets, printers, send, cancel=None, max_errors=2, serialize=False, on_event=None,
                 backlog=None, window=2, slow_factor=3.0, poll=0.2, blocks=False):
        """sheets — идентификаторы листов в порядке печати; printers — имена; send(printer, sheet) блокирует
        до отправки и бросает исключение при сбое; cancel — threading.Event; on_event(kind, printer, sheet, info).
        backlog(printer) -> число ещё не напечатанных заданий этого прогона в очереди принтера (или None, если неизвестно).
        Новый лист принтер получает, только когда в очереди меньше window заданий: так медленный или застрявший принтер
        сам получает меньше листов. Если принтер не освобождает окно в slow_factor раз дольше своего обычного темпа, шлётся событие «slow».
        blocks=True: каждому принтеру сначала достаётся свой подряд идущий блок листов (стопки не перемешиваются),
        а освободившийся раньше берёт листы с конца чужого блока."""
        if not printers:
            raise ValueError("нет принтеров")
        self.sheets = list(sheets)
        self.printers = list(dict.fromkeys(printers))
        self.send = send
        self.cancel = cancel or threading.Event()
        self.max_errors = max(1, int(max_errors))
        self.on_event = on_event
        self._lock = threading.RLock()
        self._send_lock = threading.Lock() if serialize else None      # драйверы, не терпящие параллельной отправки
        self._queue = deque(self.sheets)
        self._own = {}
        if blocks and len(self.printers) > 1:
            self._queue = deque()                                      # общая очередь нужна только для повторов
            n, k = len(self.sheets), len(self.printers)
            lo = 0
            for i, p in enumerate(self.printers):
                hi = lo + n // k + (1 if i < n % k else 0)
                self._own[p] = deque(self.sheets[lo:hi])
                lo = hi
        self._cond = threading.Condition(self._lock)
        self.state = {s: QUEUED for s in self.sheets}
        self.tries = {s: {p: 0 for p in self.printers} for s in self.sheets}   # неудачные попытки листа на принтере
        self.done = {p: [] for p in self.printers}
        self.errors = {p: [] for p in self.printers}
        self.excluded = {}                                             # принтер -> причина
        self.seconds = {p: 0.0 for p in self.printers}                 # время отправок: для оценки скорости
        self._alive = set(self.printers)
        self.backlog, self.window, self.slow_factor = backlog, max(1, int(window)), float(slow_factor)
        self.slow = set()
        self.poll = poll
        self._last_done = {p: time.time() for p in self.printers}
        self._gaps = {p: deque(maxlen=5) for p in self.printers}

    def _emit(self, kind, printer, sheet, info=None):
        if self.on_event:
            try:
                self.on_event(kind, printer, sheet, info)
            except Exception:
                pass

    def _eligible(self, s, printer):
        return self.tries[s][printer] < self.max_errors

    def _dead(self, s):
        """Листу больше некуда идти: на каждом живом принтере исчерпаны попытки."""
        return not any(p in self._alive and self._eligible(s, p) for p in self.printers)

    def _queues(self):
        return [self._queue] + list(self._own.values())

    def _remove(self, s):
        for q in self._queues():
            try:
                q.remove(s)
                return
            except ValueError:
                pass

    def _take(self, printer):
        """Следующий по порядку лист для принтера или None. Порядок очереди сохраняется."""
        for q in [self._queue, self._own.get(printer, deque())]:       # сначала повторы, затем свой блок
            for i, s in enumerate(q):
                if self._eligible(s, printer):
                    del q[i]
                    self.state[s] = SENDING
                    return s
        donors = sorted((q for p, q in self._own.items() if p != printer and q), key=len, reverse=True)
        for q in donors:                                               # своё кончилось: берём с конца самого длинного чужого блока
            for i in range(len(q) - 1, -1, -1):
                if self._eligible(q[i], printer):
                    s = q[i]
                    del q[i]
                    self.state[s] = SENDING
                    return s
        return None

    def _gate(self, printer):
        """Ждём, пока в очереди принтера освободится окно; False — прогон отменён."""
        if not self.backlog:
            return True
        while not self.cancel.is_set():
            try:
                n = self.backlog(printer)
            except Exception:
                n = None
            if n is None or n < self.window:
                if printer in self.slow:
                    self.slow.discard(printer)
                    self._emit("recovered", printer, None, None)
                return True
            gaps = sorted(self._gaps[printer])
            if gaps and printer not in self.slow:
                typical = gaps[len(gaps) // 2]
                if time.time() - self._last_done[printer] > max(typical * self.slow_factor, 20.0):
                    self.slow.add(printer)
                    self._emit("slow", printer, None, None)
            time.sleep(self.poll)
        return False

    def note_printed(self, printer):
        """Принтер реально закончил лист (вызывает опрос очереди): так считается обычный темп."""
        now = time.time()
        with self._lock:
            self._gaps[printer].append(now - self._last_done[printer])
            self._last_done[printer] = now

    def _worker(self, printer):
        streak = 0
        while True:
            if not self._gate(printer):
                return
            with self._cond:
                s = None
                while s is None:
                    if self.cancel.is_set():
                        return
                    s = self._take(printer)
                    if s is None:
                        if not any(v in (QUEUED, SENDING) for v in self.state.values()):
                            return
                        self._cond.wait(0.05)                     # другой принтер может вернуть лист в очередь
            t0 = time.time()
            try:
                if self._send_lock:
                    with self._send_lock:
                        self.send(printer, s)
                else:
                    self.send(printer, s)
            except Cancelled:
                with self._cond:
                    self.state[s] = QUEUED
                    self._queue.appendleft(s)
                    self._cond.notify_all()
                return
            except BaseException as ex:                        # SystemExit и т.п.: лист не должен остаться в SENDING навсегда
                streak += 1
                with self._cond:
                    self.errors[printer].append((s, "%s: %s" % (ex.__class__.__name__, ex)))
                    self.tries[s][printer] += 1
                    drop = streak >= self.max_errors or not isinstance(ex, Exception)
                    if drop:
                        self.excluded[printer] = str(ex) or ex.__class__.__name__
                        self._alive.discard(printer)
                    self.state[s] = QUEUED
                    self._queue.appendleft(s)
                    if drop and printer in self._own:           # блок выбывшего принтера уходит в общую очередь
                        self._queue.extend(self._own[printer])
                        self._own[printer].clear()
                    for x in [y for q in self._queues() for y in q]:      # исход листов, которым больше некуда идти, известен
                        if self._dead(x):
                            self.state[x] = FAILED
                            self._remove(x)
                    self._cond.notify_all()
                self._emit("error", printer, s, str(ex))
                if drop:
                    self._emit("excluded", printer, None, str(ex))
                    return
                continue
            streak = 0
            with self._cond:
                self.state[s] = SENT
                self.done[printer].append(s)
                self.seconds[printer] += time.time() - t0
                count = sum(len(v) for v in self.done.values())
                self._cond.notify_all()
            self._emit("sent", printer, s, count)

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
