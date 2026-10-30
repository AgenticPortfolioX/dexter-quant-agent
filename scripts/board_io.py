"""
Shared, thread-safe, atomic writers for the dashboard markdown files.

The Live Strategy Board is written from three places in the same process
(the 15s monitor loop, the 60s heartbeat thread, and the Alpha engine's board
renderer thread) plus standalone scripts.  Without a single lock and a single
atomic write path those writers interleave and corrupt the file.

Every board writer MUST go through `write_text_atomic`.
"""
import os
import threading

_WRITE_LOCK = threading.Lock()


def write_text_atomic(path, text):
    """Write `text` to `path` atomically (temp file + os.replace).

    Readers never observe a partially written board, and concurrent writers
    are serialised within this process.
    """
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with _WRITE_LOCK:
        try:
            with open(tmp_path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass


def read_text(path):
    """Read a text file, returning '' when it does not exist."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except OSError:
        return ""
