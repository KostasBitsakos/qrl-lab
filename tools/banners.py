"""Server-side dismissal of dashboard system banners (survives F5 and restarts).

.lab/dismissed_banners.json = {banner_id: sha256(key)[:16]}. `key` identifies the EVENT (e.g. the boot time, or
state+since for a health banner), not the wording, so changing "εδώ και 3λ" text does not resurrect a dismissed
banner, while a new event (different key) shows again.
"""
import hashlib
import json
import os

ROOT = os.environ.get("QRL_LAB_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _path():
    return os.environ.get("QRL_DISMISSED_FILE") or os.path.join(ROOT, ".lab", "dismissed_banners.json")


def _h(key):
    return hashlib.sha256(str(key).encode()).hexdigest()[:16]


def _load():
    try:
        with open(_path()) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def is_dismissed(banner_id, key):
    return _load().get(banner_id) == _h(key)


def dismiss(banner_id, key):
    d = _load()
    d[banner_id] = _h(key)
    os.makedirs(os.path.dirname(_path()), exist_ok=True)
    tmp = _path() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f)
    os.replace(tmp, _path())


def reboot_key(path=None):
    """Event key of the current recovery flag (its boot time), or None."""
    p = path or os.environ.get("QRL_RECOVERY_FLAG") or os.path.join(ROOT, ".lab", "recovery_flag.json")
    try:
        with open(p) as f:
            return f"reboot:{json.load(f)['boot_at']}"
    except (OSError, ValueError, KeyError):
        return None
