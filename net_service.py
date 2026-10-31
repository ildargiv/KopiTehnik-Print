"""Сетевая служба программы: владеет узлом net_link.Node, настройками сети и историей чата. Без Qt.

Настройки лежат в settings["net"]: {"enabled", "id", "name", "user", "paired": {...}, "chat": [...]}.
Окно подписывается через on_ui(kind, info): kind in presence | chat | paired | peer_found | job_received | sheet | printer_state.
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
    def __init__(self, get_settings, save, on_ui=None, port=nl.PORT_TCP, udp_port=nl.PORT_UDP, host="0.0.0.0"):
        self.get_settings, self.save, self.on_ui = get_settings, save, on_ui
        self.port, self.udp_port, self.host = port, udp_port, host
        self.node = None
        self.printing = None

    # ---- настройки ----
    @property
    def cfg(self):
        return self.get_settings().setdefault("net", {})

    def enabled(self):
        return bool(self.cfg.get("enabled"))

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
                            peers_paired=paired, on_event=self._ev)
        c["id"], c["name"] = self.node.id, self.node.name
        if self.printing:
            self.attach_printing(self.printing)
        self.node.file_dir = self.files_dir()
        self.node.start()
        try:
            self.node.listen_discovery()
            self.node.announce()
        except OSError:
            pass                                   # нет рассылки (VPN, изолированная сеть): остаётся ручной адрес
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
        if self.on_ui:
            self.on_ui(kind, info)

    # ---- ПК ----
    def peers(self):
        """Спаренные ПК: [{id, name, online, state}], state = ok|printing|attention|error|offline."""
        out = []
        for pid, p in (self.cfg.get("paired") or {}).items():
            online = bool(self.node and self.node.online(pid))
            state = "offline"
            if online:
                state = "ok"
                levels = [st.get("level") for st in (self.node.peer_state.get(pid) or {}).values()]
                if any(l in ("attention", "error") for l in levels):
                    state = "attention"
                elif "printing" in levels:
                    state = "printing"
            out.append({"id": pid, "name": p.get("alias") or p.get("name") or pid, "online": online, "state": state})
        return out

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
        """Найденные в сети, но ещё не спаренные ПК: [{id, name, addr, port}]."""
        if not self.node:
            return []
        paired = self.cfg.get("paired", {})
        return [dict(v, id=k) for k, v in self.node.found.items() if k not in paired]

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
