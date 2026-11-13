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
import ipaddress
import json
import os
import select
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
MAX_PREAUTH = 40               # соединений в стадии проверки одновременно
MAX_PREAUTH_IP = 8
PREAUTH_TIMEOUT = 20.0
PREQ_PER_MIN = 6               # запросов на подключение в минуту (всего)
DEFAULT_MAX_SHEETS = 500       # потолок листов за одно задание


# 2048-битная группа Диффи-Хеллмана (RFC 3526, группа 14): p = 2^2048 - 2^1984 - 1 + 2^64 * ([2^1918 * pi] + 124476), g = 2.
# Простота p и (p-1)/2 проверена тестом, значение вычисляется заново из числа pi.
DH_P = int("ffffffffffffffffc90fdaa22168c234c4c6628b80dc1cd129024e088a67cc74020bbea63b139b22514a08798e3404ddef9519b3cd3a431b302b0a6df25f14374fe1356d6d51c245e485b576625e7ec6f44c42e9a637ed6b0bff5cb6f406b7edee386bfb5a899fa5ae9f24117c4b1fe649286651ece45b3dc2007cb8a163bf0598da48361c55d39a69163fa8fd24cf5f83655d23dca3ad961c62f356208552bb9ed529077096966d670c354e4abc9804f1746c08ca18217c32905e462e36ce3be39e772c180e86039b2783a2ec07a28fb5c55df06f4c52c9de2bcbf6955817183995497cea956ae515d2261898fa051015728e5a8aacaa68ffffffffffffffff", 16)
DH_G = 2
PAIR_WAIT = 150.0                  # сколько ждём, пока человек на другом ПК введёт код
PAIR_TRIES = 3                     # неверных кодов за один запрос; потом запрос отклоняется
MAX_PAIR_REQUESTS = 5              # одновременно ожидающих запросов на подключение
MAX_FOUND = 64                     # найденных ПК в списке: чужие объявления в сети не раздувают память
PAIR_DENY_PAUSE = 60.0             # после отказа (или неверных кодов) запросы с того же адреса/ПК не принимаются столько секунд
FOUND_TTL = 20.0                   # найденный ПК исчезает из списка, если не объявлялся столько секунд
ANNOUNCE_EVERY = 4.0


class _PairEnd(Exception):
    pass


class NetError(Exception):
    pass


class AuthError(NetError):
    pass


class OutcomeUnknown(NetError):
    """Связь оборвалась после приёма листа: неизвестно, напечатан ли он. Перекидывать на другой принтер нельзя."""


_BIDI = set("\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")      # скрытая смена направления текста (подделка расширения)
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} | {"LPT%d" % i for i in range(1, 10)}


def safe_filename(name):
    """Имя файла без путей и запрещённых символов (присланное имя никогда не используется как путь)."""
    name = os.path.basename(str(name).replace("\\", "/")).strip().strip(".")
    name = "".join("_" if c in '<>:"/\\|?*\x00' or ord(c) < 32 or c in _BIDI else c for c in name).rstrip(" .")
    if name.split(".")[0].upper() in _RESERVED:                    # CON, NUL, COM1...: Windows не даёт создать такой файл
        name = "_" + name
    return (name or "файл")[:120]


def unique_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    for i in range(1, 1000):
        p = "%s (%d)%s" % (base, i, ext)
        if not os.path.exists(p):
            return p
    return "%s (%s)%s" % (base, uuid.uuid4().hex[:6], ext)


def dh_keypair(g=DH_G):
    priv = int.from_bytes(os.urandom(32), "big") | (1 << 255)
    return priv, pow(g, priv, DH_P)


def pake_gen(code):
    """Генератор группы, выведенный из кода (SPEKE): g = H(код)^2 mod p. Без верного кода посторонний не может проверить
    догадку по перехваченному обмену, остаётся только онлайн-попытка, которую ограничивают три ошибки."""
    raw = b"".join(hashlib.sha256(b"kt-pake|%d|%s" % (i, code.encode())).digest() for i in range(9))
    h = int.from_bytes(raw, "big") % DH_P
    return pow(h, 2, DH_P)


def dh_secret(priv, peer_pub):
    if not (2 <= peer_pub <= DH_P - 2):
        raise AuthError("неверное значение обмена ключами")
    return pow(peer_pub, priv, DH_P).to_bytes(256, "big")


def new_pin():
    """Короткий код для человека: 6 цифр (на экране показывается как «123 456»)."""
    return "%06d" % (int.from_bytes(os.urandom(4), "big") % 1000000)


def is_public_addr(addr):
    """True для публичного IP-адреса: кадры подписаны, но не шифруются, а Tailscale и домашняя сеть шифруют или закрыты.
    Имя ПК вместо адреса (Tailscale MagicDNS) и частные адреса (192.168/10/172.16, 100.64/10, link-local) дают False."""
    try:
        return ipaddress.ip_address(str(addr).strip().strip("[]")).is_global
    except ValueError:
        return False


def local_addrs():
    """IPv4-адреса этого ПК (кроме 127.x)."""
    out = []
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127.") and ip not in out:
                out.append(ip)
    except OSError:
        pass
    return out


def broadcast_targets():
    """Адреса рассылки: «x.y.z.255» для каждой сети этого ПК (маска /24 как самый частый случай) и общая 255.255.255.255."""
    out = ["255.255.255.255"]
    for ip in local_addrs():
        b = ip.rsplit(".", 1)[0] + ".255"
        if b not in out:
            out.append(b)
    return out


def tailscale_peers():
    """Онлайн-узлы Tailscale: [(имя, ip)]. Нет tailscale или он выключен: пустой список. Запускается только по полному пути."""
    import shutil
    import subprocess
    if os.name == "nt":
        cands = [os.path.join(os.environ.get(v, ""), "Tailscale", "tailscale.exe") for v in ("ProgramFiles", "ProgramFiles(x86)")]
        cands = [c for c in cands if os.path.isfile(c)]
    else:
        w = shutil.which("tailscale")
        cands = [w] if w else []
    for c in cands:
        try:
            out = subprocess.run([c, "status", "--json"], capture_output=True, timeout=4,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            continue
        if out.returncode != 0:
            continue
        try:
            d = json.loads(out.stdout.decode("utf-8", "replace"))
        except ValueError:
            continue
        res = []
        for p in (d.get("Peer") or {}).values():
            ips = [x for x in p.get("TailscaleIPs", []) if "." in x]
            if p.get("Online") and ips:
                res.append((p.get("HostName") or ips[0], ips[0]))
        return res
    return []


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
        self.last_io = time.time()          # время последнего принятого куска: длинный кадр (файл) не считается обрывом
        self._wlock = threading.Lock()

    def _rx(self, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(min(n - len(buf), 1 << 20))
            if not chunk:
                raise NetError("соединение закрыто")
            buf += chunk
            self.last_io = time.time()
        return bytes(buf)

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
        hl = struct.unpack(">I", self._rx(4))[0]
        if hl > limit_h:
            raise NetError("заголовок слишком большой")
        h = self._rx(hl)
        dl = struct.unpack(">I", self._rx(4))[0]
        if dl > (MAX_DATA if self.key else 0):
            raise NetError("данные слишком большие")
        data = self._rx(dl)
        if self.key:
            tag = self._rx(32)
            body = struct.pack(">I", hl) + h + struct.pack(">I", dl) + data
            if not hmac.compare_digest(tag, _mac(self.key, struct.pack(">Q", self.seq_in), body)):
                raise AuthError("неверная подпись кадра")
        self.seq_in += 1
        return json.loads(h.decode()), data


# ---------- рукопожатие ----------
def _client_handshake(ch, node, peer_key=None, code=None, peer_id=None):
    """peer_key — ключ пары (обычное подключение, peer_id — кого ждём) или code — код сети (спаривание)."""
    secret = peer_key or code
    mode = "auth" if peer_key else "pair"
    ids = (node.id, peer_id or "") if mode == "auth" else ("", "")      # id и роли в подписи: отражённое рукопожатие не проходит
    cn = os.urandom(16).hex()
    ch.send({"t": "hello", "proto": PROTO, "mode": mode, "id": node.id, "name": node.name, "nonce": cn})
    h, _ = ch.recv()
    if h.get("t") != "challenge":
        raise AuthError(h.get("error", "отказ узла"))
    sn = h["nonce"]
    if not hmac.compare_digest(bytes.fromhex(h["proof"]), _mac(secret, "srv", cn, sn, *ids)):
        raise AuthError("узел не знает ключ")
    ch.send({"t": "auth", "proof": _mac(secret, "cli", cn, sn, *ids).hex()})
    ch.key = _mac(secret, "sess", cn, sn, *ids)
    h, _ = ch.recv()
    if h.get("t") != "ok":
        raise AuthError(h.get("error", "отказ"))
    if mode == "auth" and peer_id and h.get("id") != peer_id:
        raise AuthError("ответил другой ПК")
    pair_key = _mac(secret, "pair", cn, sn).hex() if mode == "pair" else peer_key
    return h["id"], h.get("name", ""), pair_key


def _server_handshake(ch, node, h=None):
    if h is None:
        h, _ = ch.recv()
    if h.get("t") != "hello" or h.get("proto") != PROTO:
        ch.send({"t": "error", "error": "неподдерживаемый протокол"})
        raise AuthError("неподдерживаемый протокол")
    peer_id, mode, cn, sn = str(h["id"]), h.get("mode"), str(h["nonce"]), os.urandom(16).hex()
    if peer_id == node.id:
        ch.send({"t": "error", "error": "тот же ПК"})
        raise AuthError("соединение с самим собой")
    ids = ("", "")
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
        ids = (peer_id, node.id)
    ch.send({"t": "challenge", "nonce": sn, "proof": _mac(secret, "srv", cn, sn, *ids).hex()})
    a, _ = ch.recv()
    if a.get("t") != "auth" or not hmac.compare_digest(bytes.fromhex(a.get("proof", "")), _mac(secret, "cli", cn, sn, *ids)):
        ch.send({"t": "error", "error": "неверный ключ"})
        raise AuthError("неверный ключ")
    ch.key = _mac(secret, "sess", cn, sn, *ids)
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
            if time.time() - max(self.last_rx, self.ch.last_io) > DEAD_AFTER:
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
                 print_sheet=None, app_version=""):
        """peers_paired: {id: {"name","key","addr","port"}} (хранит программа; to_state()/from_state()).
        print_sheet(meta, data) -> dict|None печатает один лист на принтере meta['printer'] (бросает исключение при сбое)."""
        self.name = name or socket.gethostname()
        self.id = node_id or uuid.uuid4().hex[:12]
        self.handlers = dict(handlers or {})
        self.print_sheet = print_sheet
        self.app_version = app_version
        self.peer_info = {}               # peer_id -> {"version"}
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
        self._preauth = {}
        self._preq_times = []
        self._pair_pause = {}             # адрес / "id:<ПК>" -> до какого времени запросы не принимаются (после отказа)
        self._flushing = set()
        self._seen_ids = set()
        self._pair_reqs = {}              # ожидающие запросы на подключение с коротким кодом
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._srv = None
        self._queues = {}
        self._connecting = set()
        self._job_waiters = {}
        self._my_state = {}
        self._base_state = {}
        self.file_dir = None              # куда складывать присланные файлы (задаёт программа)

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
        if os.name == "nt":                                    # на Windows SO_REUSEADDR даёт двум копиям слушать один порт
            self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
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
            if len(self.sessions) >= MAX_SESSIONS or not self._reserve_preauth(addr[0]):
                s.close()                                       # поток под такое соединение не создаём
                continue
            self._pool(self._serve, s, addr)

    def _reserve_preauth(self, ip):
        """Лимит соединений, ещё не прошедших проверку (по всему узлу и с одного адреса); слот занимается до создания потока."""
        with self._lock:
            n_ip = self._preauth.get(ip, 0)
            if sum(self._preauth.values()) >= MAX_PREAUTH or n_ip >= MAX_PREAUTH_IP:
                return False
            self._preauth[ip] = n_ip + 1
            return True

    def _serve(self, s, addr):
        try:
            self._serve_inner(s, addr)
        finally:
            with self._lock:
                left = self._preauth.get(addr[0], 1) - 1
                if left > 0:
                    self._preauth[addr[0]] = left
                else:
                    self._preauth.pop(addr[0], None)

    def _serve_inner(self, s, addr):
        s.settimeout(PREAUTH_TIMEOUT)       # любой таймаут = обрыв связи, продолжать чтение кадра нельзя
        ch = Channel(s)
        try:
            h, _ = ch.recv()
            if h.get("t") == "hello" and h.get("mode") == "probe":          # «есть ли здесь программа»: без секретов
                ch.send({"t": "info", "id": self.id, "name": self.name, "port": self.port, "proto": PROTO})
                s.close()
                return
            if h.get("t") == "hello" and h.get("mode") == "preq":           # запрос на подключение с коротким кодом
                self._serve_pair_request(ch, h, addr)
                s.close()
                return
            pid, pname, pkey, mode = _server_handshake(ch, self, h)
        except (NetError, OSError, ValueError, KeyError, AttributeError, TypeError):
            s.close()
            return
        s.settimeout(DEAD_AFTER * 2)
        if mode == "pair":
            self._store_pair(pid, pname, pkey, addr[0], self.found.get(pid, {}).get("port", PORT_TCP))
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
        self._pool(self._send_about, sess)

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
        self._store_pair(pid, pname, pkey, addr, port)
        self._emit("paired", id=pid, name=pname, addr=addr)
        self._register(Session(self, ch, pid, pname, initiator_id=self.id))
        return pid

    def _store_pair(self, pid, name, key, addr, port):
        """Запомнить пару; повторное спаривание не сбрасывает имя, скрытие и запрет печати."""
        old = self.peers_paired.get(pid) or {}
        new = {"name": name, "key": key, "addr": addr, "port": int(port)}
        for k in ("alias", "hidden", "trusted"):
            if k in old:
                new[k] = old[k]
        self.peers_paired[pid] = new

    def forget(self, peer_id):
        """Забыть ПК: ключ удаляется, соединение закрывается (на другой стороне нужно сделать то же)."""
        self.peers_paired.pop(peer_id, None)
        s = self.sessions.get(peer_id)
        if s:
            s.close()

    def _connect(self, pid):
        p = self.peers_paired.get(pid)
        if not p:
            self._connecting.discard(pid)
            return
        addrs = [(p["addr"], p.get("port", PORT_TCP))]
        f = self.found.get(pid)                               # адрес из UDP только кандидат: он станет основным лишь после успешной проверки ключа
        if f and time.time() - f["seen"] <= FOUND_TTL and (f["addr"], f["port"]) != addrs[0]:
            addrs.append((f["addr"], f["port"]))
        try:
            for addr, port in addrs:
                try:
                    s = socket.create_connection((addr, port), timeout=5)
                except OSError:
                    continue
                try:
                    s.settimeout(DEAD_AFTER * 2)
                    ch = Channel(s)
                    try:
                        _client_handshake(ch, self, peer_key=p["key"], peer_id=pid)
                    except Exception:
                        s.close()
                        continue
                    if pid in self.peers_paired:
                        self.peers_paired[pid]["addr"], self.peers_paired[pid]["port"] = addr, port
                    self._register(Session(self, ch, pid, p.get("name", ""), initiator_id=self.id))
                    return
                except (OSError, NetError, ValueError, KeyError):
                    continue
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
        """Одно объявление «я здесь» (id, имя, порт; без секретов). Без addr: всем сетям этого ПК."""
        body = json.dumps({"id": self.id, "name": self.name, "port": self.port, "proto": PROTO}).encode()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            for t in ([addr] if addr else (broadcast_targets() if self.broadcast == "255.255.255.255" else [self.broadcast])):
                try:
                    s.sendto(body, (t, self.udp_port))
                except OSError:
                    continue
        finally:
            s.close()

    def listen_discovery(self):
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        u.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        u.bind((self.host, self.udp_port))
        u.settimeout(0.3)
        threading.Thread(target=self._disc_loop, args=(u,), daemon=True).start()

    def start_discovery(self, tailscale=True):
        """Слушать объявления других ПК и сами объявляться каждые несколько секунд; через Tailscale опрашивать онлайн-узлы."""
        try:
            self.listen_discovery()
        except OSError:
            pass                                   # порт занят другой копией: слушать не получится, но объявляться можно
        threading.Thread(target=self._announce_loop, args=(tailscale,), daemon=True).start()

    def _announce_loop(self, tailscale):
        last_ts = 0.0
        while not self._stop.is_set():
            try:
                self.announce()
            except OSError:
                pass
            if tailscale and time.time() - last_ts > 15:
                last_ts = time.time()
                try:
                    self.scan_tailscale()
                except Exception:
                    pass
            self._stop.wait(ANNOUNCE_EVERY)

    def _note_found(self, pid, name, addr, port, via="lan"):
        if pid == self.id:
            return
        if pid not in self.found and len(self.found) >= MAX_FOUND:
            now = time.time()
            for k, v in list(self.found.items()):
                if now - v["seen"] > FOUND_TTL:
                    self.found.pop(k, None)
            if len(self.found) >= MAX_FOUND:
                return
        new = pid not in self.found or time.time() - self.found[pid]["seen"] > FOUND_TTL
        self.found[pid] = {"name": str(name)[:64], "addr": addr, "port": int(port), "seen": time.time(), "via": via}
        if new:
            self._emit("peer_found", id=pid, name=name, addr=addr)

    def found_list(self):
        """Найденные ПК, объявлявшиеся недавно: [{id, name, addr, port, via, paired}]."""
        now = time.time()
        out = []
        for pid, v in list(self.found.items()):
            if now - v["seen"] > FOUND_TTL:
                self.found.pop(pid, None)
                continue
            out.append(dict(v, id=pid, paired=pid in self.peers_paired))
        return out

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
                self._note_found(d["id"], d["name"], addr[0], d["port"])
            except (ValueError, KeyError, TypeError):
                continue
        u.close()

    def add_peer(self, addr, port=PORT_TCP, peer_id=None):
        """Ручной адрес, если рассылка не проходит (разные подсети, VPN)."""
        with self._lock:
            if len(self.found) >= MAX_FOUND and (peer_id or f"{addr}:{port}") not in self.found:
                return
            self.found[peer_id or f"{addr}:{port}"] = {"name": addr, "addr": addr, "port": port, "seen": time.time(), "via": "manual"}

    def probe(self, addr, port=PORT_TCP, timeout=1.5):
        """Есть ли на адресе программа: {id, name, port} или None. Секреты не передаются."""
        try:
            s = socket.create_connection((addr, port), timeout=timeout)
        except OSError:
            return None
        try:
            s.settimeout(timeout)
            ch = Channel(s)
            ch.send({"t": "hello", "proto": PROTO, "mode": "probe", "id": self.id, "name": self.name, "nonce": ""})
            h, _ = ch.recv()
            return h if h.get("t") == "info" else None
        except (NetError, OSError, ValueError):
            return None
        finally:
            s.close()

    def scan_tailscale(self):
        """Tailscale не пропускает рассылку: берём онлайн-узлы из `tailscale status --json` и проверяем на каждом порт программы."""
        found = []
        for host, ip in tailscale_peers():
            info = self.probe(ip, PORT_TCP, timeout=1.0)
            if info and info.get("id"):
                self._note_found(info["id"], info.get("name") or host, ip, info.get("port", PORT_TCP), via="tailscale")
                found.append(info["id"])
        return found

    # --- подключение по запросу с коротким кодом ---
    def _serve_pair_request(self, ch, h, addr):
        """Принимающая сторона: показывает запрос человеку; тот вводит 6 цифр с экрана запрашивающего ПК.
        Пароль-обмен (SPEKE): свою часть обмена мы считаем только из введённого кода и отправляем после ввода, поэтому по
        перехваченному обмену код офлайн не подобрать, а каждая догадка стоит одной онлайн-попытки."""
        peer_id, name, cn = str(h["id"]), str(h.get("name", ""))[:64], str(h["nonce"])
        a_pub = int(h["dh"], 16)
        if not (2 <= a_pub <= DH_P - 2) or peer_id == self.id:
            ch.send({"t": "error", "error": "неверный запрос"})
            return
        now = time.time()
        with self._lock:
            self._preq_times = [t for t in self._preq_times if now - t < 60]
            self._pair_pause = {k: t for k, t in self._pair_pause.items() if t > now}
            if addr[0] in self._pair_pause or "id:" + peer_id in self._pair_pause:
                ch.send({"t": "error", "error": "подождите минуту после отказа"})
                return
            if len(self._pair_reqs) >= MAX_PAIR_REQUESTS or len(self._preq_times) >= PREQ_PER_MIN or \
                    any(r["addr"] == addr[0] or r["peer_id"] == peer_id for r in self._pair_reqs.values()):
                ch.send({"t": "error", "error": "слишком много запросов"})
                return
            self._preq_times.append(now)
            rid = uuid.uuid4().hex[:8]
            req = {"id": rid, "peer_id": peer_id, "name": name, "addr": addr[0], "event": threading.Event(), "code": None, "deny": False}
            self._pair_reqs[rid] = req
        ch.sock.settimeout(PAIR_WAIT + 30)
        result = {"ok": False, "reason": "время ожидания вышло"}
        try:
            ch.send({"t": "preq_ok", "id": self.id, "name": self.name})
            self._emit("pair_request", req_id=rid, peer_id=peer_id, name=name, addr=addr[0])
            deadline = time.time() + PAIR_WAIT
            while True:
                while not req["event"].is_set():
                    if time.time() > deadline or self._stop.is_set():
                        raise _PairEnd("время ожидания вышло")
                    r, _, _ = select.select([ch.sock], [], [], 0.4)
                    if r:                                                  # запрашивающий закрыл связь или отменил
                        raise _PairEnd("запрос отменён на другом ПК")
                    if req["deny"]:
                        ch.send({"t": "cancel"})
                        raise _PairEnd("вы отклонили запрос")
                req["event"].clear()
                if req["deny"]:
                    ch.send({"t": "cancel"})
                    raise _PairEnd("вы отклонили запрос")
                code = req["code"]
                priv, pub = dh_keypair(pake_gen(code))
                key_material = dh_secret(priv, a_pub) + code.encode()
                sn = os.urandom(16).hex()
                transcript = "%x|%x|%s|%s" % (a_pub, pub, cn, sn)
                ch.send({"t": "bpub", "dh": "%x" % pub, "nonce": sn, "proof": _mac(key_material, "B", transcript).hex()})
                r, _ = ch.recv()
                if r.get("t") == "ok":
                    if not hmac.compare_digest(bytes.fromhex(r.get("proof", "")), _mac(key_material, "A", transcript)):
                        raise _PairEnd("проверка кода не прошла")
                    self._store_pair(peer_id, name, _mac(key_material, "pairkey", transcript).hex(), addr[0], int(h.get("port", PORT_TCP)))
                    result = {"ok": True}
                    ch.send({"t": "done"})                                 # ключ уже сохранён: теперь запрашивающий может подключаться
                    self._emit("paired", id=peer_id, name=name, addr=addr[0])
                    return
                if r.get("t") == "retry":
                    self._emit("pair_result", req_id=rid, ok=False, retry=True, left=r.get("left", 0), reason="неверный код")
                    continue
                raise _PairEnd(r.get("error", "отклонено"))
        except _PairEnd as e:
            result = {"ok": False, "reason": str(e)}
            if self._stop.is_set() or "время ожидания" in str(e) or "отменён" in str(e):
                pass
            else:                                                          # отказ или неверные коды: пауза, чтобы не засыпали запросами
                until = time.time() + PAIR_DENY_PAUSE
                with self._lock:
                    self._pair_pause[addr[0]] = self._pair_pause["id:" + peer_id] = until
        except (NetError, OSError, ValueError, KeyError, TypeError):
            result = {"ok": False, "reason": "связь прервана"}
        finally:
            self._pair_reqs.pop(rid, None)
            self._emit("pair_result", req_id=rid, retry=False, **result)

    def answer_pair(self, req_id, code):
        """Человек ввёл 6 цифр с экрана другого ПК."""
        req = self._pair_reqs.get(req_id)
        code = "".join(c for c in str(code) if c.isdigit())
        if not req or len(code) != 6:
            return False
        req["code"] = code
        req["event"].set()
        return True

    def deny_pair(self, req_id):
        req = self._pair_reqs.get(req_id)
        if req:
            req["deny"] = True
            req["event"].set()

    def pending_pair_requests(self):
        return [{k: r[k] for k in ("id", "peer_id", "name", "addr")} for r in self._pair_reqs.values()]

    def request_pair(self, addr, port=PORT_TCP, on_code=None, cancel=None):
        """Запрашивающая сторона. on_code(code) показывает 6 цифр на экране; блокирует, пока человек на том ПК не введёт код.
        Возвращает id спаренного ПК или бросает NetError (отклонено, время вышло, три неверных кода)."""
        s = socket.create_connection((addr, port), timeout=10)
        ch = Channel(s)
        s.settimeout(PAIR_WAIT + 30)
        try:
            code = new_pin()
            a, pub = dh_keypair(pake_gen(code))
            cn = os.urandom(16).hex()
            ch.send({"t": "hello", "proto": PROTO, "mode": "preq", "id": self.id, "name": self.name, "nonce": cn,
                     "dh": "%x" % pub, "port": self.port})
            r, _ = ch.recv()
            if r.get("t") != "preq_ok":
                raise NetError(r.get("error", "ПК не принял запрос"))
            pid, pname = str(r["id"]), str(r.get("name", ""))[:64]
            if pid == self.id:
                raise NetError("это тот же ПК")
            if on_code:
                on_code(code)
            tries, deadline = 0, time.time() + PAIR_WAIT
            while True:
                while True:
                    if cancel and cancel():
                        raise NetError("запрос отменён")
                    if time.time() > deadline:
                        raise NetError("время ожидания вышло")
                    r_, _, _ = select.select([s], [], [], 0.4)
                    if r_:
                        break
                r, _ = ch.recv()
                if r.get("t") == "cancel":
                    raise NetError("ПК отклонил запрос")
                if r.get("t") != "bpub":
                    raise NetError(r.get("error", "отказ"))
                b_pub, sn = int(r["dh"], 16), str(r["nonce"])
                key_material = dh_secret(a, b_pub) + code.encode()
                transcript = "%x|%x|%s|%s" % (pub, b_pub, cn, sn)
                if hmac.compare_digest(bytes.fromhex(r["proof"]), _mac(key_material, "B", transcript)):
                    ch.send({"t": "ok", "proof": _mac(key_material, "A", transcript).hex()})
                    d, _ = ch.recv()
                    if d.get("t") != "done":
                        raise NetError(d.get("error", "ПК не подтвердил подключение"))
                    break
                tries += 1
                if tries >= PAIR_TRIES:
                    ch.send({"t": "fail", "error": "слишком много неверных кодов"})
                    raise NetError("слишком много неверных кодов")
                ch.send({"t": "retry", "left": PAIR_TRIES - tries})
            self._store_pair(pid, pname, _mac(key_material, "pairkey", transcript).hex(), addr, port)
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise NetError("связь прервана: %s" % e)
        finally:
            s.close()
        self._emit("paired", id=pid, name=pname, addr=addr)
        self._pool(self._connect, pid)
        return pid

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
            with self._lock:
                fresh = (sess.peer_id, msg["id"]) not in self._seen_ids and not any(m["id"] == msg["id"] and m["from"] == msg["from"] for m in self.inbox)
                if fresh:
                    self._seen_ids.add((sess.peer_id, msg["id"]))
                    self.inbox.append(msg)
            if fresh:
                self._emit("chat", **msg)
            return {"delivered": True}, b""
        if cmd == "file":
            return self._receive_file(sess, meta, data), b""
        fn = self.handlers.get(cmd)
        if not fn:
            raise KeyError(f"неизвестная команда: {cmd}")
        r = fn(meta, data, sess.peer_id)
        if isinstance(r, tuple):
            return r[0] or {}, r[1]
        return r or {}, b""

    def _on_evt(self, sess, name, meta, data):
        if name == "about":
            self.peer_info[sess.peer_id] = {"version": str(meta.get("version", ""))[:32]}
        elif name == "printer_state":
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
        if not self.peers_paired.get(sess.peer_id, {}).get("trusted", True):
            raise PermissionError("этому ПК печать на вашем принтере не разрешена")
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
        q.put((key, sess.peer_id, dict(meta, **{"from": sess.peer_name}), data))
        return {"state": "queued"}

    def _run_sheet(self, key, peer_id, meta, data):
        printer = meta.get("printer", "")
        self.publish_state(printer, "printing", "печатает для " + str(meta.get("from", "")), _busy=True)
        try:
            self._run_sheet_inner(key, peer_id, meta, data)
        finally:
            q = self._queues.get(printer)
            if not q or q.depth() == 0:          # очередь опустела: вернуть последнее настоящее состояние принтера
                base = self._base_state.get(printer) or {"level": "ok", "text": ""}
                self.publish_state(printer, base["level"], base.get("text", ""))

    def _run_sheet_inner(self, key, peer_id, meta, data):
        self._set_state(key, peer_id, "printing")
        try:
            p = self.peers_paired.get(peer_id)
            if not self.net_enabled or not p or not p.get("trusted", True):          # запрет или «забыть ПК» действуют и на уже стоящие в очереди листы
                raise PermissionError("печать для этого ПК запрещена")
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
        if not extra.get("_busy") and level != "printing":
            self._base_state[printer] = meta
        self._my_state[printer] = meta
        for s in list(self.sessions.values()):
            try:
                s.event("printer_state", meta)
            except (OSError, NetError):
                pass

    def _send_about(self, sess):
        try:
            sess.event("about", {"version": self.app_version})
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
        try:
            self._send_sheet(peer_id, s, printer, job_id, sheet_id, data, total, meta, timeout)
        except NetError as e:
            self._emit("sent_sheet", peer=peer_id, job_id=job_id, sheet_id=sheet_id, total=total, printer=printer, ok=False, error=str(e))
            raise
        self._emit("sent_sheet", peer=peer_id, job_id=job_id, sheet_id=sheet_id, total=total, printer=printer, ok=True, error="")

    def _send_sheet(self, peer_id, s, printer, job_id, sheet_id, data, total, meta, timeout):
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

    # --- файлы ---
    def _receive_file(self, sess, meta, data):
        """Сохраняет присланный файл в file_dir/<ПК>/<дата>/ (никогда не открывает и не запускает) и сообщает окну."""
        if not self.file_dir:
            raise PermissionError("приём файлов не настроен")
        fid = str(meta.get("id", ""))
        with self._lock:
            if (sess.peer_id, fid) in self._seen_ids or any(m.get("id") == fid and m["from"] == sess.peer_id for m in self.inbox):
                return {"delivered": True, "duplicate": True}
            self._seen_ids.add((sess.peer_id, fid))
        name = safe_filename(meta.get("name", "файл"))
        folder = os.path.join(self.file_dir, safe_filename(sess.peer_name or sess.peer_id), time.strftime("%Y-%m-%d"))
        try:
            os.makedirs(folder, exist_ok=True)
            path = unique_path(os.path.join(folder, name))
            with open(path, "wb") as f:
                f.write(data)
        except OSError:
            self._seen_ids.discard((sess.peer_id, fid))
            raise
        msg = {"from": sess.peer_id, "name": sess.peer_name, "user": str(meta.get("user", ""))[:64], "text": str(meta.get("text", ""))[:4000],
               "id": fid, "ts": time.time(), "channel": str(meta.get("channel", "all"))[:32],
               "att": {"name": os.path.basename(path), "size": len(data), "path": path}}
        self.inbox.append(msg)
        self._emit("chat", **msg)
        return {"delivered": True}

    # --- чат ---
    def chat_send(self, peer_id, text, user="", channel="all", file=None, msg_id=None):
        """Отправить сообщение (file — путь к файлу-вложению); если ПК офлайн, оно уйдёт при подключении."""
        m = {"id": msg_id or uuid.uuid4().hex[:12], "text": text, "user": user or self.name, "channel": channel, "ts": time.time()}
        if file:
            m["file"] = file
        self.outbox.setdefault(peer_id, deque(maxlen=500)).append(m)
        self._pool(self._flush_outbox, peer_id)
        return m["id"]

    def _flush_outbox(self, peer_id):
        """Одна отправка на ПК за раз: иначе параллельные потоки шлют первый файл очереди несколько раз."""
        with self._lock:
            if peer_id in self._flushing:
                return
            self._flushing.add(peer_id)
        try:
            while True:
                self._flush_once(peer_id)
                with self._lock:
                    q, s = self.outbox.get(peer_id), self.sessions.get(peer_id)
                    if not (q and s and s.alive) or self._flush_failed:
                        self._flushing.discard(peer_id)
                        return
        except BaseException:
            with self._lock:
                self._flushing.discard(peer_id)
            raise

    _flush_failed = False

    def _flush_once(self, peer_id):
        self._flush_failed = False
        q = self.outbox.get(peer_id)
        s = self.sessions.get(peer_id)
        while q and s and s.alive:
            m = q[0]
            if time.time() - m["ts"] > 7 * 86400:
                q.popleft()
                continue
            try:
                if m.get("file"):
                    with open(m["file"], "rb") as f:
                        blob = f.read()
                    s.call("file", {k: v for k, v in m.items() if k != "file"} | {"name": os.path.basename(m["file"])}, blob, timeout=300)
                else:
                    s.call("chat", m, timeout=10)
            except NetError:
                self._flush_failed = True
                return
            except OSError:                    # файл пропал: не блокировать очередь
                q.popleft()
                continue
            if q and q[0] is m:
                q.popleft()
            self._emit("delivered", peer=peer_id, id=m["id"])
