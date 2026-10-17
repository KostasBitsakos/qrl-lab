#!/usr/bin/env python3
"""On-demand web terminal for the dashboard (terminado + xterm.js). Full shell: see PLAN section 7 security note.

Serves ONLY on 127.0.0.1:8502. Every request (page and websocket) needs the random token that is generated at start
and stored in .lab/terminal_token (mode 600). Bash login shell in ~/qrl-lab. Exits after 30 min without input.

Run:  python3 tools/web_terminal.py   (normally started by the dashboard in tmux window `terminal`)
"""
import hmac
import json
import os
import secrets
import signal
import sys
import time

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HOST = "127.0.0.1"
PORT = 8502
IDLE_LIMIT = 30 * 60
TMUX_SESSION = "lab"
TMUX_WINDOW = "terminal"
XTERM_CSS = "https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css"
XTERM_JS = "https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js"
FIT_JS = "https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js"


def lab_path(*parts):
    return os.path.join(os.environ.get("QRL_LAB_DIR") or KIT, ".lab", *parts)


def token_ok(provided, expected):
    """Constant-time token check; empty or missing tokens never pass."""
    if not provided or not expected:
        return False
    return hmac.compare_digest(str(provided).encode(), str(expected).encode())


def is_idle(last_activity, now, limit=IDLE_LIMIT):
    return (now - last_activity) >= limit


def start_command(kit=KIT, session=TMUX_SESSION, window=TMUX_WINDOW):
    """argv that opens the server in tmux window `window` (detached, not stealing focus)."""
    py = os.path.join(kit, ".venv", "bin", "python")
    return ["tmux", "new-window", "-d", "-t", session, "-n", window, "-c", kit,
            f"{py} tools/web_terminal.py; exec bash"]


def stop_command(session=TMUX_SESSION, window=TMUX_WINDOW):
    return ["tmux", "kill-window", "-t", f"{session}:{window}"]


def running(host=HOST, port=PORT):
    import socket
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def read_token():
    try:
        with open(lab_path("terminal_token")) as f:
            return f.read().strip()
    except OSError:
        return ""


TAILNET_SUFFIX = ".ts.net"
TS_PORTS = {"terminal": 8443, "grafana": 8444, "prometheus": 8445}  # `tailscale serve --https` ports, see docs/MOBILE.md


def tailnet_host(host):
    """Hostname (no port) when `host` is a *.ts.net name, else None."""
    h = (host or "").split(":")[0].strip().lower().rstrip(".")
    return h if h.endswith(TAILNET_SUFFIX) and len(h) > len(TAILNET_SUFFIX) and h.replace("-", "").replace(".", "").isalnum() else None


def service_url(host, service, local_url):
    """https://<host>:<port><path> (query kept) for a *.ts.net request host, otherwise `local_url` unchanged."""
    th = tailnet_host(host)
    if not th:
        return local_url
    from urllib.parse import urlsplit
    u = urlsplit(local_url)
    path = u.path or "/"
    return f"https://{th}:{TS_PORTS[service]}{path}" + (f"?{u.query}" if u.query else "")


def origin_allowed(origin):
    from urllib.parse import urlparse
    try:
        pu = urlparse(origin)
    except ValueError:
        return False
    if pu.hostname in ("127.0.0.1", "localhost"):
        return True
    return pu.scheme == "https" and tailnet_host(pu.hostname) is not None


def iframe_url(host=None):
    tok = read_token()
    return service_url(host, "terminal", f"http://{HOST}:{PORT}/?token={tok}") if tok else ""


def start(wait=8.0):
    """Start the server in tmux window `terminal` unless it already runs. Returns (ok, message)."""
    import subprocess
    if running():
        return True, "already running"
    try:
        os.remove(lab_path("terminal_token"))  # never show a stale token
    except OSError:
        pass
    r = subprocess.run(start_command(), capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        return False, (r.stderr or "tmux failed").strip()
    t0 = time.time()
    while time.time() - t0 < wait:
        if running() and read_token():
            return True, "started"
        time.sleep(0.2)
    return False, "server did not come up"


def stop():
    import subprocess
    r = subprocess.run(stop_command(), capture_output=True, text=True, timeout=10)
    try:
        os.remove(lab_path("terminal_token"))
    except OSError:
        pass
    return r.returncode == 0


def write_token(path):
    tok = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(tok)
    os.chmod(path, 0o600)
    return tok


PAGE = """<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="%(css)s">
<style>html,body{margin:0;height:100%%;background:#111}#t{height:100%%}</style></head>
<body><div id="t"></div>
<script src="%(js)s"></script><script src="%(fit)s"></script>
<script>
const token = new URLSearchParams(location.search).get("token") || "";
const term = new Terminal({cursorBlink: true, fontSize: 14});
const fit = new FitAddon.FitAddon(); term.loadAddon(fit);
term.open(document.getElementById("t")); fit.fit();
const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/websocket?token=" + encodeURIComponent(token));
ws.onmessage = e => { const m = JSON.parse(e.data); if (m[0] === "stdout") term.write(m[1]); };
ws.onopen = () => ws.send(JSON.stringify(["set_size", term.rows, term.cols, 0, 0]));
ws.onclose = () => term.write("\\r\\n[connection closed]\\r\\n");
term.onData(d => ws.readyState === 1 && ws.send(JSON.stringify(["stdin", d])));
window.addEventListener("resize", () => { fit.fit();
  ws.readyState === 1 && ws.send(JSON.stringify(["set_size", term.rows, term.cols, 0, 0])); });
</script></body></html>"""


def make_app(token, state):
    import tornado.web
    from terminado import SingleTermManager, TermSocket

    class Guard:
        def _check(self):
            if not token_ok(self.get_query_argument("token", ""), token):
                raise tornado.web.HTTPError(403)

    class Index(Guard, tornado.web.RequestHandler):
        def get(self):
            self._check()
            state["last"] = time.time()
            self.set_header("Content-Security-Policy", "frame-ancestors http://127.0.0.1:* http://localhost:* *")
            self.write(PAGE % {"css": XTERM_CSS, "js": XTERM_JS, "fit": FIT_JS})

    class Sock(Guard, TermSocket):
        def prepare(self):
            self._check()

        def check_origin(self, origin):
            return origin_allowed(origin)

        def on_message(self, message):
            state["last"] = time.time()
            return super().on_message(message)

    mgr = SingleTermManager(shell_command=["bash", "-l"], term_settings={"cwd": KIT})
    return tornado.web.Application([(r"/", Index), (r"/websocket", Sock, {"term_manager": mgr})]), mgr


def main():
    import tornado.ioloop
    tpath = lab_path("terminal_token")
    os.makedirs(os.path.dirname(tpath), exist_ok=True)
    token = write_token(tpath)
    state = {"last": time.time()}
    app, mgr = make_app(token, state)
    app.listen(PORT, address=HOST)
    loop = tornado.ioloop.IOLoop.current()

    def cleanup(*_):
        try:
            os.remove(tpath)
        except OSError:
            pass
        os._exit(0)  # also ends the shell child via SIGHUP when the pty closes

    def check_idle():
        if is_idle(state["last"], time.time()):
            print("web_terminal: idle timeout, exiting", flush=True)
            cleanup()

    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, cleanup)
    tornado.ioloop.PeriodicCallback(check_idle, 30000).start()
    print(f"web_terminal: listening on {HOST}:{PORT}", flush=True)
    loop.start()


if __name__ == "__main__":
    main()
