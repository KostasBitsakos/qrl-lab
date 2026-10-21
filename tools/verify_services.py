#!/usr/bin/env python3
"""Verify (not assume) that the lab components really serve, restart the dead ones, and report the truth. No LLM.

  verify_services.py check                 print one JSON line {component: {"ok": bool, "detail": str}}
  verify_services.py ensure [--retries N]  boot_recover: check, restart what is down, retry; print final JSON
  verify_services.py watchdog              one cron tick: restart dashboard/health after STRIKES failed checks;
                                           after MAX_RESTARTS consecutive failed restarts write .lab/outages.jsonl
                                           (kind=service_failure) and post one dashboard status message.

Components: dashboard (HTTP 200 on 127.0.0.1:8501), health (heartbeat file younger than HB_STALE s),
coordinator (tmux lab:coordinator runs a claude process, not a bare shell), terminal (port 8502; ON DEMAND: the
server exits by design after 30 min idle, so a closed port is reported as "on demand", not as a failure).
Env for tests: QRL_LAB_DIR, QRL_VERIFY_DRYRUN=1 (never touches tmux; restarts are only recorded).
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.environ.get("QRL_LAB_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LAB = os.path.join(ROOT, ".lab")
SESSION = os.environ.get("QRL_TMUX_SESSION", "lab")
DASH_URL = "http://127.0.0.1:8501/"
TERM_PORT = 8502
HB_STALE = 180
STRIKES = 3        # consecutive failed checks before the watchdog restarts a component
MAX_RESTARTS = 5   # consecutive failed restarts before the outage entry
SHELLS = ("bash", "sh", "zsh", "fish", "dash")
ORDER = ("coordinator", "dashboard", "health", "terminal")
LABELS = {"coordinator": "συντονιστής (Claude)", "dashboard": "dashboard", "health": "health watch", "terminal": "web terminal"}


def _tmux(*args):
    try:
        r = subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=10)
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def check_dashboard():
    try:
        with urllib.request.urlopen(DASH_URL, timeout=4) as r:
            return r.status == 200, f"HTTP {r.status}"
    except Exception as e:  # noqa: BLE001
        return False, f"no HTTP 200 on {DASH_URL} ({type(e).__name__})"


def check_health(lab=None, now=None):
    p = os.path.join(lab or LAB, "health_watch.heartbeat")
    try:
        age = (now or time.time()) - os.stat(p).st_mtime
    except OSError:
        return False, "no heartbeat file"
    return (age <= HB_STALE), f"heartbeat {int(age)}s old"


def _descendants_have_claude(pid):
    """True if the process tree under `pid` contains a `claude` process (the foreground command can be a tool shell)."""
    try:
        out = subprocess.run(["ps", "-eo", "pid=,ppid=,comm=,args="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    kids, info = {}, {}
    for ln in out.splitlines():
        t = ln.split(None, 3)
        if len(t) >= 3 and t[0].isdigit() and t[1].isdigit():
            kids.setdefault(int(t[1]), []).append(int(t[0]))
            info[int(t[0])] = (t[2] + " " + (t[3] if len(t) > 3 else "")).lower()
    todo, seen = [int(pid)], set()
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        if p != int(pid) and "claude" in info.get(p, ""):
            return True
        todo += kids.get(p, [])
    return False


def check_coordinator():
    rc, out = _tmux("list-panes", "-t", f"{SESSION}:coordinator", "-F", "#{pane_current_command} #{pane_pid}")
    parts = out.strip().splitlines()[0].split() if rc == 0 and out.strip() else []
    if len(parts) < 2:
        return False, "no coordinator window"
    cmd, pid = parts[0], parts[1]
    if "claude" in cmd.lower() or _descendants_have_claude(pid):
        return True, "claude process in the coordinator window"
    return False, f"no claude process in the window (foreground: {cmd})"


def check_terminal():
    try:
        with socket.create_connection(("127.0.0.1", TERM_PORT), timeout=0.5):
            return True, f"port {TERM_PORT} open"
    except OSError:
        return False, "on demand (starts from the dashboard tab; idle exit after 30 min)"


CHECKS = {"coordinator": check_coordinator, "dashboard": check_dashboard, "health": check_health, "terminal": check_terminal}


def check_all():
    fake = os.environ.get("QRL_VERIFY_FAKE")  # tests only: a JSON {component: {"ok":..,"detail":..}}
    if fake:
        return json.loads(fake)
    out = {}
    for k in ORDER:
        ok, detail = CHECKS[k]()
        out[k] = {"ok": bool(ok), "detail": detail}
    return out


def restart(name, dry=None):
    """Restart one component's tmux window (never the coordinator). Returns True if the command was issued."""
    dry = os.environ.get("QRL_VERIFY_DRYRUN") == "1" if dry is None else dry
    if dry or name == "coordinator":
        return False
    if name == "terminal":
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import web_terminal
        return web_terminal.start(wait=25.0)[0]
    # cores: 0-3 dashboard, 4-7 agents/tests, 8-39 experiments (researcher, 2026-10-21)
    cmd = {"dashboard": "taskset -c 0-3 ./.venv/bin/streamlit run dashboard/app.py; exec bash",
           "health": "python3 tools/health_watch.py; exec bash"}[name]
    _tmux("kill-window", "-t", f"{SESSION}:{name}")
    rc, _ = _tmux("new-window", "-d", "-t", SESSION, "-n", name, "-c", ROOT, cmd)
    return rc == 0


def ensure(retries=6, wait=10.0, sleep=time.sleep):
    """Check, restart down components (not the coordinator), re-check up to `retries` times. Returns the final report."""
    rep = check_all()
    for i in range(retries):
        down = [k for k in ("dashboard", "health", "terminal") if not rep[k]["ok"]]
        if not down:
            break
        for k in down:
            if not rep[k].get("restarted"):
                restart(k)
        sleep(wait)
        new = check_all()
        for k in new:
            new[k]["restarted"] = rep[k].get("restarted") or (k in down)
        rep = new
    return rep


def report_items(rep):
    """Greek per-component truth for the announcement."""
    items = []
    for k in ORDER:
        r = rep[k]
        if r["ok"]:
            s = "ναι (επαληθεύτηκε)"
        elif k == "terminal":
            s = "ΟΧΙ τώρα (on-demand, ανοίγει από το dashboard)"
        else:
            s = f"ΟΧΙ ({r['detail']})"
        items.append(f"{LABELS[k]}: {s}")
    return items


# ---------------------------------------------------------------- watchdog tick
def _state_path():
    return os.path.join(LAB, "service_state.json")


def _load_state():
    try:
        with open(_state_path()) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(st):
    tmp = _state_path() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f)
    os.replace(tmp, _state_path())


def tick(rep=None, now=None, do_restart=restart, notify=None):
    """One watchdog tick over dashboard and health. Returns the list of actions taken."""
    rep = rep or check_all()
    now = int(now or time.time())
    st = _load_state()
    acts = []
    for k in ("dashboard", "health"):
        if k == "dashboard" and not os.path.exists(os.path.join(ROOT, ".venv", "bin", "streamlit")):
            continue  # same condition as the shell watchdog: no streamlit, no dashboard to supervise
        s = st.setdefault(k, {"strikes": 0, "restarts": 0, "alerted": False})
        if rep[k]["ok"]:
            s.update(strikes=0, restarts=0, alerted=False)
            continue
        s["strikes"] += 1
        if s["strikes"] < STRIKES:
            continue
        if s["restarts"] >= MAX_RESTARTS:
            if not s["alerted"]:
                s["alerted"] = True
                row = {"kind": "service_failure", "component": k, "at": now, "restarts": s["restarts"],
                       "detail": rep[k]["detail"]}
                os.makedirs(LAB, exist_ok=True)
                with open(os.environ.get("QRL_OUTAGES_FILE") or os.path.join(LAB, "outages.jsonl"), "a") as f:
                    f.write(json.dumps(row) + "\n")
                (notify or _post)(f"Κώστα, το {LABELS[k]} δεν σηκώνεται μετά από {s['restarts']} αυτόματες επανεκκινήσεις "
                                  f"({rep[k]['detail']}). Χρειάζεται χειροκίνητος έλεγχος: tmux attach -t lab, παράθυρο {k}.")
                acts.append(f"alert:{k}")
            continue
        s["restarts"] += 1
        s["strikes"] = 0
        do_restart(k)
        acts.append(f"restart:{k}")
    _save_state(st)
    return acts


def _post(text):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from labdb import LabDB
    db = LabDB()
    tid = db.ensure_thread("Διακοπές VM", "Αυτόματες ειδοποιήσεις για διακοπές και επαναφορές του VM.")
    db.post("coordinator", text, tid, kind="status", model="system")


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    cmd = a[0] if a else "check"
    if cmd == "check":
        print(json.dumps(check_all(), ensure_ascii=False))
    elif cmd == "ensure":
        n = int(a[a.index("--retries") + 1]) if "--retries" in a else 6
        print(json.dumps(ensure(retries=n), ensure_ascii=False))
    elif cmd == "watchdog":
        rc, _ = _tmux("has-session", "-t", SESSION)
        if rc == 0:
            for x in tick():
                print(time.strftime("%F %T"), x)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
