"""Single-instance guard so scheduled and manual runs never write the database at once."""
import fcntl
import sys
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def exclusive_run(lock_path):
    """Hold an exclusive lock for the duration of the block; exit quietly if another run holds it.

    flock locks are released by the OS when the process dies, so a crash never leaves a stale lock.
    """
    Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("another sync/analyze run is in progress - exiting", file=sys.stderr)
            sys.exit(0)
        yield
