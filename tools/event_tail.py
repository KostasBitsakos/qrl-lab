"""Incremental tail of an append-only JSONL file (.lab/events.jsonl): only bytes appended since the last refresh are
parsed; a full re-read happens on first use, truncation, rotation (new inode) or an in-place rewrite (the 64 bytes
before the read offset changed). Thread-safe. (M-20261021-023)"""
import json
import os
import threading


class EventTail:
    def __init__(self, path, keep=6000, tail_bytes=3_000_000):
        self.path, self.keep, self.tail_bytes = path, keep, tail_bytes
        self.ino, self.off, self.raw, self.ver = None, 0, [], 0
        self._skip_partial, self._guard = False, b""
        self._lock = threading.Lock()

    def refresh(self):
        """(version, records): version increases whenever records change. records is a new list each change; treat
        it (and its dicts) as read-only."""
        with self._lock:
            self._refresh()
            return self.ver, self.raw

    def _reset(self, ino, start):
        self.ino, self.off, self.raw, self.ver = ino, start, [], self.ver + 1
        self._skip_partial, self._guard = start > 0, b""

    def _refresh(self):
        try:
            stt = os.stat(self.path)
        except OSError:
            if self.ino is not None or self.raw:
                self._reset(None, 0)
            return
        with open(self.path, "rb") as f:
            if self.ino == stt.st_ino and stt.st_size >= self.off and self._guard:
                f.seek(self.off - len(self._guard))
                if f.read(len(self._guard)) != self._guard:  # rewritten in place (same inode, not shorter)
                    self.ino = None
            if self.ino != stt.st_ino or stt.st_size < self.off:
                self._reset(stt.st_ino, max(0, stt.st_size - self.tail_bytes))
            if stt.st_size <= self.off:
                return
            f.seek(self.off)
            chunk = f.read(stt.st_size - self.off)
        end = chunk.rfind(b"\n")
        if end < 0:  # no complete line yet (writer mid-line)
            return
        chunk = chunk[:end + 1]
        self.off += len(chunk)
        self._guard = (self._guard + chunk)[-64:]
        lines = chunk.decode("utf-8", "ignore").splitlines()
        if self._skip_partial:
            self._skip_partial = False
            lines = lines[1:]  # the first line of a mid-file tail is cut
        new = []
        for line in lines[-self.keep:]:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(e, dict):
                new.append(e)
        if new:
            self.raw = (self.raw + new)[-self.keep:]
            self.ver += 1
