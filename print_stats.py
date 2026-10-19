# -*- coding: utf-8 -*-
"""Print counter for PhotoCrop: a journal of printed sheets plus an admin password.

No GUI code here, so the agent/MCP exe can use it too.
Files in %APPDATA%\\PhotoCrop:
  print_log.jsonl   one JSON line per printed sheet; every line carries an HMAC that chains to the previous line,
                    so an edited or removed line shows up as "journal changed" in the admin window.
  print_admin.json  salted password hash, recovery-key hash and the HMAC key.
The password protects against a casual user. Someone who can edit files on this PC can still delete the journal
altogether, because the program is open source and runs locally.
"""
import csv
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

MIN_PASSWORD = 6
MAX_FAILS = 5
LOCK_SECONDS = 300
KDF_ROUNDS = 200_000
_lock = threading.Lock()


def _dir():
    return Path(os.environ.get("APPDATA", str(Path.home()))) / "PhotoCrop"


def _log_path():
    return _dir() / "print_log.jsonl"


def _admin_path():
    return _dir() / "print_admin.json"


# ------------------------------------------------------------------ admin file

def _load_admin():
    try:
        d = json.loads(_admin_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    if not d.get("key"):
        d["key"] = secrets.token_hex(32)
    return d


def _save_admin(d):
    _dir().mkdir(parents=True, exist_ok=True)
    tmp = _admin_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(d), encoding="utf-8")
    os.replace(tmp, _admin_path())


def _kdf(secret, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), bytes.fromhex(salt_hex), KDF_ROUNDS).hex()


def has_password():
    return bool(_load_admin().get("hash"))


def set_password(password, current_admin=None):
    """Sets (or replaces) the admin password. Returns a new one-time recovery key."""
    if len(password) < MIN_PASSWORD:
        raise ValueError("password too short")
    d = current_admin or _load_admin()
    d["salt"] = secrets.token_hex(16)
    d["hash"] = _kdf(password, d["salt"])
    rec = "-".join(secrets.token_hex(2).upper() for _ in range(4))
    d["rec_salt"] = secrets.token_hex(16)
    d["rec_hash"] = _kdf(rec, d["rec_salt"])
    d["fails"], d["locked_until"] = 0, 0
    _save_admin(d)
    return rec


def lock_remaining():
    return max(0, int(_load_admin().get("locked_until", 0) - time.time()))


def check_password(password):
    """-> (ok, seconds_locked). After MAX_FAILS wrong tries login is blocked for LOCK_SECONDS."""
    with _lock:
        d = _load_admin()
        left = int(d.get("locked_until", 0) - time.time())
        if left > 0:
            return False, left
        if d.get("hash") and hmac.compare_digest(_kdf(password, d["salt"]), d["hash"]):
            d["fails"], d["locked_until"] = 0, 0
            _save_admin(d)
            return True, 0
        d["fails"] = int(d.get("fails", 0)) + 1
        if d["fails"] >= MAX_FAILS:
            d["fails"], d["locked_until"] = 0, time.time() + LOCK_SECONDS
        _save_admin(d)
        return False, max(0, int(d.get("locked_until", 0) - time.time()))


def change_password(old, new):
    ok, _ = check_password(old)
    if not ok:
        return None
    return set_password(new)


def reset_with_recovery(recovery, new):
    """Sets a new password when the recovery key matches. -> new recovery key or None."""
    d = _load_admin()
    if not d.get("rec_hash") or not hmac.compare_digest(_kdf(recovery.strip().upper(), d["rec_salt"]), d["rec_hash"]):
        return None
    return set_password(new, d)


# ------------------------------------------------------------------ journal

def _mac(key, prev, body):
    return hmac.new(bytes.fromhex(key), (prev + body).encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _last_mac():
    p = _log_path()
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 4096))
            lines = f.read().decode("utf-8", "replace").strip().splitlines()
        return json.loads(lines[-1]).get("h", "") if lines else ""
    except (OSError, ValueError, IndexError):
        return ""


def record(printer, photos=0, paper="", mode="", source="app", sheets=1, files=None):
    """Adds one successfully printed sheet (x copies) to the journal. Failed or cancelled sheets are never recorded.
    Never raises: a broken counter must not stop printing."""
    try:
        with _lock:
            d = _load_admin()
            if not _admin_path().exists():
                _save_admin(d)
            now = time.time()
            rec = {"ts": round(now, 1), "t": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)), "printer": str(printer or ""),
                   "photos": int(photos), "paper": str(paper or ""), "mode": str(mode or ""), "source": str(source or "app"), "sheets": int(sheets),
                   "files": [str(x) for x in (files or [])][:60]}
            body = json.dumps(rec, ensure_ascii=False, sort_keys=True)
            rec["h"] = _mac(d["key"], _last_mac(), body)
            _dir().mkdir(parents=True, exist_ok=True)
            with open(_log_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_all():
    out = []
    try:
        for line in _log_path().read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                out.append({"bad": True})
    except OSError:
        pass
    return out


def verify():
    """-> (ok, first_bad_line_number or 0). Checks the HMAC chain."""
    key = _load_admin()["key"]
    prev = ""
    for i, r in enumerate(read_all(), 1):
        h = r.pop("h", None)
        if h is None or r.get("bad") or not hmac.compare_digest(h, _mac(key, prev, json.dumps(r, ensure_ascii=False, sort_keys=True))):
            return False, i
        prev = h
    return True, 0


def _midnight(days_back=0):
    t = time.localtime()
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday - days_back, 0, 0, 0, 0, 0, -1))


def totals(records=None, since=0.0):
    """-> {"sheets": n, "photos": n}. since = epoch seconds."""
    sheets = photos = 0
    for r in (records if records is not None else read_all()):
        if r.get("ts", 0) >= since:
            sheets += int(r.get("sheets", 1))
            photos += int(r.get("photos", 0)) * int(r.get("sheets", 1))     # файлов напечатано = фото на листе x копии
    return {"sheets": sheets, "photos": photos}


def today():
    return totals(since=_midnight(0))


def summary(records=None):
    """Aggregates for the admin window."""
    recs = [r for r in (records if records is not None else read_all()) if not r.get("bad")]
    periods = {"today": _midnight(0), "week": _midnight(6), "month": _midnight(29), "all": 0.0}
    out = {"periods": {k: totals(recs, v) for k, v in periods.items()}}
    for field in ("printer", "paper", "source"):
        agg = {}
        for r in recs:
            k = r.get(field) or "-"
            agg[k] = agg.get(k, 0) + int(r.get("sheets", 1))
        out[field] = sorted(agg.items(), key=lambda kv: -kv[1])
    days = {}
    for r in recs:
        if r.get("ts", 0) >= _midnight(13):
            days[r["t"][:10]] = days.get(r["t"][:10], 0) + int(r.get("sheets", 1))
    out["days"] = sorted(days.items())
    return out


def export_csv(path):
    recs = [r for r in read_all() if not r.get("bad")]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["time", "printer", "paper_mm", "photos_on_sheet", "mode", "source", "sheets", "files"])
        for r in recs:
            w.writerow([r.get("t"), r.get("printer"), r.get("paper"), r.get("photos"), r.get("mode"), r.get("source"), r.get("sheets", 1), " | ".join(r.get("files") or [])])
    return len(recs)


def clear_log():
    """Moves the journal to a dated backup file and starts an empty one. -> backup path or None."""
    with _lock:
        p = _log_path()
        if not p.exists():
            return None
        bak = p.with_name("print_log_" + time.strftime("%Y%m%d_%H%M%S") + ".jsonl.bak")
        os.replace(p, bak)
        return bak
