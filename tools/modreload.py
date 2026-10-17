"""Reload local tools modules whose file changed since last load (Streamlit keeps old modules in sys.modules)."""
import importlib
import os
import sys

_MTIMES = {}


def reload_changed(names, cache=None):
    """Reload each already-imported module in `names` if its file mtime differs from the last seen one.
    Returns the list of reloaded names. First sight only records the mtime."""
    cache = _MTIMES if cache is None else cache
    done = []
    for n in names:
        mod = sys.modules.get(n)
        path = getattr(mod, "__file__", None)
        if not path or not os.path.exists(path):
            continue
        mt = os.path.getmtime(path)
        old = cache.get(n)
        cache[n] = mt
        if old is not None and old != mt:
            importlib.reload(mod)
            done.append(n)
    return done
