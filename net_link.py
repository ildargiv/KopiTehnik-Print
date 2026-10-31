"""Сетевое соединение экземпляров КопиТехник PRINT (только стандартная библиотека, без Qt и без Windows).

Архитектура: dev/архитектура-сеть-принтеров.md (проект). Этап 1:
  * Узел (Node) с постоянным id и именем; обнаружение по UDP (id, имя, порт; без секретов) и ручной адрес.
  * Спаривание по одноразовому коду сети: из кода и двух случайных чисел выводится собственный ключ пары; код дальше не нужен.
    «Забыть ПК» = удалить ключ (на обеих сторонах).
  * Постоянное соединение с каждым спаренным ПК, пульс раз в 5 с (нет кадров 15 с = офлайн), автопереподключение,
    события presence (online/offline), printer_state, chat.
  * Кадры подписаны ключом сессии и номером кадра (подмена и повтор отсекаются). Содержимое НЕ шифруется (решение владельца для
    доверенной сети; Tailscale шифрует сам).
  * Задания без дублей: ключ (job_id, sheet_id), у исполнителя одна очередь на каждый физический принтер,
    submit отвечает сразу, состояния queued/printing/spooled/failed приходят событием; при обрыве исход «неизвестно» (OutcomeUnknown).
  * Чат: сообщения с очередью доставки при офлайне.
Печать выполняет обработчик print_sheet(meta, data), переданный программой; принтеры модуль не трогает.
Кадр: 4 байта длины | JSON-заголовок | 4 байта длины данных | данные | 32 байта HMAC (после рукопожатия).
"""
import hashlib
import hmac
import json
import os
import socket
import struct
import threading
import time
import uuid
from collections import deque

PORT_TCP = 47615
PORT_UDP = 47616
PROTO = 2
MAX_PRE_AUTH = 1 << 16        # до проверки ключа принимается не больше 64 КБ
MAX_HEADER = 1 << 20
MAX_DATA = 256 << 20
PING_EVERY = 5.0
DEAD_AFTER = 15.0
MAX_SESSIONS = 32
DEFAULT_MAX_SHEETS = 500       # потолок листов за одно задание


class NetError(Exception):
    pass


class AuthError(NetError):
    pass


class OutcomeUnknown(NetError):
    """Связь оборвалась после приёма листа: неизвестно, напечатан ли он. Перекидывать на другой принтер нельзя."""


def new_code():
    return os.urandom(16).hex()


def _b(x):
    return x if isinstance(x, bytes) else str(x).encode()


def _mac(key, *parts):
    h = hmac.new(_b(key), digestmod=hashlib.sha256)
    for p in parts:
        h.update(_b(p))
        h.update(b"\x00")
    return h.digest()


def _recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise NetError("соединение закрыто")
        buf += chunk
    return bytes(buf)


class Channel:
    def __init__(self, sock):
        self.sock, self.key = sock, None
        self.seq_out = self.seq_in = 0
        self._wlock = threading.Lock()

    def send(self, header, data=b""):
        h = json.dumps(header, ensure_ascii=False).encode()
        if len(h) > MAX_HEADER or len(data) > MAX_DATA:
            raise NetError("кадр слишком большой")
        with self._wlock:
            body = struct.pack(">I", len(h)) + h + struct.pack(">I", len(data)) + data
            tag = _mac(self.key, struct.pack(">Q", self.seq_out), body) if self.key else b""
            self.seq_out += 1
            self.sock.sendall(body + tag)

    def recv(self):
        limit_h = MAX_HEADER if self.key else MAX_PRE_AUTH
        hl = struct.unpack(">I", _recv_exact(self.sock, 4))[0]
        if hl > limit_h:
            raise NetError("заголовок слишком большой")
        h = _recv_exact(self.sock, hl)
        dl = struct.unpack(">I", _recv_exact(self.sock, 4))[0]
        if dl > (MAX_DATA if self.key else 0):
            raise NetError("данные слишком большие")
        data = _recv_exact(self.sock, dl)
        if self.key:
            tag = _recv_exact(self.sock, 32)
            body = struct.pack(">I", hl) + h + struct.pack(">I", dl) + data
            if not hmac.compare_digest(tag, _mac(self.key, struct.pack(">Q", self.seq_in), body)):
                raise AuthError("неверная подпись кадра")
        self.seq_in += 1
        return json.loads(h.decode()), data


# ---------- рукопожатие ----------
def _client_handshake(ch, node, peer_key=None, code=None):
    """peer_key — ключ пары (обычное подключение) или code — код сети (спаривание). Возвращает (id пира, имя, ключ пары)."""
    secret = peer_key or code
    mode = "auth" if peer_key else "pair"
    cn = os.urandom(16).hex()
    ch.send({"t": "hello", "proto": PROTO, "mode": mode, "id": node.id, "name": node.name, "nonce": cn})
    h, _ = ch.recv()
    if h.get("t") != "challenge":
        raise AuthError(h.get("error", "отказ узла"))
    sn = h["nonce"]
    if not hmac.compare_digest(bytes.fromhex(h["proof"]), _mac(secret, "srv", cn, sn)):
        raise AuthError("узел не знает ключ")
    ch.send({"t": "auth", "proof": _mac(secret, "cli", cn, sn).hex()})
    ch.key = _mac(secret, "sess", cn, sn)
    h, _ = ch.recv()
    if h.get("t") != "ok":
        raise AuthError(h.get("error", "отказ"))
    pair_key = _mac(secret, "pair", cn, sn).hex() if mode == "pair" else peer_key
    return h["id"], h.get("name", ""), pair_key


def _server_handshake(ch, node):
    h, _ = ch.recv()
    if h.get("t") != "hello" or h.get("proto") != PROTO:
        ch.send({"t": "error", "error": "неподдерживаемый протокол"})
        raise AuthError("неподдерживаемый протокол")
    peer_id, mode, cn, sn = h["id"], h.get("mode"), h["nonce"], os.urandom(16).hex()
    if mode == "pair":
        secret = node._pairing_code()
        if not secret:
            ch.send({"t": "error", "error": "спаривание не открыто"})
            raise AuthError("спаривание не открыто")
    else:
        p = node.peers_paired.get(peer_id)
        if not p:
            ch.send({"t": "error", "error": "ПК не спарен"})
            raise AuthError("ПК не спарен")
        secret = p["key"]
    ch.send({"t": "challenge", "nonce": sn, "proof": _mac(secret, "srv", cn, sn).hex()})
    a, _ = ch.recv()
    if a.get("t") != "auth" or not hmac.compare_digest(bytes.fromhex(a.get("proof", "")), _mac(secret, "cli", cn, sn)):
        ch.send({"t": "error", "error": "неверный ключ"})
        raise AuthError("неверный ключ")
    ch.key = _mac(secret, "sess", cn, sn)
    ch.send({"t": "ok", "id": node.id, "name": node.name})
    pair_key = _mac(secret, "pair", cn, sn).hex() if mode == "pair" else secret
    return peer_id, h.get("name", ""), pair_key, mode


# ---------- сессия ----------
class Session:
    """Двусторонняя сессия: запросы req/res и события evt по одному соединению."""

    def __init__(self, node, ch, peer_id, peer_name, initiator_id):
        self.node, self.ch, self.peer_id, self.peer_name = node, ch, peer_id, peer_name
        self.initiator_id = initiator_id
        self.alive = True
        self.last_rx = time.time()
        self._rid = 0
        self._wait = {}
        self._lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._pinger, daemon=True).start()

    def close(self):
        if self.alive:
            self.alive = False
            try:
                self.ch.sock.shutdown(socket.SHUT_RDWR)      # close() один не будит поток, ждущий в recv
            except OSError:
                pass
            try:
                self.ch.sock.close()
            except OSError:
                pass
            with self._lock:
                for ev, box in self._wait.values():
                    box.setdefault("err", "соединение закрыто")
                    ev.set()
            self.node._session_closed(self)

    def event(self, name, meta=None, data=b""):
        self.ch.send({"t": "evt", "name": name, "meta": meta or {}}, data)

    def call(self, cmd, meta=None, data=b"", timeout=30.0):
        with self._lock:
            self._rid += 1
            rid = self._rid
            ev, box = threading.Event(), {}
            self._wait[rid] = (ev, box)
        try:
            self.ch.send({"t": "req", "cmd": cmd, "rid": rid, "meta": meta or {}}, data)
        except (OSError, NetError):
            self.close()
            raise NetError("нет связи")
        if not ev.wait(timeout):
            raise NetError("нет ответа")
        with self._lock:
            self._wait.pop(rid, None)
        if "err" in box:
            raise NetError(box["err"])
        return box["h"], box["data"]

    def _pinger(self):
        while self.alive:
            time.sleep(PING_EVERY)
            if time.time() - self.last_rx > DEAD_AFTER:
                self.close()
                return
            try:
                self.ch.send({"t": "ping"})
            except (OSError, NetError):
                self.close()
                return

    def _reader(self):
        try:
            while self.alive:
                h, data = self.ch.recv()
                self.last_rx = time.time()
                t = h.get("t")
                if t == "ping":
                    self.ch.send({"t": "pong"})
                elif t == "res":
                    with self._lock:
                        w = self._wait.get(h.get("rid"))
                    if w:
                        w[1]["h"], w[1]["data"] = h, data
                        w[0].set()
                elif t == "req":
                    self.node._pool(self._handle_req, h, data)
                elif t == "evt":
                    self.node._on_evt(self, h.get("name"), h.get("meta") or {}, data)
        except (NetError, OSError, ValueError, KeyError):
            pass
        finally:
            self.close()

    def _handle_req(self, h, data):
        try:
            res, out = self.node._dispatch(self, h.get("cmd"), h.get("meta") or {}, data)
            self.ch.send({"t": "res", "rid": h.get("rid"), "ok": True, **res}, out)
        except Exception as e:
            try:
                self.ch.send({"t": "res", "rid": h.get("rid"), "ok": False, "error": str(e)})
            except (OSError, NetError):
                self.close()


# ---------- очередь принтера ----------
class _PrinterQueue:
    """Одна очередь на физический принтер: задания идут по одному."""

    def __init__(self, node, printer):
        self.node, self.printer = node, printer
        self.q = deque()
        self.cv = threading.Condition()
        threading.Thread(target=self._run, daemon=True).start()

    def put(self, item):
        with self.cv:
            self.q.append(item)
            self.cv.notify()

    def depth(self):
        with self.cv:
            return len(self.q)

    def _run(self):
        while not self.node._stop.is_set():
            with self.cv:
                while not self.q and not self.node._stop.is_set():
                    self.cv.wait(0.5)
                if self.node._stop.is_set():
                    return
                key, sess_id, meta, data = self.q.popleft()
            self.node._run_sheet(key, sess_id, meta, data)


# ---------- узел ----------
class Node:
    def __init__(self, name="", node_id=None, handlers=None, port=PORT_TCP, udp_port=PORT_UDP, host="0.0.0.0",
                 broadcast="255.255.255.255", on_event=None, peers_paired=None, max_sheets=DEFAULT_MAX_SHEETS,
                 print_sheet=None):
        """peers_paired: {id: {"name","key","addr","port"}} (хранит программа; to_state()/from_state()).
        print_sheet(meta, data) -> dict|None печатает один лист на принтере meta['printer'] (бросает исключение при сбое)."""
        self.name = name or socket.gethostname()
        self.id = node_id or uuid.uuid4().hex[:12]
        self.handlers = dict(handlers or {})
        self.print_sheet = print_sheet
        self.port, self.udp_port, self.host, self.broadcast = port, udp_port, host, broadcast
        self.on_event = on_event
        self.peers_paired = peers_paired if peers_paired is not None else {}
        self.found = {}                   # неспаренные найденные: id -> {name, addr, port, seen}
        self.sessions = {}                # peer_id -> Session
        self.peer_state = {}              # peer_id -> {printer: state}
        self.net_enabled = True           # общий выключатель приёма печати
        self.shared = None                # None = все принтеры; иначе множество имён
        self.max_sheets = max_sheets
        self.jobs = {}                    # job_id -> {from, printer, total, got, ts}
        self.sheets = {}                  # (job_id, sheet_id) -> {"state","error","from"}
        self.outbox = {}                  # peer_id -> deque чата
        self.inbox = []
        self._pairing = None              # (code, expires)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._srv = None
        self._queues = {}
        self._connecting = set()
        self._job_waiters = {}
        self._my_state = {}

    # --- служебное ---
    def _emit(self, kind, **info):
        if self.on_event:
            try:
                self.on_event(kind, info)
            except Exception:
                pass

    def _pool(self, fn, *a):
        threading.Thread(target=fn, args=a, daemon=True).start()

    def to_state(self):
        return {"id": self.id, "name": self.name, "paired": self.peers_paired}

    def _pairing_code(self):
        p = self._pairing
        return p[0] if p and p[1] > time.time() else None

    def open_pairing(self, code=None, ttl=300):
        """Открыть спаривание на ttl секунд; возвращает код для ввода на другом ПК."""
        code = code or new_code()
        self._pairing = (code, time.time() + ttl)
        return code

    def close_pairing(self):
        self._pairing = None

    # --- сервер ---
    def start(self):
        self._srv = socket.socket()
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((self.host, self.port))
        self.port = self._srv.getsockname()[1]
        self._srv.listen(16)
        self._srv.settimeout(0.3)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._reconnect_loop, daemon=True).start()
        return self

    def stop(self):
        self._stop.set()
        for s in list(self.sessions.values()):
            s.close()
        if self._srv:
            self._srv.close()

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                s, addr = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            if len(self.sessions) >= MAX_SESSIONS:
                s.close()
                continue
            self._pool(self._serve, s, addr)

    def _serve(self, s, addr):
        s.settimeout(DEAD_AFTER * 2)       # любой таймаут = обрыв связи, продолжать чтение кадра нельзя
        ch = Channel(s)
        try:
            pid, pname, pkey, mode = _server_handshake(ch, self)
        except (NetError, OSError, ValueError, KeyError):
            s.close()
            return
        if mode == "pair":
            self.peers_paired[pid] = {"name": pname, "key": pkey, "addr": addr[0], "port": self.found.get(pid, {}).get("port", PORT_TCP)}
            self._emit("paired", id=pid, name=pname, addr=addr[0])
        else:
            self.peers_paired[pid]["addr"] = addr[0]
        self._register(Session(self, ch, pid, pname, initiator_id=pid))

    def _register(self, sess):
        with self._lock:
            old = self.sessions.get(sess.peer_id)
            if old and old.alive:
                # при встречных подключениях остаётся то, что начал узел с меньшим id
                keep_new = sess.initiator_id == min(self.id, sess.peer_id)
                if not keep_new:
                    sess.close()
                    return
                self.sessions.pop(sess.peer_id, None)
                old.close()
            self.sessions[sess.peer_id] = sess
        sess.start()
        self._emit("presence", id=sess.peer_id, name=sess.peer_name, online=True)
        self._pool(self._flush_outbox, sess.peer_id)
        self._pool(self._send_all_state, sess)

    def _session_closed(self, sess):
        with self._lock:
            if self.sessions.get(sess.peer_id) is sess:
                del self.sessions[sess.peer_id]
                gone = True
            else:
                gone = False
        if gone:
            self.peer_state.pop(sess.peer_id, None)
            self._emit("presence", id=sess.peer_id, name=sess.peer_name, online=False)

    # --- клиент ---
    def pair(self, addr, code, port=PORT_TCP):
        """Спарить этот ПК с узлом по коду сети, показанному на нём."""
        s = socket.create_connection((addr, port), timeout=10)
        s.settimeout(DEAD_AFTER * 2)
        ch = Channel(s)
        try:
            pid, pname, pkey = _client_handshake(ch, self, code=code)
        except Exception:
            s.close()
            raise
        self.peers_paired[pid] = {"name": pname, "key": pkey, "addr": addr, "port": port}
        self._emit("paired", id=pid, name=pname, addr=addr)
        self._register(Session(self, ch, pid, pname, initiator_id=self.id))
        return pid

    def forget(self, peer_id):
        """Забыть ПК: ключ удаляется, соединение закрывается (на другой стороне нужно сделать то же)."""
        self.peers_paired.pop(peer_id, None)
        s = self.sessions.get(peer_id)
        if s:
            s.close()

    def _connect(self, pid):
        p = self.peers_paired.get(pid)
        if not p:
            return
        try:
            s = socket.create_connection((p["addr"], p.get("port", PORT_TCP)), timeout=5)
            s.settimeout(DEAD_AFTER * 2)
            ch = Channel(s)
            try:
                _client_handshake(ch, self, peer_key=p["key"])
            except Exception:
                s.close()
                raise
            self._register(Session(self, ch, pid, p.get("name", ""), initiator_id=self.id))
        except (OSError, NetError, ValueError, KeyError):
            pass
        finally:
            self._connecting.discard(pid)

    def _reconnect_loop(self):
        while not self._stop.is_set():
            for pid in list(self.peers_paired):
                if pid not in self.sessions and pid not in self._connecting:
                    self._connecting.add(pid)
                    self._pool(self._connect, pid)
            self._stop.wait(3.0)

    def online(self, peer_id):
        s = self.sessions.get(peer_id)
        return bool(s and s.alive)

    # --- обнаружение ---
    def announce(self, addr=None):
        body = json.dumps({"id": self.id, "name": self.name, "port": self.port, "proto": PROTO})
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(body.encode(), (addr or self.broadcast, self.udp_port))
        finally:
            s.close()

    def listen_discovery(self):
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        u.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        u.bind((self.host, self.udp_port))
        u.settimeout(0.3)
        threading.Thread(target=self._disc_loop, args=(u,), daemon=True).start()

    def _disc_loop(self, u):
        while not self._stop.is_set():
            try:
                pkt, addr = u.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                d = json.loads(pkt.decode())
                if d["id"] == self.id:
                    continue
                new = d["id"] not in self.found
                self.found[d["id"]] = {"name": str(d["name"])[:64], "addr": addr[0], "port": int(d["port"]), "seen": time.time()}
                if d["id"] in self.peers_paired:
                    self.peers_paired[d["id"]]["addr"] = addr[0]
                    self.peers_paired[d["id"]]["port"] = int(d["port"])
                if new:
                    self._emit("peer_found", id=d["id"], name=d["name"], addr=addr[0])
            except (ValueError, KeyError, TypeError):
                continue
        u.close()

    # --- запросы и события от пира ---
    def _dispatch(self, sess, cmd, meta, data):
        if cmd == "submit":
            return self._submit(sess, meta, data), b""
        if cmd == "job_status":
            st = self.sheets.get((meta.get("job_id"), meta.get("sheet_id")))
            return ({"state": st["state"], "error": st.get("error")} if st else {"state": "unknown"}), b""
        if cmd == "chat":
            msg = {"from": sess.peer_id, "name": sess.peer_name, "user": str(meta.get("user", ""))[:64],
                   "text": str(meta.get("text", ""))[:4000], "id": str(meta.get("id", "")), "ts": time.time(),
                   "channel": str(meta.get("channel", "all"))[:32]}
            if not any(m["id"] == msg["id"] and m["from"] == msg["from"] for m in self.inbox):
                self.inbox.append(msg)
                self._emit("chat", **msg)
            return {"delivered": True}, b""
        fn = self.handlers.get(cmd)
        if not fn:
            raise KeyError(f"неизвестная команда: {cmd}")
        r = fn(meta, data, sess.peer_id)
        if isinstance(r, tuple):
            return r[0] or {}, r[1]
        return r or {}, b""

    def _on_evt(self, sess, name, meta, data):
        if name == "printer_state":
            self.peer_state.setdefault(sess.peer_id, {})[meta.get("printer", "")] = meta
        elif name == "job":
            k = (meta.get("job_id"), meta.get("sheet_id"))
            w = self._job_waiters.get(k)
            if w:
                w[1].update(meta)
                w[0].set()
        self._emit("event:" + str(name), peer=sess.peer_id, **meta)

    # --- исполнитель: приём листов ---
    def _submit(self, sess, meta, data):
        if not self.net_enabled:
            raise PermissionError("приём печати по сети выключен")
        printer, job_id, sheet_id = meta.get("printer"), meta.get("job_id"), meta.get("sheet_id")
        if not (printer and job_id and sheet_id):
            raise ValueError("нужны printer, job_id, sheet_id")
        if self.shared is not None and printer not in self.shared:
            raise PermissionError("принтер недоступен по сети")
        if not self.print_sheet:
            raise RuntimeError("печать не подключена")
        key = (job_id, sheet_id)
        with self._lock:
            if key in self.sheets:                          # повтор: не печатать второй раз
                return {"state": self.sheets[key]["state"], "duplicate": True}
            total = int(meta.get("total", 1))
            if total > self.max_sheets:
                raise ValueError(f"в задании больше {self.max_sheets} листов")
            job = self.jobs.get(job_id)
            if not job:
                job = self.jobs[job_id] = {"from": sess.peer_id, "printer": printer, "total": total, "got": 0, "ts": time.time()}
                self._emit("job_received", peer=sess.peer_id, name=sess.peer_name, printer=printer, sheets=total, job_id=job_id)
            job["got"] += 1
            self.sheets[key] = {"state": "queued", "from": sess.peer_id}
            q = self._queues.get(printer) or self._queues.setdefault(printer, _PrinterQueue(self, printer))
        q.put((key, sess.peer_id, dict(meta), data))
        return {"state": "queued"}

    def _run_sheet(self, key, peer_id, meta, data):
        self._set_state(key, peer_id, "printing")
        try:
            self.print_sheet(meta, data)
            self._set_state(key, peer_id, "spooled")
        except Exception as e:
            self._set_state(key, peer_id, "failed", str(e))

    def _set_state(self, key, peer_id, state, error=None):
        self.sheets[key].update(state=state, error=error)
        s = self.sessions.get(peer_id)
        if s:
            try:
                s.event("job", {"job_id": key[0], "sheet_id": key[1], "state": state, "error": error})
            except (OSError, NetError):
                pass
        self._emit("sheet", peer=peer_id, job_id=key[0], sheet_id=key[1], state=state, error=error)

    # --- состояние принтера ---
    def publish_state(self, printer, level, text="", **extra):
        """level: ok|warning|attention|error|offline. Рассылается всем подключённым ПК."""
        meta = {"printer": printer, "level": level, "text": text, "ts": time.time(), **extra}
        self._my_state[printer] = meta
        for s in list(self.sessions.values()):
            try:
                s.event("printer_state", meta)
            except (OSError, NetError):
                pass

    def _send_all_state(self, sess):
        for meta in list(self._my_state.values()):
            try:
                sess.event("printer_state", meta)
            except (OSError, NetError):
                return

    # --- клиент: печать листа на удалённом принтере ---
    def send_sheet(self, peer_id, printer, job_id, sheet_id, data, total=1, meta=None, timeout=300.0):
        """Блокирует, пока лист не передан в спулер удалённого ПК. NetError — лист точно не принят или не напечатан;
        OutcomeUnknown — связь потеряна, судьба листа неизвестна (не перекидывать на другой принтер)."""
        s = self.sessions.get(peer_id)
        if not s or not s.alive:
            raise NetError("ПК не в сети")
        key = (job_id, sheet_id)
        ev, box = threading.Event(), {}
        self._job_waiters[key] = (ev, box)
        m = dict(meta or {}, printer=printer, job_id=job_id, sheet_id=sheet_id, total=total)
        try:
            try:
                h, _ = s.call("submit", m, data, timeout=120)
            except NetError:
                return self._resolve(peer_id, key, timeout)     # запрос мог дойти: выяснить
            if not h.get("ok"):
                raise NetError(h.get("error", "ПК не принял лист"))
            state, end = h.get("state"), time.time() + timeout
            while state not in ("spooled", "failed"):
                if not s.alive:
                    return self._resolve(peer_id, key, timeout)
                if time.time() > end:
                    raise OutcomeUnknown("нет ответа о печати листа")
                if ev.wait(0.5):
                    ev.clear()
                    state = box.get("state")
            if state == "failed":
                raise NetError(box.get("error") or "принтер не напечатал лист")
        finally:
            self._job_waiters.pop(key, None)

    def _resolve(self, peer_id, key, timeout):
        """После обрыва: дождаться переподключения и спросить судьбу листа."""
        end = time.time() + min(timeout, 60)
        while time.time() < end:
            time.sleep(1.0)
            s = self.sessions.get(peer_id)
            if not (s and s.alive):
                continue
            try:
                h, _ = s.call("job_status", {"job_id": key[0], "sheet_id": key[1]}, timeout=10)
            except NetError:
                continue
            st = h.get("state")
            if st == "unknown":
                raise NetError("лист не принят")
            if st == "spooled":
                return
            if st == "failed":
                raise NetError(h.get("error") or "принтер не напечатал лист")
        raise OutcomeUnknown("не удалось выяснить судьбу листа")

    def remote_send(self, peer_id, job_id=None):
        """send(printer, sheet) для multi_print.MultiRun; sheet — bytes готового листа. Печатает на принтере ПК peer_id."""
        job = job_id or uuid.uuid4().hex[:10]

        def send(printer, sheet):
            self.send_sheet(peer_id, printer, job, uuid.uuid4().hex[:10], sheet)
        return send

    # --- чат ---
    def chat_send(self, peer_id, text, user="", channel="all"):
        """Отправить сообщение; если ПК офлайн, оно уйдёт при подключении."""
        m = {"id": uuid.uuid4().hex[:12], "text": text, "user": user or self.name, "channel": channel, "ts": time.time()}
        self.outbox.setdefault(peer_id, deque(maxlen=500)).append(m)
        self._pool(self._flush_outbox, peer_id)
        return m["id"]

    def _flush_outbox(self, peer_id):
        q = self.outbox.get(peer_id)
        s = self.sessions.get(peer_id)
        while q and s and s.alive:
            m = q[0]
            if time.time() - m["ts"] > 7 * 86400:
                q.popleft()
                continue
            try:
                s.call("chat", m, timeout=10)
            except NetError:
                return
            if q and q[0] is m:
                q.popleft()
