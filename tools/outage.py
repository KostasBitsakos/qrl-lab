#!/usr/bin/env python3
"""VM outage bookkeeping (no LLM). Used by tools/boot_recover.sh and the dashboard tab «Διακοπές».

  outage.py record     compare the last heartbeat with the boot time, append to .lab/outages.jsonl, write the banner flag
  outage.py announce   post the Greek status message into the dashboard thread «Διακοπές VM» (--dry: print only)

Files (override with env for tests / dry run): QRL_OUTAGES_FILE, QRL_RECOVERY_FLAG; heartbeat: .lab/heartbeat
(written every minute by tools/watchdog.sh; the last value before the boot is also kept in .lab/heartbeat_pre_boot).
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

ROOT = os.environ.get("QRL_LAB_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LAB = os.path.join(ROOT, ".lab")
FLAG_TTL = 24 * 3600
THREAD_TITLE = "Διακοπές VM"
SHUTDOWN_SLACK = 180  # a shutdown entry counts if it lies in [down_at - slack, boot_at]


def outages_path():
    return os.environ.get("QRL_OUTAGES_FILE") or os.path.join(LAB, "outages.jsonl")


def flag_path():
    return os.environ.get("QRL_RECOVERY_FLAG") or os.path.join(LAB, "recovery_flag.json")


def read_epoch(path):
    """Integer epoch from a one-line file; None when missing or malformed."""
    try:
        with open(path) as f:
            v = int(float(f.read().strip().split()[0]))
        return v if v > 0 else None
    except (OSError, ValueError, IndexError):
        return None


def boot_time():
    """Boot epoch from /proc/stat btime; None if unavailable."""
    try:
        with open("/proc/stat") as f:
            for ln in f:
                if ln.startswith("btime "):
                    return int(ln.split()[1])
    except (OSError, ValueError):
        pass
    return None


def last_heartbeat(lab, boot_at):
    """Latest heartbeat strictly before the boot (the file itself, or the copy the watchdog saved before overwriting)."""
    c = [read_epoch(os.path.join(lab, n)) for n in ("heartbeat", "heartbeat_pre_boot")]
    c = [v for v in c if v is not None and v < boot_at]
    return max(c) if c else None


def shutdown_times(text):
    """Epochs of shutdown/reboot entries from `last -x -F shutdown reboot` output (best effort)."""
    out = []
    for ln in text.splitlines():
        if not ln.startswith(("shutdown", "reboot")):
            continue
        # "shutdown system down  5.4.0  Sat Oct 17 17:30:01 2026 - Sat Oct 17 17:31:12 2026 (00:01)"
        toks = ln.split()
        for i in range(len(toks) - 4):
            try:
                t = dt.datetime.strptime(" ".join(toks[i:i + 5]), "%a %b %d %H:%M:%S %Y")
            except ValueError:
                continue
            out.append(int(t.timestamp()))
            break
    return out


def classify(shutdowns, down_at, boot_at):
    """'reboot' if a clean shutdown entry sits between the last heartbeat and the boot; 'crash/power' if the log is readable
    but has none; 'unknown' when there is no log or no heartbeat."""
    if down_at is None or shutdowns is None:
        return "unknown"
    if any(down_at - SHUTDOWN_SLACK <= s <= boot_at for s in shutdowns):
        return "reboot"
    return "crash/power"


def read_last_x():
    try:
        r = subprocess.run(["last", "-x", "-F", "shutdown", "reboot"], capture_output=True, text=True, timeout=10)
        return shutdown_times(r.stdout) if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        return None


def compute(down_at, boot_at, recovered_at, shutdowns):
    return {"down_at": down_at, "boot_at": boot_at, "recovered_at": recovered_at,
            "downtime_s": (recovered_at - down_at) if down_at is not None else None,
            "kind": classify(shutdowns, down_at, boot_at)}


def load(path=None):
    rows = []
    try:
        with open(path or outages_path()) as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                    if isinstance(r, dict) and "boot_at" in r:
                        rows.append(r)
                except ValueError:
                    pass
    except OSError:
        pass
    return rows


def summary(rows):
    known = [r["downtime_s"] for r in rows if isinstance(r.get("downtime_s"), (int, float))]
    return {"count": len(rows), "total_downtime_s": sum(known), "last": rows[-1] if rows else None}


def fmt_dur(s):
    if s is None:
        return "άγνωστη"
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return (f"{h}ω " if h else "") + (f"{m}λ " if (h or m) else "") + f"{sec}δ"


def fmt_ts(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "άγνωστη"


def banner_text(now=None, path=None):
    """Banner text while a recovery flag is younger than 24h, else ''."""
    now = now or time.time()
    try:
        with open(path or flag_path()) as f:
            fl = json.load(f)
        if now - float(fl["recovered_at"]) < FLAG_TTL:
            return f"⚡ Το VM επανεκκινήθηκε στις {fmt_ts(fl['boot_at'])} (διάρκεια διακοπής: {fmt_dur(fl.get('downtime_s'))})"
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return ""


def record(lab=None, now=None, boot_at=None, shutdowns="auto"):
    """Idempotent per boot: returns (row, created)."""
    lab = lab or LAB
    boot_at = boot_at or boot_time()
    if boot_at is None:
        raise RuntimeError("boot time unknown")
    for r in load():
        if r["boot_at"] == boot_at:
            return r, False
    now = int(now or time.time())
    down_at = last_heartbeat(lab, boot_at)
    sd = read_last_x() if shutdowns == "auto" else shutdowns
    row = compute(down_at, boot_at, now, sd)
    os.makedirs(os.path.dirname(outages_path()), exist_ok=True)
    with open(outages_path(), "a") as f:
        f.write(json.dumps(row) + "\n")
    with open(flag_path(), "w") as f:
        json.dump(row, f)
    return row, True


def up_status():
    """Greek per-component truth, from real checks (HTTP 200, fresh heartbeat, claude in the window, terminal port)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import verify_services
    return verify_services.report_items(verify_services.check_all())


def message(row, items):
    kind = {"reboot": "καθαρή επανεκκίνηση", "crash/power": "κατάρρευση/διακοπή ρεύματος", "unknown": "άγνωστη αιτία"}[row["kind"]]
    down = f"στις {fmt_ts(row['down_at'])}" if row["down_at"] else "(ώρα άγνωστη, δεν υπήρχε heartbeat)"
    return (f"Κώστα, το VM έπεσε {down} και ξανανέβηκε στις {fmt_ts(row['boot_at'])} "
            f"(διάρκεια {fmt_dur(row['downtime_s'])}, {kind}). Κατάσταση υπηρεσιών (επαληθευμένη τώρα): " + "; ".join(items) + ". "
            "Δεν καλύπτεται: αν το Claude ζητήσει νέο login, χρειάζεται δικό σου βήμα στο terminal· τυχόν runs που έτρεχαν "
            "διακόπηκαν και πρέπει να ελεγχθούν.")


def announce(dry=False):
    rows = load()
    if not rows:
        print("no outage recorded")
        return None
    row = rows[-1]
    text = message(row, up_status())
    if dry:
        print(text)
        return text
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from labdb import LabDB
    db = LabDB()
    tid = db.ensure_thread(THREAD_TITLE, "Αυτόματες ειδοποιήσεις για διακοπές και επαναφορές του VM.")
    print(db.post("coordinator", text, tid, kind="status", model="system"))
    return text


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("record")
    a = sub.add_parser("announce")
    a.add_argument("--dry", action="store_true")
    ns = ap.parse_args(argv)
    if ns.cmd == "record":
        row, created = record()
        print(json.dumps({"created": created, **row}))
    else:
        announce(ns.dry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
