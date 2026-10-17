"""Access control for requests that reach the dashboard through Tailscale Serve (Host *.ts.net).

Localhost (SSH tunnel) is never restricted. Over the tailnet:
  A. identity allowlist: header Tailscale-User-Login must be in .lab/access.json "allowed_logins";
  B. PIN (salted scrypt hash in .lab/access.json) for the Terminal and Sudo tabs; 5 wrong PINs lock them 15 min;
  C. every denial / wrong PIN / lockout goes to .lab/access_log.jsonl and (max once per 10 min) to a dashboard message.
Header names are from the Tailscale Serve docs (Tailscale-User-Login / Tailscale-User-Name); not verified against the
installed CLI (its help does not list them), and they are only trustworthy because Serve overwrites them.

CLI:  python3 tools/access.py set-pin | status
"""
import hashlib
import hmac
import json
import os
import secrets
import sys
import time

MAX_FAILS = 5
LOCK_SECONDS = 15 * 60
UNLOCK_SECONDS = 30 * 60
ALERT_EVERY = 10 * 60
THREAD_TITLE = "Ασφάλεια πρόσβασης"
_INSTRUCTIONS = ("Βάλε στο allowed_logins τα Tailscale logins που επιτρέπονται (π.χ. \"you@gmail.com\"). "
                 "Το pin_hash ορίζεται με: python3 tools/access.py set-pin")


def _lab():
    return os.path.join(os.environ.get("QRL_LAB_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), ".lab")


def _p(name):
    return os.path.join(_lab(), name)


def _read(name, default):
    try:
        with open(_p(name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(name, data):
    os.makedirs(_lab(), exist_ok=True)
    tmp = _p(name) + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, _p(name))


def load_config():
    """Reads access.json; creates it with an empty allowlist (deny everyone over the tailnet) if missing."""
    cfg = _read("access.json", None)
    if cfg is None:
        cfg = {"allowed_logins": [], "pin_hash": None, "instructions": _INSTRUCTIONS}
        _write("access.json", cfg)
    return cfg


def hash_pin(pin, salt=None):
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pin.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_hash(pin, stored):
    try:
        _, salt, h = stored.split("$")
        cand = hash_pin(pin, bytes.fromhex(salt)).split("$")[2]
        return hmac.compare_digest(cand, h)
    except (ValueError, AttributeError):
        return False


def set_pin(pin):
    if len(pin) < 6:
        raise ValueError("PIN must have at least 6 characters.")
    cfg = load_config()
    cfg["pin_hash"] = hash_pin(pin)
    _write("access.json", cfg)
    _write("access_state.json", {"fails": [], "locked_until": 0, "last_alert": 0})


def client_info(headers):
    g = lambda k: (headers.get(k) or "") if headers else ""  # noqa: E731
    return {"login": g("Tailscale-User-Login").strip(), "ip": g("X-Forwarded-For").strip() or g("X-Real-Ip").strip(),
            "ua": g("User-Agent")[:200]}


def check_login(info, cfg=None):
    """Returns (allowed, reason). Call only for .ts.net hosts."""
    cfg = cfg or load_config()
    if not info["login"]:
        return False, "missing Tailscale-User-Login header"
    allowed = [x.strip().lower() for x in cfg.get("allowed_logins", []) if isinstance(x, str)]
    if info["login"].lower() not in allowed:
        return False, "login not in allowlist"
    return True, ""


def log_event(info, reason, now=None):
    now = now or time.time()
    os.makedirs(_lab(), exist_ok=True)
    row = {"ts": now, "login": info.get("login", ""), "ip": info.get("ip", ""), "ua": info.get("ua", ""), "reason": reason}
    with open(_p("access_log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def recent(limit=50, max_age=None, now=None):
    out = []
    try:
        with open(_p("access_log.jsonl"), encoding="utf-8") as f:
            for line in f.readlines()[-2000:]:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        return []
    if max_age is not None:
        out = [r for r in out if (now or time.time()) - r["ts"] <= max_age]
    return out[-limit:][::-1]


def alert(info, reason, post=None, now=None):
    """Log the event; post a dashboard message at most once per ALERT_EVERY. Returns True if a message was posted.
    `post(text)` is injectable for tests; default writes to the lab DB."""
    now = now or time.time()
    log_event(info, reason, now)
    st = _read("access_state.json", {"fails": [], "locked_until": 0, "last_alert": 0})
    if now - st.get("last_alert", 0) < ALERT_EVERY:
        return False
    st["last_alert"] = now
    _write("access_state.json", st)
    text = (f"Απορρίφθηκε πρόσβαση στο dashboard: {reason}. Login: {info.get('login') or '(κανένα)'}, "
            f"IP: {info.get('ip') or '-'}. Δες το «🛡️ Πρόσβαση» στην καρτέλα Sudo.")
    try:
        (post or _post_db)(text)
    except Exception:  # noqa: BLE001 - alerting must never break the denial itself
        return False
    return True


def _post_db(text):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from labdb import LabDB
    d = LabDB()
    try:
        tid = d.ensure_thread(THREAD_TITLE, "Ειδοποιήσεις για απορριφθείσες προσβάσεις στο dashboard.")
        d.post("system", text, tid, kind="status")
    finally:
        d.close()


def locked(now=None):
    """Seconds left of the PIN lockout (0 if not locked)."""
    st = _read("access_state.json", {})
    return max(0, int(st.get("locked_until", 0) - (now or time.time())))


def try_pin(pin, info, post=None, now=None):
    """Returns (ok, message). Counts wrong PINs globally (a page refresh does not reset them)."""
    now = now or time.time()
    left = locked(now)
    if left:
        return False, f"Κλειδωμένο για ακόμη {left // 60 + 1} λεπτά."
    cfg = load_config()
    if not cfg.get("pin_hash"):
        return False, "Δεν έχει οριστεί PIN (python3 tools/access.py set-pin)."
    if verify_hash(pin, cfg["pin_hash"]):
        st = _read("access_state.json", {})
        st["fails"] = []
        _write("access_state.json", st)
        return True, ""
    st = _read("access_state.json", {"fails": [], "locked_until": 0, "last_alert": 0})
    st["fails"] = [t for t in st.get("fails", []) if now - t < LOCK_SECONDS] + [now]
    if len(st["fails"]) >= MAX_FAILS:
        st["locked_until"] = now + LOCK_SECONDS
        st["fails"] = []
        _write("access_state.json", st)
        alert(info, f"{MAX_FAILS} λάθος PIN, κλείδωμα 15 λεπτών", post, now)
        return False, "Πολλά λάθος PIN: κλειδώθηκε για 15 λεπτά."
    _write("access_state.json", st)
    alert(info, "λάθος PIN", post, now)
    return False, f"Λάθος PIN ({MAX_FAILS - len(st['fails'])} προσπάθειες ακόμη)."


def main(argv):
    if len(argv) > 1 and argv[1] == "set-pin":
        import getpass
        a, b = getpass.getpass("Νέο PIN (min 6): "), getpass.getpass("Επανάληψη: ")
        if a != b:
            print("Δεν ταιριάζουν.")
            return 1
        try:
            set_pin(a)
        except ValueError as e:
            print(e)
            return 1
        print("PIN ορίστηκε (αποθηκεύεται μόνο ως salted scrypt hash στο .lab/access.json).")
        return 0
    if len(argv) > 1 and argv[1] == "status":
        cfg = load_config()
        print(f"allowed_logins: {cfg.get('allowed_logins')}  pin_set: {bool(cfg.get('pin_hash'))}  lock_left_s: {locked()}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
