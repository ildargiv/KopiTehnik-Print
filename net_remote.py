"""Печать листов программы на принтере другого ПК. Лист собирается здесь в нейтральном виде (sRGB, вся бумага), цвет принтера,
поправка и настройки драйвера применяются на ПК с принтером из его профиля (net_print.NetPrinting)."""
import io
import threading
import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

import net_link as nl
import net_ui


def paper_problem(snap, L, tol=2.0):
    """Бумага в драйвере удалённого принтера должна совпадать с форматом листа в окне; иначе текст причины."""
    gw, gh = snap["paper_mm"]
    if abs(min(gw, gh) - L["PW"]) > tol or abs(max(gw, gh) - L["PH"]) > tol:
        return "бумага в драйвере удалённого принтера %g×%g мм, а лист в программе %g×%g мм" % (round(gw, 1), round(gh, 1), L["PW"], L["PH"])
    return None


def send_sheets(svc, peer_id, printer, snap, plan, photos, o, mode, compose, copies, user, fmt, progress, cancel):
    """Собрать листы и отправить по одному. Возвращает число отправленных листов; NetError/OutcomeUnknown пробрасываются.
    compose(plan, k, photos, ppi, o, mode, cache=...) -> PIL.Image."""
    node = svc._need()
    job_id = uuid.uuid4().hex[:10]
    n = len(plan["sheets"])
    total, done, cache = n * copies, 0, {}
    for k in range(n):
        if cancel():
            break
        progress(done, total, "Готовлю лист %d из %d…" % (k + 1, n))
        img = compose(plan, k, photos, snap["ppi"], o, mode, cache=cache)
        bio = io.BytesIO()
        img.convert("RGB").save(bio, "PNG", compress_level=3, dpi=(snap["ppi"], snap["ppi"]))
        data = bio.getvalue()
        del img, bio
        for r in range(copies):
            if cancel():
                break
            progress(done, total, "Отправляю лист %d из %d…" % (done + 1, total))
            node.send_sheet(peer_id, printer, job_id, "%d-%d" % (k, r), data, total=total,
                            meta={"profile": snap.get("profile"), "format": fmt, "rev": snap.get("rev"), "from": user,
                                  "photos": len(plan["sheets"][k])})
            done += 1
    progress(done, total, "")
    return done


class RemotePrintDialog(QDialog):
    got_printers = Signal(object, str)
    prog = Signal(int, int, str)
    finished_job = Signal(bool, str)

    def __init__(self, app, svc, theme, tr, compose, parent=None):
        super().__init__(parent if parent is not None else (app if isinstance(app, QWidget) else None))
        self.app, self.svc, self.tr, self.compose = app, svc, tr, compose
        self.cancel_flag = False
        self.busy = False
        self.setWindowTitle(tr("Печать на другом ПК"))
        self.setObjectName("remoteDlg")
        self.setMinimumWidth(420)
        self.setStyleSheet(net_ui._dlg_style("remoteDlg", net_ui._theme(theme)))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        t = QLabel("🖨  " + tr("Печать на другом ПК"))
        t.setObjectName("title")
        lay.addWidget(t)
        self.hint = QLabel("")
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        self.c_pc, self.c_pr = QComboBox(), QComboBox()
        for p in svc.peers():
            if p["online"]:
                self.c_pc.addItem(p["name"], p["id"])
        lay.addWidget(QLabel(tr("ПК")))
        lay.addWidget(self.c_pc)
        lay.addWidget(QLabel(tr("Принтер")))
        lay.addWidget(self.c_pr)
        lay.addWidget(self.hint)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.hide()
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        self.b_go = QPushButton(tr("Печатать"))
        self.b_go.setObjectName("primary")
        self.b_close = QPushButton(tr("Закрыть"))
        self.b_go.clicked.connect(self.start)
        self.b_close.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(self.b_close)
        row.addWidget(self.b_go)
        lay.addLayout(row)
        self.got_printers.connect(self._fill_printers)
        self.prog.connect(self._progress)
        self.finished_job.connect(self._finished)
        self.c_pc.currentIndexChanged.connect(self.load_printers)
        if not self.c_pc.count():
            self.hint.setText(tr("Нет подключённых ПК в сети."))
            self.b_go.setEnabled(False)
        else:
            self.load_printers()

    def load_printers(self):
        pid = self.c_pc.currentData()
        self.c_pr.clear()
        self.b_go.setEnabled(False)
        self.hint.setText(self.tr("Запрашиваю принтеры…"))

        def work():
            try:
                self.got_printers.emit(self.svc.remote_printers(pid), "")
            except Exception as e:
                self.got_printers.emit([], str(e))
        threading.Thread(target=work, daemon=True).start()

    def _fill_printers(self, printers, err):
        self.c_pr.clear()
        for p in printers:
            self.c_pr.addItem(p["name"], p["name"])
        self.b_go.setEnabled(bool(printers) and not self.busy)
        self.hint.setText(err or (self.tr("На этом ПК нет доступных по сети принтеров.") if not printers else
                                  self.tr("Цвет и настройки драйвера берутся из профиля принтера на том ПК.")))

    def start(self):
        if self.busy or not self.c_pr.count():
            return
        app, svc = self.app, self.svc
        peer, printer = self.c_pc.currentData(), self.c_pr.currentData()
        try:
            plan, photos, o, L = app.sheet_plan()
        except Exception as e:
            self.hint.setText(str(e))
            return
        if not plan["sheets"]:
            self.hint.setText(self.tr("Нет фото для печати: отметьте фото в списке слева."))
            return
        fmt = app.s["format"]
        copies = max(1, int(app.pr["copies"]))
        o.update(sheet_copies=1, one_by_one=True, job_pause=0.0, marks=bool(app.pr["marks"]))
        mode = app.mode()
        self.busy, self.cancel_flag = True, False
        self.b_go.setEnabled(False)
        self.c_pc.setEnabled(False)
        self.c_pr.setEnabled(False)
        self.b_close.setText(self.tr("Отмена"))
        self.bar.show()
        self.hint.setText(self.tr("Проверяю принтер…"))

        def work():
            try:
                snap = svc.remote_snapshot(peer, printer, None, fmt)
                bad = paper_problem(snap, L)
                if bad:
                    raise nl.NetError(bad)
                n = send_sheets(svc, peer, printer, snap, plan, photos, o, mode, self.compose, copies, svc.user(), fmt,
                                lambda a, b, t: self.prog.emit(a, b, t), lambda: self.cancel_flag)
                self.finished_job.emit(True, "%d" % n)
            except nl.OutcomeUnknown as e:
                self.finished_job.emit(False, "Связь потеряна, неизвестно, напечатался ли последний лист. Проверьте принтер, повторно не отправляйте вслепую. (%s)" % e)
            except Exception as e:
                self.finished_job.emit(False, str(e))
        threading.Thread(target=work, daemon=True).start()

    def _progress(self, a, b, text):
        self.bar.setMaximum(max(1, b))
        self.bar.setValue(a)
        if text:
            self.hint.setText(text)

    def _finished(self, ok, text):
        self.busy = False
        self.bar.hide()
        self.c_pc.setEnabled(True)
        self.c_pr.setEnabled(True)
        self.b_go.setEnabled(True)
        self.b_close.setText(self.tr("Закрыть"))
        if ok:
            self.hint.setText(self.tr("Отправлено листов: %s. Они в очереди принтера на том ПК.") % text)
        else:
            self.hint.setText(self.tr("Не напечатано") + ": " + text)

    def reject(self):
        if self.busy:
            self.cancel_flag = True
            return
        super().reject()
