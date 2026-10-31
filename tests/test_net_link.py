import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import net_link as nl
import multi_print


def mk(name, **kw):
    return nl.Node(name, host="127.0.0.1", port=0, udp_port=0, **kw).start()


def pair(a, b):
    code = b.open_pairing()
    a.pair("127.0.0.1", code, b.port)
    return code


def wait(cond, t=5.0):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def nodes():
    made = []

    def make(name, **kw):
        n = mk(name, **kw)
        made.append(n)
        return n
    yield make
    for n in made:
        n.stop()


def test_pairing_and_presence(nodes):
    events = []
    a = nodes("A", on_event=lambda k, i: events.append((k, i.get("online"))))
    b = nodes("B")
    pair(a, b)
    assert wait(lambda: a.online(b.id) and b.online(a.id))
    assert b.peers_paired[a.id]["key"] == a.peers_paired[b.id]["key"]
    assert ("presence", True) in events
    b.sessions[a.id].close()
    assert wait(lambda: not a.online(b.id))
    assert wait(lambda: ("presence", False) in events)      # событие уходит чуть позже, чем сессия снята


def test_pairing_wrong_code_and_closed(nodes):
    a, b = nodes("A"), nodes("B")
    with pytest.raises(nl.NetError):
        a.pair("127.0.0.1", nl.new_code(), b.port)        # спаривание не открыто
    b.open_pairing()
    with pytest.raises(nl.NetError):
        a.pair("127.0.0.1", nl.new_code(), b.port)        # чужой код
    assert not a.peers_paired and not b.peers_paired


def test_unpaired_node_rejected_and_forget(nodes):
    a, b, c = nodes("A"), nodes("B"), nodes("C")
    pair(a, b)
    assert wait(lambda: a.online(b.id))
    c.peers_paired[b.id] = {"name": "B", "key": nl.new_code(), "addr": "127.0.0.1", "port": b.port}
    time.sleep(0.5)
    assert not c.online(b.id)
    b.forget(a.id)
    assert wait(lambda: not a.online(b.id))
    time.sleep(3.5)                                        # a пробует переподключиться, но b ключ забыл
    assert not a.online(b.id)


def test_submit_dedup_and_events(nodes):
    printed = []
    got = []
    b = nodes("B", print_sheet=lambda m, d: printed.append((m["printer"], d)),
              on_event=lambda k, i: got.append(k))
    a = nodes("A")
    pair(a, b)
    assert wait(lambda: a.online(b.id))
    a.send_sheet(b.id, "Epson", "j1", "s1", b"x" * 100000, total=2)
    s = a.sessions[b.id]
    h, _ = s.call("submit", {"printer": "Epson", "job_id": "j1", "sheet_id": "s1", "total": 2}, b"x")
    assert h["duplicate"] and len(printed) == 1                       # повтор не печатается
    a.send_sheet(b.id, "Epson", "j1", "s2", b"y", total=2)
    assert len(printed) == 2
    assert got.count("job_received") == 1                              # уведомление один раз на задание


def test_limits_and_switch(nodes):
    printed = []
    b = nodes("B", print_sheet=lambda m, d: printed.append(1), max_sheets=3)
    a = nodes("A")
    pair(a, b)
    assert wait(lambda: a.online(b.id))
    with pytest.raises(nl.NetError):
        a.send_sheet(b.id, "P", "big", "s1", b"x", total=4)
    b.shared = {"Open"}
    with pytest.raises(nl.NetError):
        a.send_sheet(b.id, "Closed", "j", "s1", b"x")
    a.send_sheet(b.id, "Open", "j", "s2", b"x")
    b.net_enabled = False
    with pytest.raises(nl.NetError):
        a.send_sheet(b.id, "Open", "j", "s3", b"x")
    assert len(printed) == 1


def test_printer_failure_reported(nodes):
    def boom(m, d):
        raise RuntimeError("нет бумаги")
    b = nodes("B", print_sheet=boom)
    a = nodes("A")
    pair(a, b)
    assert wait(lambda: a.online(b.id))
    with pytest.raises(nl.NetError, match="нет бумаги"):
        a.send_sheet(b.id, "P", "j", "s1", b"x")


def test_one_queue_per_printer(nodes):
    active, peak = [0], [0]

    def slow(m, d):
        active[0] += 1
        peak[0] = max(peak[0], active[0])
        time.sleep(0.1)
        active[0] -= 1
    b = nodes("B", print_sheet=slow)
    a = nodes("A")
    pair(a, b)
    assert wait(lambda: a.online(b.id))
    ts = [threading.Thread(target=a.send_sheet, args=(b.id, "P", "j", f"s{i}", b"x", 4)) for i in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert peak[0] == 1


def test_printer_state_and_chat(nodes):
    chats = []
    b = nodes("B", on_event=lambda k, i: chats.append(i) if k == "chat" else None)
    a = nodes("A")
    pair(a, b)
    assert wait(lambda: a.online(b.id) and b.online(a.id))
    b.publish_state("Epson", "attention", "нет бумаги")
    assert wait(lambda: a.peer_state.get(b.id, {}).get("Epson", {}).get("level") == "attention")
    a.chat_send(b.id, "жду фото", user="Аня")
    assert wait(lambda: chats and chats[0]["text"] == "жду фото" and chats[0]["user"] == "Аня")
    # офлайн: сообщение ждёт в очереди и доходит после переподключения
    a.sessions[b.id].close()
    assert wait(lambda: not a.online(b.id))
    a.chat_send(b.id, "второе")
    assert wait(lambda: len(chats) == 2, 10)


def test_outcome_unknown_on_drop(nodes):
    release = threading.Event()

    def hang(m, d):
        release.wait(5)
    b = nodes("B", print_sheet=hang)
    a = nodes("A")
    pair(a, b)
    assert wait(lambda: a.online(b.id))
    threading.Timer(0.5, lambda: (a.sessions[b.id].close(), b.forget(a.id))).start()
    with pytest.raises(nl.OutcomeUnknown):
        a.send_sheet(b.id, "P", "j", "s1", b"x", timeout=3)
    release.set()


def test_tampered_frame_detected(nodes):
    a, b = nodes("A"), nodes("B")
    pair(a, b)
    assert wait(lambda: a.online(b.id))
    s = a.sessions[b.id]
    s.ch.seq_out += 1                  # рассинхрон номера кадра = повтор/подмена
    with pytest.raises(nl.NetError):
        s.call("ping", timeout=2)
    assert wait(lambda: not b.online(a.id))


def test_discovery_and_remote_send_with_multirun(nodes):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    printed, local = [], []
    b = nodes("B", print_sheet=lambda m, d: printed.append(d))
    a = nodes("A")
    a.udp_port = b.udp_port = port
    a.listen_discovery()
    b.announce("127.0.0.1")
    assert wait(lambda: b.id in a.found)
    assert a.found[b.id]["port"] == b.port
    pair(a, b)
    assert wait(lambda: a.online(b.id))
    remote = a.remote_send(b.id)

    def send(printer, sheet):
        if printer == "remote":
            remote(printer, sheet)
        else:
            time.sleep(0.3)                  # медленный локальный принтер: часть листов уйдёт на удалённый
            local.append(sheet)
    multi_print.MultiRun([b"s1", b"s2", b"s3", b"s4"], ["local", "remote"], send).run()
    assert len(printed) + len(local) == 4 and printed
