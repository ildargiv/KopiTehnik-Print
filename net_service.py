"""Сетевая служба программы: владеет узлом net_link.Node, настройками сети и историей чата. Без Qt.

Настройки лежат в settings["net"]: {"enabled", "id", "name", "user", "paired": {...}, "chat": [...]}.
Окно подписывается через on_ui(kind, info): kind in presence | chat | paired | peer_found | pair_request | pair_result | job_received | sheet | printer_state.
Вызывается из потоков сети, поэтому окно обязано перенаправить событие в свой поток (сигналом Qt).
"""
import os
import time

import net_link as nl

CHAT_KEEP = 300
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")
MAX_SEND = 200 << 20            # один файл в чате не больше 200 МБ (передаётся одним кадром)
EMOJI_COMMON = "😀 😃 😄 😁 😅 😂 🙂 😉 😊 😍 😘 😎 🤔 😐 😴 😢 😡 🙏 👍 👎 👌 ✌️ 👏 🤝 💪 🔥 ⭐ ❤️ 🎉 ✅ ❌ ⚠️ ❓ ❗".split()
EMOJI_PRINT = "🖨️ 📄 📃 📑 🗂️ 📁 📎 ✂️ 📏 📐 🖼️ 📸 🎞️ 🎨 🖌️ 🌈 💧 🖍️ 🧾 📦 📥 📤 ⏳ ⌛ 🔔 🧰 🔧 🪫 🔋 🧹".split()


class NetService:
    def __init__(self, get_settings, save, on_ui=None, port=nl.PORT_TCP, udp_port=nl.PORT_UDP, host="0.0.0.0", version=""):
        self.version = version
        self._sent = {}
        self.get_settings, self.save, self.on_ui = get_settings, save, on_ui
        self.port, self.udp_port, self.host = port, udp_port, host
        self.node = None
        self.printing = None

    # ---- настройки ----
    @property
    def cfg(self):
        return self.get_settings().setdefault("net", {})

    def enabled(self):
        return bool(self.cfg.get("enabled", True))      # автопоиск работает сразу; выключается в настройках

    def set_enabled(self, on):
        if on:
            self.cfg["enabled"] = True
            self.start()
        else:
            self.stop(disable=True)

    def accept_print(self):
        return bool(self.cfg.get("accept_print", True))

    def set_accept_print(self, on):
        self.cfg["accept_print"] = bool(on)
        if self.node:
            self.node.net_enabled = bool(on)
        self.save()

    def set_files_dir(self, path):
        self.cfg["files_dir"] = path or ""
        if self.node:
            self.node.file_dir = self.files_dir()
        self.save()

    def tailscale_on(self):
        return bool(self.cfg.get("tailscale", True))

    def set_tailscale(self, on):
        self.cfg["tailscale"] = bool(on)
        self.save()

    def shared_names(self, installed):
        """Какие принтеры отданы по сети: подмножество installed. None в настройках = все."""
        allowed = self.get_settings().get("net_shared")
        return list(installed) if allowed is None else [n for n in installed if n in allowed]

    def set_shared(self, names, installed):
        names = [n for n in names if n in installed]
        self.get_settings()["net_shared"] = None if len(names) == len(list(installed)) else names
        self.save()

    def user(self):
        return self.cfg.get("user") or (self.node.name if self.node else "")

    def set_user(self, name):
        self.cfg["user"] = name.strip()[:64]
        self.save()

    def files_dir(self):
        """Папка присланных файлов («Получено»). Можно сменить в settings['net']['files_dir']."""
        d = self.cfg.get("files_dir")
        if not d:
            import app_dirs
            d = str(app_dirs.data_dir() / "Получено")
        return d

    def sound_on(self):
        return bool(self.cfg.get("sound", True))

    def set_sound(self, on):
        self.cfg["sound"] = bool(on)
        self.save()

    # ---- запуск ----
    def start(self):
        if self.node:
            return self.node
        c = self.cfg
        c["enabled"] = True
        paired = c.setdefault("paired", {})
        self.node = nl.Node(c.get("name") or "", c.get("id"), port=self.port, udp_port=self.udp_port, host=self.host,
                            peers_paired=paired, on_event=self._ev, app_version=self.version)
        self.node.net_enabled = bool(c.get("accept_print", True))
        c["id"], c["name"] = self.node.id, self.node.name
        if self.printing:
            self.attach_printing(self.printing)
        self.node.file_dir = self.files_dir()
        self.node.start()
        self.node.start_discovery(tailscale=self.cfg.get("tailscale", True))      # нет рассылки: остаётся ручной адрес
        self.save()
        return self.node

    def stop(self, disable=False):
        if disable:
            self.cfg["enabled"] = False
            self.save()
        if self.node:
            self.node.stop()
            self.node = None

    def attach_printing(self, netprinting):
        """Подключить обработчик печати (net_print.NetPrinting): ПК начинает принимать листы."""
        self.printing = netprinting
        if self.node:
            self.node.print_sheet = netprinting.print_sheet
            self.node.handlers.update(netprinting.handlers())

    # ---- события ----
    def _ev(self, kind, info):
        if kind == "chat":
            self._store(info["from"], False, info.get("user") or info.get("name", ""), info.get("text", ""), info.get("ts"),
                        chan="all" if info.get("channel") == "all" else info["from"], att=info.get("att"))
        if kind == "paired":
            self.save()
        if kind in ("sheet", "sent_sheet"):
            self._job_note(kind, info)
        if kind == "pair_result" and info.get("ok"):
            self.save()
        if self.on_ui:
            self.on_ui(kind, info)

    # ---- уведомления о печати ----
    def _job_note(self, kind, i):
        """Короткая строка в чате: задание напечатано или сбой (у отправителя и у исполнителя)."""
        peer = i.get("peer")
        name = ((self.cfg.get("paired") or {}).get(peer) or {}).get("alias") or ((self.cfg.get("paired") or {}).get(peer) or {}).get("name") or "ПК"
        text = None
        if kind == "sent_sheet":
            j = self._sent.setdefault(i["job_id"], {"ok": 0, "fail": 0, "err": ""})
            j["ok" if i["ok"] else "fail"] += 1
            if not i["ok"]:
                j["err"] = i.get("error", "")
            if j["ok"] + j["fail"] >= int(i.get("total") or 1):
                self._sent.pop(i["job_id"], None)
                text = ("Напечатано на ПК «%s»: %s, листов %d" % (name, i.get("printer", ""), j["ok"])) if not j["fail"] else \
                       ("Не всё напечатано на ПК «%s»: %d из %d. %s" % (name, j["ok"], j["ok"] + j["fail"], j["err"]))
        elif kind == "sheet" and self.node and i.get("state") in ("spooled", "failed"):
            job = self.node.jobs.get(i["job_id"])
            states = [v["state"] for k, v in self.node.sheets.items() if k[0] == i["job_id"]]
            if job and not job.get("noted") and len(states) >= job["total"] and all(x in ("spooled", "failed") for x in states):
                job["noted"] = True
                bad = states.count("failed")
                text = ("Напечатано для «%s»: %s, листов %d" % (name, job["printer"], len(states) - bad)) if not bad else \
                       ("Сбой печати для «%s»: %s, не напечатано листов %d из %d" % (name, job["printer"], bad, len(states)))
        if text and peer:
            ts = time.time()
            self._store(peer, False, "🖨 Печать", text, ts, chan=peer)
            if self.on_ui:
                self.on_ui("chat", {"from": peer, "channel": "dm", "user": "🖨 Печать", "text": text, "ts": ts, "sys": True})

    # ---- ПК ----
    def peers(self, include_hidden=False):
        """Спаренные ПК: [{id, name, online, state, hidden, trusted, addr, version}], state = ok|printing|attention|offline."""
        out = []
        for pid, p in (self.cfg.get("paired") or {}).items():
            if p.get("hidden") and not include_hidden:
                continue
            online = bool(self.node and self.node.online(pid))
            state = "offline"
            if online:
                state = "ok"
                levels = [st.get("level") for st in (self.node.peer_state.get(pid) or {}).values()]
                if any(l in ("attention", "error") for l in levels):
                    state = "attention"
                elif "printing" in levels:
                    state = "printing"
            ver = ((self.node.peer_info.get(pid) or {}).get("version", "")) if self.node else ""
            out.append({"id": pid, "name": p.get("alias") or p.get("name") or pid, "online": online, "state": state,
                        "hidden": bool(p.get("hidden")), "trusted": p.get("trusted", True), "addr": p.get("addr", ""), "version": ver})
        return out

    def set_hidden(self, peer_id, on):
        p = self.cfg.get("paired", {}).get(peer_id)
        if p is not None:
            p["hidden"] = bool(on)
            self.save()

    def set_trusted(self, peer_id, on):
        """Недоверенный ПК остаётся в чате, но печатать на ваших принтерах не может."""
        p = self.cfg.get("paired", {}).get(peer_id)
        if p is not None:
            p["trusted"] = bool(on)
            self.save()

    def remote_printers(self, peer_id):
        """Принтеры, которые ПК отдаёт по сети: [{name, profiles}]. NetError, если ПК не в сети."""
        return self._ask(peer_id, "printers", {}).get("printers", [])

    def remote_snapshot(self, peer_id, printer, profile=None, fmt=None):
        return self._ask(peer_id, "printer_snapshot", {"printer": printer, "profile": profile, "format": fmt})

    def _ask(self, peer_id, cmd, meta):
        sess = self.node.sessions.get(peer_id) if self.node else None
        if not sess or not sess.alive:
            raise nl.NetError("ПК не в сети")
        h, _ = sess.call(cmd, meta, timeout=20)
        if not h.get("ok", True):
            raise nl.NetError(h.get("error", "отказ"))
        return h

    def rename(self, peer_id, alias):
        p = self.cfg.get("paired", {}).get(peer_id)
        if p is not None:
            p["alias"] = alias.strip()[:64]
            self.save()

    def forget(self, peer_id):
        if self.node:
            self.node.forget(peer_id)
        else:
            self.cfg.get("paired", {}).pop(peer_id, None)
        self.save()

    def open_pairing(self, ttl=300):
        self.start()
        return self.node.open_pairing(ttl=ttl)

    def pair(self, addr, code, port=nl.PORT_TCP):
        self.start()
        pid = self.node.pair(addr.strip(), code.strip(), port)
        self.save()
        return pid

    def found(self):
        """Найденные в сети, но ещё не спаренные ПК: [{id, name, addr, port, via}], свежие первыми по имени."""
        if not self.node:
            return []
        out = [f for f in self.node.found_list() if not f["paired"]]
        out.sort(key=lambda f: f["name"].lower())
        return out

    def probe(self, addr, port=nl.PORT_TCP):
        """Проверка адреса, введённого вручную: {id, name, port} или None."""
        self.start()
        return self.node.probe(addr.strip(), port, timeout=3.0)

    def request_pair(self, addr, port=nl.PORT_TCP, on_code=None, cancel=None):
        """Запрос на подключение: у нас показывается 6 цифр, их вводят на другом ПК. Блокирует; вызывать в потоке."""
        self.start()
        pid = self.node.request_pair(addr.strip(), port, on_code=on_code, cancel=cancel)
        self.save()
        return pid

    def answer_pair(self, req_id, code):
        return bool(self.node and self.node.answer_pair(req_id, code))

    def deny_pair(self, req_id):
        if self.node:
            self.node.deny_pair(req_id)

    def pair_requests(self):
        return self.node.pending_pair_requests() if self.node else []

    # ---- чат ----
    def history(self, peer_id=None):
        """peer_id=None: общий канал (все сообщения «всем»)."""
        key = peer_id or "all"
        return [m for m in self.cfg.get("chat", []) if m["chan"] == key]

    def unread(self, peer_id=None):
        if peer_id is not None:
            return sum(1 for m in self.cfg.get("chat", []) if m["chan"] == peer_id and not m["me"] and not m.get("read"))
        return sum(1 for m in self.cfg.get("chat", []) if not m["me"] and not m.get("read"))

    def mark_read(self, peer_id=None):
        key = peer_id or "all"
        for m in self.cfg.get("chat", []):
            if m["chan"] == key:
                m["read"] = True
        self.save()

    def _store(self, peer, me, user, text, ts=None, chan=None, att=None):
        chat = self.cfg.setdefault("chat", [])
        m = {"chan": chan or peer, "peer": peer, "me": me, "user": user, "text": text, "ts": ts or time.time(), "read": me}
        if att:
            att = dict(att, kind="image" if att["name"].lower().endswith(IMAGE_EXT) else "file")
            m["att"] = att
        chat.append(m)
        del chat[:-CHAT_KEEP]
        self.save()

    def send_chat(self, text, peer_id=None):
        """peer_id=None: всем спаренным ПК. Офлайн-получатели получат сообщение при подключении."""
        text = text.strip()
        if not text:
            return
        self.start()
        targets = [peer_id] if peer_id else list(self.cfg.get("paired", {}))
        for pid in targets:
            self.node.chat_send(pid, text, user=self.user(), channel="all" if not peer_id else "dm")
        self._store(peer_id or "all", True, self.user(), text, chan=peer_id or "all")

    def send_file(self, path, peer_id=None, text=""):
        """Отправить файл (любой) выбранному ПК или всем. Фото в чате показываются картинкой, остальное значком."""
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        size = os.path.getsize(path)
        if size > MAX_SEND:
            raise ValueError("Файл больше %d МБ." % (MAX_SEND >> 20))
        self.start()
        targets = [peer_id] if peer_id else list(self.cfg.get("paired", {}))
        for pid in targets:
            self.node.chat_send(pid, text, user=self.user(), channel="all" if not peer_id else "dm", file=path)
        self._store(peer_id or "all", True, self.user(), text, chan=peer_id or "all",
                    att={"name": os.path.basename(path), "size": size, "path": path})

    @staticmethod
    def download(att, dest):
        """Кнопка «Скачать»: копия присланного файла туда, куда выбрал человек."""
        import shutil
        shutil.copyfile(att["path"], dest)
