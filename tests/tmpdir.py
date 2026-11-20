"""A temporary directory that cleans up reliably on Windows.

Windows refuses to delete a file that is still open. A SQLite connection that a test (or a background
thread it started) has not closed yet would make tempfile.TemporaryDirectory raise PermissionError on exit,
failing a test whose assertions all passed. This version collects stray connections first, retries
briefly, and leaves anything still locked for the operating system's temp cleaner."""
import gc
import shutil
import tempfile
import time


class TempDir:
    def __init__(self):
        self.name = tempfile.mkdtemp()

    def __enter__(self):
        return self.name

    def __exit__(self, *exc):
        self.cleanup()
        return False

    def cleanup(self):
        for attempt in range(5):
            gc.collect()                      # closes sqlite3 connections nobody references any more
            try:
                shutil.rmtree(self.name)
                return
            except FileNotFoundError:
                return
            except OSError:
                time.sleep(0.1 * (attempt + 1))
        shutil.rmtree(self.name, ignore_errors=True)
